"""Tests for the confidence model: components, bands and the published value."""

import pytest

from src.agent import Failure
from src.confidence import (
    WEIGHTS,
    constraint_health,
    margin,
    score_run,
    specificity,
)
from src.recommender import load_songs


@pytest.fixture(scope="module")
def songs():
    return load_songs()


def picks_of(songs, *scores):
    return [(songs[index], score, "test") for index, score in enumerate(scores)]


# --- components ------------------------------------------------------------------------


def test_specificity_counts_only_meaningful_fields():
    """`k`, `mode` and `arc` always have defaults, so counting them would inflate every run."""
    assert specificity({"k": 5, "mode": "balanced", "arc": "flat"}) == 0.0
    assert specificity({"genre": "pop"}) > 0.0


def test_specificity_rises_with_a_fuller_profile():
    thin = specificity({"genre": "pop"})
    full = specificity(
        {
            "genre": "pop",
            "mood": "happy",
            "energy": 0.8,
            "tempo_bpm": 120,
            "mood_tags": ["sunny"],
            "likes_acoustic": False,
        }
    )
    assert full > thin


def test_specificity_ignores_empty_values():
    assert specificity({"genre": "", "mood": None, "mood_tags": []}) == 0.0


def test_margin_is_zero_without_picks():
    assert margin([]) == 0.0


def test_margin_rewards_a_high_top_score(songs):
    assert margin(picks_of(songs, 5.0)) > margin(picks_of(songs, 1.0))


def test_margin_falls_when_the_cut_was_arbitrary(songs):
    """If the last pick ties the best song left behind, the tie-breaker chose the playlist."""
    decisive = margin(picks_of(songs, 5.0, 4.0), runner_up_score=1.0)
    arbitrary = margin(picks_of(songs, 5.0, 4.0), runner_up_score=4.0)
    assert decisive > arbitrary


def test_constraint_health_is_perfect_for_a_clean_first_attempt():
    assert constraint_health([], iterations=1) == 1.0


def test_constraint_health_penalises_unresolved_failures():
    assert constraint_health([Failure("x", "y")]) < 1.0
    assert constraint_health([Failure("x", "y"), Failure("z", "w")]) < constraint_health([Failure("x", "y")])


def test_constraint_health_penalises_extra_iterations():
    assert constraint_health([], iterations=4) < constraint_health([], iterations=1)


def test_constraint_health_never_goes_negative():
    assert constraint_health([Failure(str(i), "x") for i in range(20)]) == 0.0


# --- the combined score ----------------------------------------------------------------


def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_a_strong_run_scores_high(songs):
    report = score_run(
        retrieval_strength=1.0,
        profile={
            "genre": "lofi",
            "mood": "chill",
            "energy": 0.35,
            "tempo_bpm": 78,
            "mood_tags": ["rainy"],
            "likes_acoustic": True,
        },
        picks=picks_of(songs, 6.0, 5.0, 4.0),
        failures=[],
        iterations=1,
        runner_up_score=1.0,
    )
    assert report.value > 0.7
    assert report.band == "high"


def test_a_thin_run_scores_low(songs):
    report = score_run(
        retrieval_strength=0.0,
        profile={"k": 5, "mode": "balanced"},
        picks=picks_of(songs, 0.0, 0.0),
        failures=[],
        iterations=1,
    )
    assert report.value < 0.45
    assert report.band == "low"
    assert any("default" in note for note in report.notes)


def test_no_picks_means_zero_confidence(songs):
    report = score_run(retrieval_strength=1.0, profile={"genre": "pop"}, picks=[])
    assert report.value == 0.0
    assert any("no song scored" in note for note in report.notes)


def test_degraded_run_is_discounted_and_says_so(songs):
    arguments = dict(
        retrieval_strength=1.0,
        profile={"genre": "lofi", "mood": "chill", "energy": 0.4},
        picks=picks_of(songs, 5.0, 4.0),
        failures=[],
        iterations=1,
        runner_up_score=1.0,
    )
    clean = score_run(**arguments)
    degraded = score_run(**arguments, degraded=True)
    assert degraded.value < clean.value
    assert any("degraded" in note for note in degraded.notes)


def test_unresolved_failures_are_reported_in_the_notes(songs):
    report = score_run(
        retrieval_strength=0.8,
        profile={"genre": "pop"},
        picks=picks_of(songs, 3.0),
        failures=[Failure("size_short", "asked for 5, got 1")],
    )
    assert any("constraint" in note for note in report.notes)


def test_value_is_always_in_range(songs):
    for strength in (0.0, 0.5, 1.0):
        for failures in ([], [Failure("a", "b")] * 5):
            report = score_run(
                retrieval_strength=strength,
                profile={"genre": "pop", "mood": "happy"},
                picks=picks_of(songs, 9.0, 8.0),
                failures=failures,
            )
            assert 0.0 <= report.value <= 1.0


def test_per_song_confidence_tracks_the_score_order(songs):
    report = score_run(
        retrieval_strength=1.0,
        profile={"genre": "lofi", "mood": "chill"},
        picks=picks_of(songs, 6.0, 3.0, 1.0),
        runner_up_score=0.5,
    )
    values = [report.per_song[int(songs[i]["id"])] for i in range(3)]
    assert values == sorted(values, reverse=True)
    assert all(0.0 <= value <= 1.0 for value in values)


def test_report_serialises(songs):
    report = score_run(retrieval_strength=0.5, profile={"genre": "pop"}, picks=picks_of(songs, 3.0))
    data = report.as_dict()
    assert set(data) == {"value", "band", "components", "per_song", "notes"}
    assert set(data["components"]) == set(WEIGHTS)
