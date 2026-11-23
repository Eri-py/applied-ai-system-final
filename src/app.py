"""Command-line entry point for VibeFinder 2.0.

    python -m src.app "something gentle for a rainy sunday morning"
    python -m src.app "40 minutes of house for a party" --verbose
    python -m src.app "music for the gym" --offline --json
    python -m src.app "something to study to" --no-retrieval      # the RAG ablation
    python -m src.app "a wind-down playlist" --tool-loop          # model drives the tools

The output is written so that every number on screen can be traced: the notes that were
retrieved, the profile that was derived from them, the score and reasons for every song, the
confidence and its components, and every repair the agent made along the way.

Exit codes: 0 if a playlist was produced and passed its checks, 1 if constraints were left
unsatisfied, 2 if the request was refused by a guardrail.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from tabulate import tabulate

from src.agent import VibeAgent, PlaylistResult
from src.llm import build_backend
from src.obs import RunLogger, logging_enabled, new_run_id
from src.recommender import SCORING_MODES, load_songs
from src.retrieval import DEFAULT_NOTES_DIR, NoteRetriever, load_notes

BAR_WIDTH = 78


def _rule(title: str = "") -> str:
    if not title:
        return "-" * BAR_WIDTH
    return f"--- {title} " + "-" * max(0, BAR_WIDTH - len(title) - 5)


def _confidence_bar(value: float, width: int = 20) -> str:
    filled = int(round(value * width))
    return "#" * filled + "." * (width - filled)


def render(result: PlaylistResult, verbose: bool = False) -> str:
    """Formats one run as the text a person reads."""
    lines: List[str] = []
    lines.append("")
    lines.append(f'VibeFinder 2.0  |  request: "{result.request}"')
    lines.append(f"planner: {result.backend_detail}  |  run: {result.run_id}")
    lines.append("")

    if result.refused:
        lines.append(_rule("REFUSED"))
        lines.append(f"  {result.refusal}")
        if result.guardrail and result.guardrail.code:
            lines.append(f"  guardrail: {result.guardrail.code}")
        lines.append("")
        return "\n".join(lines)

    if result.degraded:
        lines.append(_rule("DEGRADED"))
        lines.append(f"  The model call failed, so the deterministic planner was used instead.")
        lines.append(f"  reason: {result.degrade_reason}")
        lines.append("")

    # Retrieval
    lines.append(_rule("RETRIEVED NOTES"))
    if result.hits:
        for hit in result.hits:
            lines.append(f"  {hit.score:6.2f}  {hit.title}  [{hit.id}]")
    else:
        lines.append("  (none - retrieval found no relevant note, or was disabled)")
    lines.append("")

    # Profile
    lines.append(_rule("DERIVED PROFILE"))
    shown = {k: v for k, v in result.profile.items() if not k.startswith("_")}
    for key in sorted(shown):
        source = (result.profile.get("_sources") or {}).get(key, "")
        suffix = f"   <- {source}" if source and verbose else ""
        lines.append(f"  {key:16} {shown[key]}{suffix}")
    if result.rationale:
        lines.append(f"\n  why: {result.rationale}")
    for note in result.clamp_notes:
        lines.append(f"  [clamped] {note}")
    lines.append("")

    # Playlist
    lines.append(_rule("PLAYLIST"))
    if result.picks:
        confidence_per_song = (result.confidence.per_song if result.confidence else {}) or {}
        rows = []
        for index, (song, score, _) in enumerate(result.picks, start=1):
            rows.append(
                [
                    index,
                    song["title"],
                    song["artist"],
                    song["genre"],
                    f"{float(song['energy']):.2f}",
                    int(song["tempo_bpm"]),
                    f"{int(song['duration_sec']) // 60}:{int(song['duration_sec']) % 60:02d}",
                    f"{score:.2f}",
                    f"{confidence_per_song.get(int(song['id']), 0.0):.2f}",
                ]
            )
        lines.append(
            tabulate(
                rows,
                headers=["#", "title", "artist", "genre", "energy", "bpm", "len", "score", "conf"],
                tablefmt="simple",
            )
        )
        total = sum(int(song["duration_sec"]) for song, _, _ in result.picks)
        lines.append(f"\n  total running time: {total // 60} min {total % 60} sec")
    else:
        lines.append("  (no songs)")
    lines.append("")

    # Why each song
    lines.append(_rule("WHY EACH SONG"))
    for index, (song, score, reasons) in enumerate(result.picks, start=1):
        lines.append(f"  {index}. {song['title']} ({score:.2f})")
        for reason in reasons.split(";"):
            if reason.strip():
                lines.append(f"       - {reason.strip()}")
    lines.append("")

    # The agent's work
    lines.append(_rule("AGENT LOOP"))
    for attempt in result.attempts:
        status = "PASS" if attempt["ok"] else "FAIL"
        lines.append(
            f"  attempt {attempt['iteration']}: k={attempt['k']} order={attempt['order']} "
            f"diversify={attempt['diversify']} -> {status}"
        )
        for code in attempt.get("failures", []):
            lines.append(f"       x {code}")
        for action in attempt.get("repairs", []) or []:
            lines.append(f"       > {action}")
    if result.verdict.failures:
        lines.append("  unresolved after the final attempt:")
        for failure in result.verdict.failures:
            lines.append(f"       ! [{failure.code}] {failure.detail}")
    lines.append("")

    # Confidence
    if result.confidence:
        report = result.confidence
        lines.append(_rule("CONFIDENCE"))
        lines.append(f"  {report.value:.2f}  [{_confidence_bar(report.value)}]  {report.band.upper()}")
        for key in sorted(report.components):
            lines.append(f"       {key:14} {report.components[key]:.2f}")
        for note in report.notes:
            lines.append(f"  note: {note}")
        lines.append("")

    # Summary
    if result.summary:
        lines.append(_rule("SUMMARY"))
        for line in _wrap(result.summary, BAR_WIDTH - 4):
            lines.append(f"  {line}")
        lines.append("")

    footer = f"ok={result.ok}  iterations={result.iterations}"
    if result.log_path:
        footer += f"  log={result.log_path}"
    lines.append(footer)
    lines.append("")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> List[str]:
    """Minimal greedy word wrap, so the summary paragraph reads well in a terminal."""
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def result_to_dict(result: PlaylistResult) -> dict:
    """Machine-readable form of a run, for `--json` and for the evaluation harness."""
    return {
        "run_id": result.run_id,
        "request": result.request,
        "ok": result.ok,
        "refused": result.refused,
        "refusal": result.refusal,
        "guardrail_code": result.guardrail.code if result.guardrail else None,
        "cold_start": result.cold_start,
        "backend": result.backend,
        "backend_detail": result.backend_detail,
        "degraded": result.degraded,
        "degrade_reason": result.degrade_reason,
        "profile": {k: v for k, v in result.profile.items() if not k.startswith("_")},
        "retrieved": [{"id": hit.id, "title": hit.title, "score": hit.score} for hit in result.hits],
        "playlist": [
            {
                "id": int(song["id"]),
                "title": song["title"],
                "artist": song["artist"],
                "genre": song["genre"],
                "energy": float(song["energy"]),
                "tempo_bpm": int(song["tempo_bpm"]),
                "duration_sec": int(song["duration_sec"]),
                "language": song["language"],
                "score": round(float(score), 2),
                "reasons": reasons,
            }
            for song, score, reasons in result.picks
        ],
        "total_seconds_of_music": sum(int(song["duration_sec"]) for song, _, _ in result.picks),
        "confidence": result.confidence.as_dict() if result.confidence else None,
        "verdict": result.verdict.as_dict(),
        "iterations": result.iterations,
        "attempts": result.attempts,
        "summary": result.summary,
        "rationale": result.rationale,
        "clamp_notes": result.clamp_notes,
        "log_path": result.log_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.app",
        description="VibeFinder 2.0 - turn a plain-English request into an explained playlist.",
        epilog='example: python -m src.app "half an hour of lo-fi to wind down" --verbose',
    )
    parser.add_argument("request", nargs="?", help="what you want to listen to, in plain English")
    parser.add_argument("-k", "--songs", type=int, default=None, help="how many songs (1-10)")
    parser.add_argument(
        "--mode",
        choices=sorted(SCORING_MODES),
        default=None,
        help="force a scoring strategy instead of letting the planner choose",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="use the deterministic planner even if an API key is available",
    )
    parser.add_argument(
        "--no-retrieval",
        action="store_true",
        help="ablation: skip the notes corpus entirely, to show what retrieval contributes",
    )
    parser.add_argument(
        "--tool-loop",
        action="store_true",
        help="let Claude drive the tools itself instead of the Python loop (needs an API key)",
    )
    parser.add_argument("--verbose", action="store_true", help="trace every event to stderr")
    parser.add_argument("--json", action="store_true", help="print the run as JSON")
    parser.add_argument("--no-log", action="store_true", help="do not write a run log file")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.request:
        print(
            'Give a request, e.g.:  python -m src.app "something calm for studying"\n'
            "Run with --help for every option.",
            file=sys.stderr,
        )
        return 2

    logger = RunLogger(
        run_id=new_run_id(),
        trace=args.verbose,
        enabled=logging_enabled() and not args.no_log,
    )

    songs = load_songs()
    retriever = NoteRetriever(load_notes(DEFAULT_NOTES_DIR))
    backend, detail = build_backend(logger=logger, force_offline=args.offline)

    if args.tool_loop:
        return _run_tool_loop(args, songs, retriever, logger, detail)

    agent = VibeAgent(
        songs=songs,
        retriever=retriever,
        backend=backend,
        backend_detail=detail,
        logger=logger,
        use_retrieval=not args.no_retrieval,
    )

    # CLI overrides are applied after planning but before clamping, so an explicit `-k` or
    # `--mode` beats whatever the planner inferred and is still range-checked.
    overrides = {"k": args.songs, "mode": args.mode}
    result = agent.run(args.request, overrides=overrides)

    if args.json:
        print(json.dumps(result_to_dict(result), indent=2, default=str))
    else:
        print(render(result, verbose=args.verbose))

    if result.refused:
        return 2
    return 0 if result.ok else 1


def _run_tool_loop(args, songs, retriever, logger, detail) -> int:
    """The `--tool-loop` path: Claude decides which tools to call."""
    from src.agent import ToolBox
    from src.guardrails import check_request
    from src.llm import credentials_available, offline_forced
    from src.tool_loop import run_tool_loop

    guard = check_request(args.request)
    logger.event("guardrail", ok=guard.ok, code=guard.code)
    if guard.refused:
        print(f"\nREFUSED: {guard.message}\n")
        return 2

    if offline_forced() or not credentials_available():
        print(
            "\n--tool-loop needs an API key: it is the path where Claude itself decides which\n"
            "tools to call, so there is nothing to fall back to. Set ANTHROPIC_API_KEY, or drop\n"
            "the flag to use the deterministic Python loop (which needs no key).\n",
            file=sys.stderr,
        )
        return 2

    tools = ToolBox(songs, retriever, logger)
    outcome = run_tool_loop(guard.cleaned, tools, logger=logger)

    print("")
    print(f'VibeFinder 2.0 (model-driven tool loop)  |  request: "{args.request}"')
    print(f"turns: {outcome.iterations}   tools called: {', '.join(outcome.tool_calls) or 'none'}")
    print(f"stopped: {outcome.stopped_because}")
    if outcome.usage:
        print(f"tokens: {outcome.usage}")
    print("")
    if outcome.picks:
        rows = [
            [index, song["title"], song["artist"], song["genre"], f"{float(song['energy']):.2f}", f"{score:.2f}"]
            for index, (song, score, _) in enumerate(outcome.picks, start=1)
        ]
        print(tabulate(rows, headers=["#", "title", "artist", "genre", "energy", "score"], tablefmt="simple"))
    else:
        print("  (the loop produced no playlist)")
    print("")
    if outcome.explanation:
        for line in _wrap(outcome.explanation, BAR_WIDTH - 2):
            print(f"  {line}")
        print("")
    for error in outcome.errors:
        print(f"  [error] {error}")
    logger.close()
    return 0 if outcome.finalized and outcome.picks else 1


if __name__ == "__main__":
    raise SystemExit(main())
