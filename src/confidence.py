"""Confidence scoring: how much the system should be trusted on a given run.

The failure this exists to prevent is the one `data/notes/theory-cold-start.md` describes: a
playlist built from a request that specified almost nothing looks exactly like a playlist
built from a precise one. Five songs, five explanations, same formatting. Without a published
confidence the user has no way to tell those two runs apart, and the thin one is the dangerous
one precisely because it is invisible.

The score is a weighted sum of four measurable components, never a model's self-report. A
model asked "how confident are you?" produces a number correlated with its own fluency rather
than with the quality of the retrieval or the margin between candidates, so every component
here is computed from the run's own data.

`evaluation/run_eval.py` checks whether the number means anything, by comparing average
confidence on cases that pass with average confidence on cases that fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# How much each component contributes. Retrieval and specificity describe how much the system
# was *told*; margin and constraints describe how well it then *did*. They are weighted
# roughly equally as pairs, because a confident-looking result from a vague request is the
# error being guarded against.
WEIGHTS = {
    "retrieval": 0.25,
    "specificity": 0.25,
    "margin": 0.30,
    "constraints": 0.20,
}

# Profile fields that count as the user (or a note) having actually specified something.
# `k`, `mode` and `arc` are excluded: they always have a default, so counting them would make
# every profile look specified.
SPECIFICITY_FIELDS = (
    "genre",
    "mood",
    "energy",
    "tempo_bpm",
    "mood_tags",
    "likes_acoustic",
    "language",
    "decade",
    "total_minutes",
)

# A top score around this value means the catalog had a genuinely strong answer. Derived from
# the `balanced` weights in `src/recommender.py`: genre 2.0 + mood 1.0 + tags 1.2 + energy 1.5
# is about 5.7 before the optional terms, so 5.0 is a demanding but reachable bar.
STRONG_SCORE = 5.0

BANDS = ((0.70, "high"), (0.45, "medium"), (0.0, "low"))


@dataclass
class ConfidenceReport:
    """A confidence value, its band, and the components that produced it."""

    value: float
    band: str
    components: Dict[str, float] = field(default_factory=dict)
    per_song: Dict[int, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "value": self.value,
            "band": self.band,
            "components": self.components,
            "per_song": self.per_song,
            "notes": self.notes,
        }


def _band(value: float) -> str:
    for threshold, name in BANDS:
        if value >= threshold:
            return name
    return "low"


def specificity(profile: Dict) -> float:
    """Fraction of the meaningful profile fields that carry a value."""
    present = sum(1 for key in SPECIFICITY_FIELDS if profile.get(key) not in (None, "", []))
    return round(present / len(SPECIFICITY_FIELDS), 3)


def margin(picks: List, runner_up_score: Optional[float] = None) -> float:
    """How decisively the chosen songs beat the alternatives.

    Two things matter and are averaged: whether the top pick scored well in absolute terms
    (a weak best answer is a weak answer however it ranks), and whether there was a real gap
    between the last song taken and the best song left behind. A playlist where the 5th pick
    and the 6th candidate are tied was effectively chosen by the tie-breaker.
    """
    if not picks:
        return 0.0
    scores = [score for _, score, _ in picks]
    top = max(scores)
    absolute = max(0.0, min(1.0, top / STRONG_SCORE))

    if runner_up_score is None or top <= 0:
        separation = absolute
    else:
        gap = min(scores) - runner_up_score
        # A gap of a full point is decisive; zero or negative means the cut was arbitrary.
        separation = max(0.0, min(1.0, gap / 1.0))

    return round((absolute + separation) / 2, 3)


def constraint_health(failures: List, iterations: int = 1) -> float:
    """1.0 for a playlist that passed every check first time, falling as repairs pile up.

    Unresolved failures cost much more than repaired ones: a run that needed three attempts
    but ended clean is a working system, while a run that ends with a failure still standing
    is returning something it knows is wrong.
    """
    health = 1.0 - 0.3 * len(failures)
    health -= 0.05 * max(0, iterations - 1)
    return round(max(0.0, min(1.0, health)), 3)


def score_run(
    retrieval_strength: float,
    profile: Dict,
    picks: List,
    failures: Optional[List] = None,
    iterations: int = 1,
    runner_up_score: Optional[float] = None,
    degraded: bool = False,
) -> ConfidenceReport:
    """Combines the four components into one published confidence."""
    failures = failures or []
    components = {
        "retrieval": round(float(retrieval_strength or 0.0), 3),
        "specificity": specificity(profile),
        "margin": margin(picks, runner_up_score),
        "constraints": constraint_health(failures, iterations),
    }

    value = sum(components[key] * weight for key, weight in WEIGHTS.items())

    notes: List[str] = []
    if degraded:
        # The offline planner is capable but blunter than the model, so a degraded run should
        # not report the same confidence as a clean one.
        value *= 0.9
        notes.append("planner degraded to the offline backend; confidence reduced by 10%")
    if components["retrieval"] < 0.2:
        notes.append("no listening note matched this request, so the profile is mostly defaults")
    if components["specificity"] < 0.25:
        notes.append("the request specified very little, so the ranking rests on default weights")
    if failures:
        notes.append(f"{len(failures)} constraint(s) could not be satisfied")
    if not picks:
        notes.append("no song scored above zero")
        value = 0.0

    value = round(max(0.0, min(1.0, value)), 3)

    per_song: Dict[int, float] = {}
    if picks:
        top = max(score for _, score, _ in picks) or 1.0
        for song, score, _ in picks:
            share = max(0.0, score) / top if top > 0 else 0.0
            per_song[int(song["id"])] = round(min(1.0, share) * value, 3)

    return ConfidenceReport(
        value=value,
        band=_band(value),
        components=components,
        per_song=per_song,
        notes=notes,
    )
