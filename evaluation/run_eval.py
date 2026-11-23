"""The evaluation harness: runs the labelled case set and three structured experiments.

    python -m evaluation.run_eval                 # run everything, print the report
    python -m evaluation.run_eval --write         # also write EVALUATION.md and results.json
    python -m evaluation.run_eval --quick         # cases only, skip the experiments

What it measures:

1. **Correctness** -- every case in `evaluation/cases.py` against its declared expectations,
   reporting which individual criterion failed rather than just the case.
2. **Reproducibility** -- each case run three times, checking the output is identical. A
   deterministic system is a testable one, so this is a property worth asserting, not
   assuming.
3. **The retrieval ablation** -- every case re-run with the notes corpus switched off. This is
   the measurement that shows whether RAG is load-bearing: if the pass rate were unchanged,
   the retrieval layer would be decoration.
4. **Confidence calibration** -- mean published confidence on cases that passed versus cases
   that failed. A confidence score that does not separate those two is not measuring anything,
   and reporting it would be worse than reporting nothing.

Everything runs against the deterministic offline backend by default, so the numbers in
EVALUATION.md are reproducible by anyone with no API key and no spend. `--live` runs the same
set through Claude instead, for comparison.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from evaluation.cases import CASES, Case
from src.agent import VibeAgent, PlaylistResult
from src.app import result_to_dict
from src.llm import OfflineBackend, build_backend
from src.obs import RunLogger
from src.recommender import load_songs
from src.retrieval import NoteRetriever, load_notes

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_JSON = Path(__file__).resolve().parent / "results.json"
REPORT_MD = REPO_ROOT / "EVALUATION.md"

REPRODUCIBILITY_RUNS = 3


# --------------------------------------------------------------------------------------
# Criteria
# --------------------------------------------------------------------------------------


def _mean(values: List[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _energies(result: PlaylistResult) -> List[float]:
    return [float(song["energy"]) for song, _, _ in result.picks]


def _playlist_minutes(result: PlaylistResult) -> float:
    return sum(int(song["duration_sec"]) for song, _, _ in result.picks) / 60.0


# Each criterion takes (result, expected) and returns (passed, observed-as-text).
CRITERIA: Dict[str, Callable[[PlaylistResult, object], Tuple[bool, str]]] = {
    "not_refused": lambda r, _: (not r.refused, f"refused={r.refused}" + (f" ({r.guardrail.code})" if r.refused else "")),
    "refused_with": lambda r, expected: (
        r.refused and r.guardrail is not None and r.guardrail.code == expected,
        f"{r.guardrail.code if r.guardrail else 'none'}",
    ),
    "no_playlist": lambda r, _: (not r.picks, f"{len(r.picks)} songs"),
    "exactly_k": lambda r, expected: (len(r.picks) == expected, f"{len(r.picks)} songs"),
    "min_songs": lambda r, expected: (len(r.picks) >= expected, f"{len(r.picks)} songs"),
    "min_mean_energy": lambda r, expected: (
        _mean(_energies(r)) >= expected,
        f"mean energy {_mean(_energies(r)):.2f}",
    ),
    "max_mean_energy": lambda r, expected: (
        bool(r.picks) and _mean(_energies(r)) <= expected,
        f"mean energy {_mean(_energies(r)):.2f}",
    ),
    "energy_between": lambda r, expected: (
        bool(r.picks) and expected[0] <= _mean(_energies(r)) <= expected[1],
        f"mean energy {_mean(_energies(r)):.2f}",
    ),
    "min_mean_acousticness": lambda r, expected: (
        _mean([float(s["acousticness"]) for s, _, _ in r.picks]) >= expected,
        f"mean acousticness {_mean([float(s['acousticness']) for s, _, _ in r.picks]):.2f}",
    ),
    "max_mean_popularity": lambda r, expected: (
        _mean([int(s["popularity"]) for s, _, _ in r.picks]) <= expected,
        f"mean popularity {_mean([int(s['popularity']) for s, _, _ in r.picks]):.0f}",
    ),
    "no_repeat_artist": lambda r, _: (
        len({s["artist"] for s, _, _ in r.picks}) == len(r.picks),
        f"{len({s['artist'] for s, _, _ in r.picks})} distinct artists of {len(r.picks)}",
    ),
    "all_scores_positive": lambda r, _: (
        bool(r.picks) and all(score > 0 for _, score, _ in r.picks),
        f"min score {min([score for _, score, _ in r.picks], default=0):.2f}",
    ),
    "distinct_genres": lambda r, expected: (
        len({s["genre"] for s, _, _ in r.picks}) >= expected,
        f"{len({s['genre'] for s, _, _ in r.picks})} distinct genres",
    ),
    "includes_genre": lambda r, expected: (
        any(str(s["genre"]) == expected for s, _, _ in r.picks),
        f"genres {sorted({str(s['genre']) for s, _, _ in r.picks})}",
    ),
    "excludes_genre": lambda r, expected: (
        all(str(s["genre"]) != expected for s, _, _ in r.picks),
        f"genres {sorted({str(s['genre']) for s, _, _ in r.picks})}",
    ),
    "language_share": lambda r, expected: (
        bool(r.picks)
        and sum(1 for s, _, _ in r.picks if str(s["language"]) == expected[0]) / len(r.picks) >= expected[1],
        f"{sum(1 for s, _, _ in r.picks if str(s['language']) == expected[0])}/{len(r.picks)} {expected[0]}",
    ),
    "duration_minutes_within": lambda r, expected: (
        abs(_playlist_minutes(r) - expected[0]) <= expected[0] * expected[1],
        f"{_playlist_minutes(r):.1f} min",
    ),
    "min_confidence": lambda r, expected: (
        r.confidence is not None and r.confidence.value >= expected,
        f"confidence {r.confidence.value if r.confidence else 'none'}",
    ),
    "max_confidence": lambda r, expected: (
        r.confidence is not None and r.confidence.value <= expected,
        f"confidence {r.confidence.value if r.confidence else 'none'}",
    ),
    "retrieved_note": lambda r, expected: (
        bool(r.hits) and r.hits[0].id == expected,
        f"top note {r.hits[0].id if r.hits else 'none'}",
    ),
    "profile_field": lambda r, expected: (
        r.profile.get(expected[0]) == expected[1],
        f"{expected[0]}={r.profile.get(expected[0])!r}",
    ),
    "cold_start": lambda r, expected: (r.cold_start is expected, f"cold_start={r.cold_start}"),
    "arc_not_rising": lambda r, _: (
        len(r.picks) < 2 or _energies(r)[-1] <= _energies(r)[0],
        f"energy {_energies(r)[0]:.2f} -> {_energies(r)[-1]:.2f}" if r.picks else "no songs",
    ),
    "arc_not_falling": lambda r, _: (
        len(r.picks) < 2 or _energies(r)[-1] >= _energies(r)[0],
        f"energy {_energies(r)[0]:.2f} -> {_energies(r)[-1]:.2f}" if r.picks else "no songs",
    ),
    "relaxation_mentions": lambda r, expected: (
        r.confidence is not None and any(expected in note for note in r.confidence.notes),
        f"notes {r.confidence.notes if r.confidence else []}",
    ),
    "confidence_note_mentions": lambda r, expected: (
        r.confidence is not None and any(expected in note for note in r.confidence.notes),
        f"{len(r.confidence.notes) if r.confidence else 0} notes",
    ),
    # Degenerate inputs: the only requirement is that the system handled them.
    "terminates": lambda r, _: (True, f"{r.iterations} iterations"),
    "no_crash": lambda r, _: (True, "handled"),
    "any_playlist_or_honest_failure": lambda r, _: (
        bool(r.picks) or bool(r.verdict.failures) or r.refused,
        f"{len(r.picks)} songs, {len(r.verdict.failures)} unresolved",
    ),
}


@dataclass
class CriterionOutcome:
    name: str
    expected: object
    passed: bool
    observed: str


@dataclass
class CaseOutcome:
    case: Case
    passed: bool
    criteria: List[CriterionOutcome] = field(default_factory=list)
    confidence: Optional[float] = None
    iterations: int = 0
    refused: bool = False
    error: str = ""
    seconds: float = 0.0
    result_json: Optional[Dict] = None

    @property
    def failed_criteria(self) -> List[CriterionOutcome]:
        return [outcome for outcome in self.criteria if not outcome.passed]


def make_agent(use_retrieval: bool = True, live: bool = False) -> VibeAgent:
    """One agent, with logging off so an evaluation run does not litter `logs/`."""
    logger = RunLogger(enabled=False)
    if live:
        backend, detail = build_backend(logger=logger)
    else:
        backend, detail = OfflineBackend(), "offline (deterministic planner; evaluation)"
    return VibeAgent(
        songs=load_songs(),
        retriever=NoteRetriever(load_notes()),
        backend=backend,
        backend_detail=detail,
        logger=logger,
        use_retrieval=use_retrieval,
    )


def run_case(agent: VibeAgent, case: Case) -> CaseOutcome:
    """Runs one case and checks every criterion it declares."""
    started = time.perf_counter()
    try:
        result = agent.run(case.request)
    except Exception as error:  # noqa: BLE001 - a crash is a result, and must be reported
        return CaseOutcome(
            case=case,
            passed=False,
            error=f"{type(error).__name__}: {error}",
            seconds=time.perf_counter() - started,
        )

    outcomes: List[CriterionOutcome] = []
    for name, expected in case.expect.items():
        check = CRITERIA.get(name)
        if check is None:
            outcomes.append(CriterionOutcome(name, expected, False, "unknown criterion"))
            continue
        try:
            passed, observed = check(result, expected)
        except Exception as error:  # noqa: BLE001 - a broken check must not stop the suite
            passed, observed = False, f"check raised {type(error).__name__}"
        outcomes.append(CriterionOutcome(name, expected, bool(passed), observed))

    return CaseOutcome(
        case=case,
        passed=all(outcome.passed for outcome in outcomes),
        criteria=outcomes,
        confidence=result.confidence.value if result.confidence else None,
        iterations=result.iterations,
        refused=result.refused,
        seconds=time.perf_counter() - started,
        result_json=result_to_dict(result),
    )


# --------------------------------------------------------------------------------------
# Experiments
# --------------------------------------------------------------------------------------


def experiment_reproducibility(agent: VibeAgent, runs: int = REPRODUCIBILITY_RUNS) -> Dict:
    """Runs every case `runs` times and checks the playlists are identical each time."""
    unstable: List[str] = []
    for case in CASES:
        signatures = set()
        for _ in range(runs):
            result = agent.run(case.request)
            signatures.add(
                json.dumps(
                    {
                        "ids": [int(song["id"]) for song, _, _ in result.picks],
                        "refused": result.refused,
                        "confidence": result.confidence.value if result.confidence else None,
                    },
                    sort_keys=True,
                )
            )
        if len(signatures) > 1:
            unstable.append(case.id)
    return {
        "runs_per_case": runs,
        "cases": len(CASES),
        "identical": len(CASES) - len(unstable),
        "unstable_cases": unstable,
        "rate": round((len(CASES) - len(unstable)) / len(CASES), 3),
    }


def experiment_ablation(live: bool = False) -> Dict:
    """Re-runs the whole set with retrieval disabled, to measure what the notes contribute."""
    with_notes = [run_case(make_agent(use_retrieval=True, live=live), case) for case in CASES]
    without = [run_case(make_agent(use_retrieval=False, live=live), case) for case in CASES]

    def summarise(outcomes: List[CaseOutcome]) -> Dict:
        confidences = [o.confidence for o in outcomes if o.confidence is not None]
        return {
            "passed": sum(1 for o in outcomes if o.passed),
            "total": len(outcomes),
            "pass_rate": round(sum(1 for o in outcomes if o.passed) / len(outcomes), 3),
            "mean_confidence": round(_mean(confidences), 3),
        }

    newly_failing = sorted(
        {o.case.id for o in without if not o.passed} - {o.case.id for o in with_notes if not o.passed}
    )
    return {
        "with_retrieval": summarise(with_notes),
        "without_retrieval": summarise(without),
        "cases_that_only_fail_without_retrieval": newly_failing,
    }


def experiment_calibration(outcomes: List[CaseOutcome], live: bool = False) -> Dict:
    """Checks the confidence score separates runs that passed from runs that failed.

    The main suite currently passes every case, which leaves nothing to compare against -- so
    the pass/fail separation is measured on the degraded configuration from the ablation,
    where 13 cases genuinely fail. That is a fairer test anyway: those runs failed for real
    reasons, and the question is whether the published confidence saw it coming.
    """
    scored = [o for o in outcomes if o.confidence is not None and not o.refused]
    thin = [o.confidence for o in scored if o.case.category == "thin"]
    specified = [o.confidence for o in scored if o.case.category in ("happy", "situation")]

    degraded = [
        o
        for o in (run_case(make_agent(use_retrieval=False, live=live), case) for case in CASES)
        if o.confidence is not None and not o.refused
    ]
    degraded_pass = [o.confidence for o in degraded if o.passed]
    degraded_fail = [o.confidence for o in degraded if not o.passed]

    return {
        "scored_runs": len(scored),
        "mean_confidence_all_passing": round(_mean([o.confidence for o in scored if o.passed]), 3),
        "mean_confidence_thin_requests": round(_mean(thin), 3) if thin else None,
        "mean_confidence_specified_requests": round(_mean(specified), 3) if specified else None,
        "thin_scored_below_specified": (_mean(thin) < _mean(specified)) if thin and specified else None,
        "separation_measured_on": "the no-retrieval configuration, where cases actually fail",
        "degraded_scored_runs": len(degraded),
        "degraded_mean_confidence_passing": round(_mean(degraded_pass), 3) if degraded_pass else None,
        "degraded_mean_confidence_failing": round(_mean(degraded_fail), 3) if degraded_fail else None,
        "degraded_separation": (
            round(_mean(degraded_pass) - _mean(degraded_fail), 3) if degraded_pass and degraded_fail else None
        ),
    }


# --------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------


def _table(headers: List[str], rows: List[List[str]]) -> str:
    """A markdown table, written by hand so the report has no rendering dependency."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def build_report(outcomes: List[CaseOutcome], experiments: Dict, backend_detail: str) -> str:
    passed = sum(1 for outcome in outcomes if outcome.passed)
    total = len(outcomes)
    confidences = [o.confidence for o in outcomes if o.confidence is not None]

    parts: List[str] = []
    parts.append("# Evaluation results\n")
    parts.append(
        "Generated by `python -m evaluation.run_eval --write`. Every number here is "
        "reproducible: the suite runs against the deterministic offline planner, so it needs "
        "no API key and spends nothing.\n"
    )
    parts.append(
        f"- **planner:** {backend_detail}\n"
        f"- **cases:** {total}\n"
        f"- **passed:** {passed}/{total} ({passed / total:.0%})\n"
        f"- **mean confidence:** {_mean(confidences):.2f}\n"
        f"- **mean repair iterations:** "
        f"{_mean([float(o.iterations) for o in outcomes if not o.refused]):.2f}\n"
    )

    # Headline summary sentence, in the shape the brief asks for.
    parts.append("\n## Summary\n")
    failing = [o for o in outcomes if not o.passed]
    if failing:
        parts.append(
            f"{passed} of {total} cases passed. The {len(failing)} that did not are "
            f"{', '.join('`' + o.case.id + '`' for o in failing)}; each failing criterion is "
            f"listed in the table below with what was actually observed.\n"
        )
    else:
        parts.append(
            f"All {total} cases passed. Confidence averaged {_mean(confidences):.2f} across the "
            f"set, and the agent needed "
            f"{_mean([float(o.iterations) for o in outcomes if not o.refused]):.2f} attempts per "
            f"request on average.\n"
        )
        parts.append(
            "\n**That 100% should not be read as a strong result on its own.** The case set was "
            "written alongside the fixes it describes: eight real defects were found by "
            "running the system by hand and reading its output (a faint retrieval hit "
            "injecting invented numeric targets, a cold-start request driving the repair loop "
            "to exclude the entire catalog, and an off-domain check that rejected `my "
            "girlfriend dumped me`, among others -- the full list is in the README), and the "
            "cases that would have caught them were added as they were fixed. A suite that "
            "passes everything it was written against is a regression guard, not evidence of "
            "quality.\n\n"
            "The load-bearing evidence is in the three experiments below, where the system is "
            "measured against configurations it was *not* tuned for -- and in the ablation it "
            f"drops to a "
            f"{experiments.get('ablation', {}).get('without_retrieval', {}).get('pass_rate', 0):.0%} "
            "pass rate.\n"
        )

    # Per-category
    parts.append("\n## By category\n")
    categories: Dict[str, List[CaseOutcome]] = {}
    for outcome in outcomes:
        categories.setdefault(outcome.case.category, []).append(outcome)
    rows = []
    for category in sorted(categories):
        group = categories[category]
        group_confidences = [o.confidence for o in group if o.confidence is not None]
        rows.append(
            [
                f"`{category}`",
                len(group),
                sum(1 for o in group if o.passed),
                f"{sum(1 for o in group if o.passed) / len(group):.0%}",
                f"{_mean(group_confidences):.2f}" if group_confidences else "n/a",
            ]
        )
    parts.append(_table(["category", "cases", "passed", "rate", "mean confidence"], rows))

    # Case detail
    parts.append("\n## Every case\n")
    rows = []
    for outcome in outcomes:
        if outcome.error:
            detail = f"**crashed:** {outcome.error}"
        elif outcome.passed:
            detail = f"{len(outcome.criteria)} criteria met"
        else:
            detail = "<br>".join(
                f"`{criterion.name}` expected `{criterion.expected}`, observed {criterion.observed}"
                for criterion in outcome.failed_criteria
            )
        rows.append(
            [
                f"`{outcome.case.id}`",
                f"`{outcome.case.category}`",
                f'"{outcome.case.request[:58]}{"..." if len(outcome.case.request) > 58 else ""}"',
                "PASS" if outcome.passed else "FAIL",
                f"{outcome.confidence:.2f}" if outcome.confidence is not None else "-",
                outcome.iterations,
                detail,
            ]
        )
    parts.append(
        _table(["case", "category", "request", "result", "conf", "iters", "detail"], rows)
    )

    # Experiments
    if "reproducibility" in experiments:
        data = experiments["reproducibility"]
        parts.append("\n## Experiment 1: reproducibility\n")
        parts.append(
            f"Each of the {data['cases']} cases was run {data['runs_per_case']} times and the "
            f"playlist, refusal and confidence compared.\n"
        )
        parts.append(
            _table(
                ["metric", "value"],
                [
                    ["cases run", data["cases"]],
                    ["runs per case", data["runs_per_case"]],
                    ["byte-identical across runs", f"{data['identical']}/{data['cases']}"],
                    ["rate", f"{data['rate']:.0%}"],
                    ["unstable cases", ", ".join(data["unstable_cases"]) or "none"],
                ],
            )
        )

    if "ablation" in experiments:
        data = experiments["ablation"]
        parts.append("\n## Experiment 2: the retrieval ablation\n")
        parts.append(
            "The same suite with the notes corpus switched off (`--no-retrieval`). This is the "
            "measurement that shows whether retrieval is load-bearing: if the pass rate were "
            "unchanged, the RAG layer would be decoration.\n"
        )
        parts.append(
            _table(
                ["configuration", "passed", "pass rate", "mean confidence"],
                [
                    [
                        "with retrieval",
                        f"{data['with_retrieval']['passed']}/{data['with_retrieval']['total']}",
                        f"{data['with_retrieval']['pass_rate']:.0%}",
                        f"{data['with_retrieval']['mean_confidence']:.2f}",
                    ],
                    [
                        "without retrieval",
                        f"{data['without_retrieval']['passed']}/{data['without_retrieval']['total']}",
                        f"{data['without_retrieval']['pass_rate']:.0%}",
                        f"{data['without_retrieval']['mean_confidence']:.2f}",
                    ],
                ],
            )
        )
        broken = data["cases_that_only_fail_without_retrieval"]
        parts.append(
            f"\nCases that pass with retrieval and fail without it: "
            f"{', '.join('`' + case_id + '`' for case_id in broken) if broken else 'none'}.\n"
        )

    if "calibration" in experiments:
        data = experiments["calibration"]
        parts.append("\n## Experiment 3: is the confidence score worth publishing\n")
        parts.append(
            "A confidence number that does not separate good runs from bad ones is not "
            "measuring anything, and publishing it would be worse than publishing nothing.\n"
        )
        parts.append(
            _table(
                ["metric", "value"],
                [
                    ["scored runs (refusals excluded)", data["scored_runs"]],
                    ["mean confidence, thin requests", data["mean_confidence_thin_requests"]],
                    ["mean confidence, specified requests", data["mean_confidence_specified_requests"]],
                    ["thin scored below specified", data["thin_scored_below_specified"]],
                    ["--- pass/fail separation, measured on the no-retrieval runs ---", ""],
                    ["degraded runs scored", data["degraded_scored_runs"]],
                    ["mean confidence, degraded runs that passed", data["degraded_mean_confidence_passing"]],
                    ["mean confidence, degraded runs that failed", data["degraded_mean_confidence_failing"]],
                    ["separation", data["degraded_separation"]],
                ],
            )
        )
        separation = data.get("degraded_separation")
        thin_gap = None
        if data["mean_confidence_specified_requests"] and data["mean_confidence_thin_requests"]:
            thin_gap = round(
                data["mean_confidence_specified_requests"] - data["mean_confidence_thin_requests"], 3
            )
        parts.append(
            "\n**Reading this honestly: the confidence score is good at one of its two jobs "
            "and weak at the other.**\n\n"
            f"It separates a thin request from a well-specified one clearly -- a gap of "
            f"{thin_gap} between the two groups ("
            f"{data['mean_confidence_thin_requests']} against "
            f"{data['mean_confidence_specified_requests']}). That is the failure it was built "
            "to catch, and it catches it.\n\n"
            f"It is much weaker at separating runs that *failed* from runs that *passed* when "
            f"both were equally under-informed: only {separation} between them in the degraded "
            "configuration. The reason is structural -- two of the four components (retrieval "
            "strength and specificity) are near zero for every run in that configuration, so "
            "they depress the score for the passing and failing runs alike. In other words the "
            "score answers \"was I told enough to do this well?\" and not \"did I actually get "
            "this one right?\". Those are different questions, and only the first is currently "
            "measured. Narrowing that gap would need a signal the system does not yet have, "
            "such as held-out human judgements to regress against.\n"
        )

    parts.append("\n## What this suite does not cover\n")
    parts.append(
        "- **The live Claude path.** Every number above comes from the deterministic offline\n"
        "  planner. The `ClaudeBackend` request shape is pinned by unit tests with a fake\n"
        "  client (model id, schema, grounding content, refusal handling, fallback), but no\n"
        "  test in this repository has called the real API. Run\n"
        "  `python -m evaluation.run_eval --live` with `ANTHROPIC_API_KEY` set to produce the\n"
        "  comparable table.\n"
        "- **Playlist taste.** Every criterion here is a measurable property -- energy, "
        "artist repetition, running time, ordering. Whether the playlist is *good* is a human\n"
        "  judgement, recorded separately in `docs/human_eval.md`.\n"
        "- **Catalog scale.** 22 songs is small enough that some constraints are\n"
        "  unsatisfiable in principle (there is exactly one Spanish track). The suite asserts\n"
        "  the system relaxes and explains, not that it succeeds.\n"
    )
    return "\n".join(parts)


def print_console(outcomes: List[CaseOutcome], experiments: Dict) -> None:
    passed = sum(1 for outcome in outcomes if outcome.passed)
    print()
    print("=" * 78)
    print(f"  VibeFinder 2.0 evaluation: {passed}/{len(outcomes)} cases passed")
    print("=" * 78)
    for outcome in outcomes:
        mark = "PASS" if outcome.passed else "FAIL"
        confidence = f"{outcome.confidence:.2f}" if outcome.confidence is not None else " -  "
        print(f"  [{mark}] {outcome.case.id:20} conf={confidence}  iters={outcome.iterations}")
        for criterion in outcome.failed_criteria:
            print(f"         - {criterion.name}: expected {criterion.expected!r}, got {criterion.observed}")
        if outcome.error:
            print(f"         ! {outcome.error}")
    for name, data in experiments.items():
        print()
        print(f"  --- {name} ---")
        print("  " + json.dumps(data, indent=2).replace("\n", "\n  "))
    print()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evaluation.run_eval")
    parser.add_argument("--write", action="store_true", help="write EVALUATION.md and results.json")
    parser.add_argument("--quick", action="store_true", help="cases only, skip the experiments")
    parser.add_argument("--live", action="store_true", help="use the Claude backend instead of offline")
    parser.add_argument("--case", help="run a single case by id")
    args = parser.parse_args(argv)

    if not args.live:
        # Pin the planner even if a key is present, so the committed numbers are reproducible.
        os.environ["VIBEFINDER_OFFLINE"] = "1"

    agent = make_agent(live=args.live)
    cases = [case for case in CASES if case.id == args.case] if args.case else CASES
    if not cases:
        print(f"no such case: {args.case}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    outcomes = [run_case(agent, case) for case in cases]

    experiments: Dict = {}
    if not args.quick and not args.case:
        experiments["reproducibility"] = experiment_reproducibility(make_agent(live=args.live))
        experiments["ablation"] = experiment_ablation(live=args.live)
        experiments["calibration"] = experiment_calibration(outcomes, live=args.live)

    print_console(outcomes, experiments)
    elapsed = time.perf_counter() - started
    print(f"  completed in {elapsed:.1f}s")

    if args.write:
        report = build_report(outcomes, experiments, agent.backend_detail)
        REPORT_MD.write_text(report, encoding="utf-8")
        RESULTS_JSON.write_text(
            json.dumps(
                {
                    # No timings or commit hash in here on purpose: this file is
                    # committed, and CI regenerates it to check the report is not
                    # stale. A value that changes on every run would make that
                    # check fire constantly and mean nothing.
                    "generated_by": "python -m evaluation.run_eval --write",
                    "backend": agent.backend_detail,
                    "summary": {
                        "cases": len(outcomes),
                        "passed": sum(1 for outcome in outcomes if outcome.passed),
                        "mean_confidence": round(
                            _mean([o.confidence for o in outcomes if o.confidence is not None]), 3
                        ),
                    },
                    "cases": [
                        {
                            "id": outcome.case.id,
                            "category": outcome.case.category,
                            "request": outcome.case.request,
                            "passed": outcome.passed,
                            "confidence": outcome.confidence,
                            "iterations": outcome.iterations,
                            "error": outcome.error,
                            "criteria": [
                                {
                                    "name": criterion.name,
                                    "expected": criterion.expected,
                                    "passed": criterion.passed,
                                    "observed": criterion.observed,
                                }
                                for criterion in outcome.criteria
                            ],
                        }
                        for outcome in outcomes
                    ],
                    "experiments": experiments,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"  wrote {REPORT_MD.relative_to(REPO_ROOT)} and {RESULTS_JSON.relative_to(REPO_ROOT)}")

    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
