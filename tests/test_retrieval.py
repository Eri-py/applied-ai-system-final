"""Tests for the retrieval layer: note parsing, BM25 ranking and hint merging."""

import pytest

from src.retrieval import (
    HINT_FLOOR_RATIO,
    Hit,
    Note,
    NoteRetriever,
    load_notes,
    merge_hints,
    parse_note,
    tokenize,
)


@pytest.fixture(scope="module")
def retriever():
    return NoteRetriever(load_notes())


# --- frontmatter parsing ---------------------------------------------------------------


def test_parse_note_reads_frontmatter_and_body():
    note = parse_note(
        "---\n"
        "id: demo\n"
        "title: A demo note\n"
        "kind: context\n"
        "keywords: alpha, beta gamma\n"
        "hints:\n"
        "  mood: chill\n"
        "  energy: 0.35\n"
        "  tempo_bpm: 78\n"
        "  likes_acoustic: true\n"
        "  mood_tags: rainy, cosy\n"
        "---\n"
        "The body text.\n"
    )
    assert note.id == "demo"
    assert note.title == "A demo note"
    assert note.kind == "context"
    assert note.keywords == ["alpha", "beta gamma"]
    assert note.body.strip() == "The body text."
    assert note.hints == {
        "mood": "chill",
        "energy": 0.35,
        "tempo_bpm": 78,
        "likes_acoustic": True,
        "mood_tags": ["rainy", "cosy"],
    }


def test_parse_note_coerces_hint_types():
    """Energy must be a float and tempo an int, or the scoring layer gets strings."""
    note = parse_note("---\nid: x\nhints:\n  energy: 0.9\n  tempo_bpm: 145\n---\nbody")
    assert isinstance(note.hints["energy"], float)
    assert isinstance(note.hints["tempo_bpm"], int)


def test_parse_note_without_frontmatter_still_retrieves():
    """A malformed note is degraded, not fatal: no hints, but the prose is still searchable."""
    note = parse_note("just some prose about sleep and tempo")
    assert note.hints == {}
    assert "sleep" in note.body


def test_parse_note_ignores_unparseable_numeric_hint():
    note = parse_note("---\nid: x\nhints:\n  energy: not-a-number\n---\nbody")
    assert "energy" not in note.hints


# --- tokenizing ------------------------------------------------------------------------


def test_tokenize_drops_stopwords_and_single_characters():
    assert tokenize("I want a song for the gym") == ["song", "gym"]


def test_tokenize_keeps_rnb_as_one_term():
    """`r&b` is a catalog genre and must not be split into two discarded letters."""
    assert "rnb" in tokenize("some r&b please")


# --- ranking ---------------------------------------------------------------------------


def test_corpus_loads():
    notes = load_notes()
    assert len(notes) >= 10
    assert all(isinstance(note, Note) for note in notes)
    assert all(note.id for note in notes)


@pytest.mark.parametrize(
    "query,expected_note",
    [
        ("something for the gym", "context-workout"),
        ("i need to focus while coding", "context-focus"),
        ("help me get to sleep", "context-sleep"),
        ("a playlist for a house party", "context-party"),
        ("my girlfriend dumped me", "context-heartbreak"),
        ("night drive on the motorway", "context-commute"),
        ("rainy sunday indoors", "context-rainy-day"),
        ("play me something good", "theory-cold-start"),
    ],
)
def test_retrieval_finds_the_right_note(retriever, query, expected_note):
    """The whole system rests on this: the right note must rank first."""
    hits = retriever.search(query, k=3)
    assert hits, f"no hits for {query!r}"
    assert hits[0].id == expected_note


def test_search_is_deterministic(retriever):
    first = [hit.id for hit in retriever.search("quiet acoustic evening", k=3)]
    second = [hit.id for hit in retriever.search("quiet acoustic evening", k=3)]
    assert first == second


def test_search_returns_nothing_for_an_unmatched_query(retriever):
    assert retriever.search("zzzz qqqq xxxx", k=3) == []


def test_search_on_empty_query_is_empty(retriever):
    assert retriever.search("", k=3) == []
    assert retriever.search("   ", k=3) == []


def test_strength_is_zero_without_hits(retriever):
    assert retriever.strength([]) == 0.0


def test_strength_is_higher_for_a_direct_match(retriever):
    direct = retriever.strength(retriever.search("gym workout training", k=3))
    vague = retriever.strength(retriever.search("music", k=3))
    assert direct > vague


# --- hint merging ----------------------------------------------------------------------


def test_merge_hints_prefers_the_top_hit(retriever):
    """A specific context note must not have its numbers averaged away by a genre note."""
    hits = retriever.search("something for the gym", k=3)
    merged = merge_hints(hits)
    assert merged["mood"] == "intense"
    assert merged["energy"] == pytest.approx(0.9)
    assert merged["likes_acoustic"] is False


def test_merge_hints_records_provenance(retriever):
    merged = merge_hints(retriever.search("help me sleep", k=3))
    assert merged["_provenance"]["energy"] == "context-sleep"


def test_merge_hints_ignores_weak_tail_hits():
    """The floor is what stops a faint keyword collision injecting invented precision."""
    strong = Note(id="strong", title="strong", kind="context", keywords=[], hints={"mode": "balanced"}, body="")
    weak = Note(
        id="weak",
        title="weak",
        kind="context",
        keywords=[],
        hints={"energy": 0.4, "language": "instrumental"},
        body="",
    )
    hits = [Hit(note=strong, score=10.0), Hit(note=weak, score=10.0 * HINT_FLOOR_RATIO / 2)]
    merged = merge_hints(hits)
    assert merged["mode"] == "balanced"
    assert "energy" not in merged
    assert "language" not in merged


def test_merge_hints_includes_tail_hits_above_the_floor():
    strong = Note(id="strong", title="s", kind="context", keywords=[], hints={"mode": "balanced"}, body="")
    near = Note(id="near", title="n", kind="context", keywords=[], hints={"energy": 0.4}, body="")
    hits = [Hit(note=strong, score=10.0), Hit(note=near, score=9.0)]
    assert merge_hints(hits)["energy"] == pytest.approx(0.4)


def test_merge_hints_on_no_hits_is_empty():
    assert merge_hints([]) == {}


def test_vague_request_inherits_no_numeric_targets(retriever):
    """Regression: 'play me something good' used to pick up the focus note's 0.40 energy."""
    merged = merge_hints(retriever.search("play me something good", k=3))
    assert "energy" not in merged
    assert "language" not in merged
