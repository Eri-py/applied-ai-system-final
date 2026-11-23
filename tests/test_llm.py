"""Tests for the language layer: the offline planner, the Claude request shape, and fallback.

The `ClaudeBackend` tests use a fake client rather than the network. They cannot prove the
live API accepts the request -- that needs a key -- but they do pin down everything this
repository is responsible for: the model id, the structured-output schema, which fields are
sent, how a refusal is handled, and that any failure degrades instead of crashing.
"""

import json
from types import SimpleNamespace

import pytest

from src.llm import (
    CLAUDE_MODEL,
    ClaudeBackend,
    OfflineBackend,
    PROFILE_SCHEMA,
    ResilientBackend,
    build_backend,
    offline_forced,
)
from src.recommender import load_songs
from src.retrieval import NoteRetriever, load_notes


@pytest.fixture(scope="module")
def retriever():
    return NoteRetriever(load_notes())


@pytest.fixture(scope="module")
def songs():
    return load_songs()


@pytest.fixture
def planner():
    return OfflineBackend()


def plan_for(planner, retriever, request, k=3):
    return planner.plan(request, retriever.search(request, k=k))


# --- the offline planner ---------------------------------------------------------------


@pytest.mark.parametrize(
    "request_text,field,expected",
    [
        ("something for the gym", "energy", 0.9),
        ("something for the gym", "mood", "intense"),
        ("help me get to sleep", "energy", 0.22),
        ("i need to focus", "language", "instrumental"),
        ("a house party playlist", "mood", "energetic"),
        ("my girlfriend dumped me", "mood", "melancholy"),
    ],
)
def test_planner_takes_targets_from_the_retrieved_notes(planner, retriever, request_text, field, expected):
    """The hints in the notes are the planner's source of numeric targets."""
    assert plan_for(planner, retriever, request_text).profile[field] == expected


@pytest.mark.parametrize(
    "request_text,field,expected",
    [
        ("some lo-fi for studying", "genre", "lofi"),
        ("play me drum and bass", "genre", "drum and bass"),
        ("some bedroom pop", "genre", "bedroom pop"),
        ("give me r&b", "genre", "r&b"),
        ("techno for the gym", "genre", "house"),
        ("rap for the commute", "genre", "hip hop"),
    ],
)
def test_planner_maps_genre_synonyms(planner, retriever, request_text, field, expected):
    assert plan_for(planner, retriever, request_text).profile[field] == expected


def test_planner_prefers_the_longer_genre_name(planner, retriever):
    """'bedroom pop' must not be read as 'pop'."""
    assert plan_for(planner, retriever, "bedroom pop please").profile["genre"] == "bedroom pop"


def test_request_overrides_the_note_hint(planner, retriever):
    """An explicit word in the request beats the note's default."""
    plan = plan_for(planner, retriever, "very quiet music for the gym")
    assert plan.profile["energy"] == 0.15


@pytest.mark.parametrize(
    "request_text,expected_k",
    [
        ("4 songs for the gym", 4),
        ("three upbeat spanish songs", 3),
        ("give me seven tracks", 7),
        ("ten really quiet instrumental songs", 10),
    ],
)
def test_planner_reads_a_song_count(planner, retriever, request_text, expected_k):
    assert plan_for(planner, retriever, request_text).profile["k"] == expected_k


@pytest.mark.parametrize(
    "request_text,minutes",
    [
        ("30 minutes of lofi", 30),
        ("half an hour of jazz", 30),
        ("an hour of ambient", 60),
        ("45 mins for the gym", 45),
    ],
)
def test_planner_reads_a_running_time(planner, retriever, request_text, minutes):
    assert plan_for(planner, retriever, request_text).profile["total_minutes"] == minutes


@pytest.mark.parametrize(
    "request_text,decade",
    [("some 90s rock", 1990), ("music from the 2000s", 2000), ("1980s synthwave", 1980)],
)
def test_planner_reads_a_decade(planner, retriever, request_text, decade):
    assert plan_for(planner, retriever, request_text).profile["decade"] == decade


def test_planner_reads_a_tempo(planner, retriever):
    assert plan_for(planner, retriever, "house at 128 bpm").profile["tempo_bpm"] == 128


def test_planner_reads_acoustic_preference(planner, retriever):
    assert plan_for(planner, retriever, "acoustic songs").profile["likes_acoustic"] is True
    assert plan_for(planner, retriever, "electronic songs").profile["likes_acoustic"] is False


def test_planner_reads_an_arc(planner, retriever):
    assert plan_for(planner, retriever, "lofi to wind down").profile["arc"] == "descend"


def test_planner_reads_discovery_intent(planner, retriever):
    assert plan_for(planner, retriever, "something obscure").profile["mode"] == "discovery"


def test_planner_records_where_every_field_came_from(planner, retriever):
    """Provenance is what makes `--verbose` able to explain the profile."""
    sources = plan_for(planner, retriever, "4 songs for the gym").profile["_sources"]
    assert sources["energy"].startswith("note:")
    assert sources["k"].startswith("request:")


def test_planner_is_deterministic(planner, retriever):
    first = plan_for(planner, retriever, "something gentle for a rainy sunday")
    second = plan_for(planner, retriever, "something gentle for a rainy sunday")
    assert first.profile == second.profile
    assert first.rationale == second.rationale


def test_planner_with_no_hits_explains_itself(planner):
    plan = planner.plan("zzz qqq", [])
    assert "No listening note matched" in plan.rationale


def test_planner_narrates_without_inventing_a_song(planner, songs):
    picks = [(songs[0], 4.0, "genre match: pop (+2.00)")]
    text, _ = planner.narrate("pop please", {"genre": "pop"}, picks, 0.8)
    assert songs[0]["title"] in text
    assert songs[1]["title"] not in text


def test_planner_narration_flags_low_confidence(planner, songs):
    picks = [(songs[0], 1.0, "weak")]
    text, _ = planner.narrate("anything", {}, picks, 0.2)
    assert "low" in text.lower()


def test_planner_narration_handles_an_empty_playlist(planner):
    text, _ = planner.narrate("x", {}, [], 0.0)
    assert "no song" in text.lower()


# --- the Claude request shape -----------------------------------------------------------


class FakeMessages:
    """Captures the request and returns a canned response."""

    def __init__(self, payload, stop_reason="end_turn"):
        self.payload = payload
        self.stop_reason = stop_reason
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason=self.stop_reason,
            stop_details=None,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=0),
        )


class FakeClient:
    def __init__(self, payload, stop_reason="end_turn", beta_fails=False):
        self.messages = FakeMessages(payload, stop_reason)
        # The beta endpoint is tried first (for refusal fallbacks); some deployments reject it.
        if beta_fails:
            class Rejecting:
                def create(self, **kwargs):
                    raise _BadRequest("beta not enabled")

            self.beta = SimpleNamespace(messages=Rejecting())
        else:
            self.beta = SimpleNamespace(messages=self.messages)


class _BadRequest(Exception):
    pass


_BadRequest.__name__ = "BadRequestError"


VALID_PROFILE = {
    "genre": "lofi",
    "mood": "chill",
    "energy": 0.35,
    "tempo_bpm": 78,
    "mood_tags": ["rainy"],
    "likes_acoustic": True,
    "language": None,
    "decade": None,
    "k": 5,
    "total_minutes": None,
    "mode": "mood_first",
    "arc": "flat",
    "rationale": "The rainy-day note sets a low energy and acoustic texture.",
}


def test_schema_requires_every_field_and_forbids_extras():
    """Structured output only guarantees anything if the schema is closed."""
    assert PROFILE_SCHEMA["additionalProperties"] is False
    assert set(PROFILE_SCHEMA["required"]) == set(PROFILE_SCHEMA["properties"])


def test_schema_allows_null_for_unstated_fields():
    """A planner forced to fill every field will invent a decade."""
    for field in ("genre", "mood", "energy", "language", "decade"):
        assert "null" in PROFILE_SCHEMA["properties"][field]["type"]


def test_claude_plan_sends_the_expected_request(retriever):
    client = FakeClient(VALID_PROFILE)
    backend = ClaudeBackend(client=client)
    hits = retriever.search("rainy sunday", k=2)
    plan = backend.plan("rainy sunday", hits)

    sent = client.messages.calls[0]
    assert sent["model"] == CLAUDE_MODEL == "claude-opus-5-5"
    assert sent["output_config"]["format"]["schema"] is PROFILE_SCHEMA
    assert sent["output_config"]["effort"] == "low"
    assert "rainy sunday" in sent["messages"][0]["content"]
    # The retrieved note prose must actually reach the model, or it is not grounding.
    assert "context-rainy-day" in sent["messages"][0]["content"]
    assert plan.backend == "claude"
    assert plan.profile["genre"] == "lofi"
    assert plan.rationale.startswith("The rainy-day note")
    assert plan.usage["input_tokens"] == 100


def test_claude_plan_drops_null_fields(retriever):
    backend = ClaudeBackend(client=FakeClient(VALID_PROFILE))
    profile = backend.plan("x", []).profile
    assert "language" not in profile
    assert "decade" not in profile


def test_claude_plan_raises_on_a_refusal(retriever):
    backend = ClaudeBackend(client=FakeClient(VALID_PROFILE, stop_reason="refusal"))
    with pytest.raises(RuntimeError, match="refused"):
        backend.plan("x", [])


def test_claude_retries_without_the_fallback_beta_if_it_is_rejected(retriever):
    """An unavailable reliability feature must not cost the user their playlist."""
    client = FakeClient(VALID_PROFILE, beta_fails=True)
    backend = ClaudeBackend(client=client)
    plan = backend.plan("x", [])
    assert plan.profile["genre"] == "lofi"
    assert client.messages.calls, "it must fall through to the non-beta endpoint"


def test_claude_narrate_sends_the_songs_and_their_reasons(songs):
    client = FakeClient("A short paragraph.")
    backend = ClaudeBackend(client=client)
    picks = [(songs[0], 4.0, "genre match: pop (+2.00)")]
    text, plan = backend.narrate("pop", {"genre": "pop"}, picks, 0.8)

    sent = client.messages.calls[0]["messages"][0]["content"]
    assert songs[0]["title"] in sent
    assert "genre match: pop" in sent
    assert text == "A short paragraph."
    assert plan.backend == "claude"


# --- fallback behaviour -----------------------------------------------------------------


class ExplodingBackend:
    name = "claude"
    model = CLAUDE_MODEL

    def plan(self, request, hits):
        raise ConnectionError("network down")

    def narrate(self, request, profile, picks, confidence):
        raise ConnectionError("network down")


def test_resilient_backend_degrades_on_failure(retriever):
    backend = ResilientBackend(primary=ExplodingBackend(), fallback=OfflineBackend())
    plan = backend.plan("music for the gym", retriever.search("music for the gym", k=3))
    assert plan.degraded
    assert "ConnectionError" in plan.degrade_reason
    assert plan.profile["mood"] == "intense", "the fallback must still produce a real profile"


def test_resilient_backend_degrades_on_narrate_failure(songs):
    backend = ResilientBackend(primary=ExplodingBackend(), fallback=OfflineBackend())
    text, plan = backend.narrate("x", {"genre": "pop"}, [(songs[0], 4.0, "reason")], 0.8)
    assert plan.degraded
    assert text


def test_resilient_backend_logs_the_degradation(retriever):
    class Recorder:
        def __init__(self):
            self.events = []

        def event(self, kind, **payload):
            self.events.append((kind, payload))

    recorder = Recorder()
    ResilientBackend(primary=ExplodingBackend(), fallback=OfflineBackend(), logger=recorder).plan("x", [])
    assert any(kind == "backend_degraded" for kind, _ in recorder.events)


def test_resilient_backend_without_a_primary_uses_the_fallback_directly(retriever):
    plan = ResilientBackend(primary=None, fallback=OfflineBackend()).plan("gym", [])
    assert not plan.degraded
    assert plan.backend == "offline"


def test_build_backend_respects_forced_offline(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    backend, detail = build_backend(force_offline=True)
    assert backend.primary is None
    assert "offline" in detail


def test_build_backend_goes_offline_without_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    backend, detail = build_backend()
    assert backend.primary is None
    assert "offline" in detail


def test_offline_forced_env_var(monkeypatch):
    monkeypatch.setenv("VIBEFINDER_OFFLINE", "1")
    assert offline_forced()
    monkeypatch.setenv("VIBEFINDER_OFFLINE", "")
    assert not offline_forced()
