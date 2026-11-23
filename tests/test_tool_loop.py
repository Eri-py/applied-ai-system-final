"""Tests for the model-driven tool loop, using a scripted fake client.

These cover the half of `--tool-loop` this repository owns: tool dispatch, `tool_result`
pairing, the "only real song ids" guardrail, error handling and the iteration cap. They do
not and cannot cover the live API's behaviour, which needs a key -- see EVALUATION.md for
what was and was not verified.
"""

import json
from types import SimpleNamespace

import pytest

from src.agent import ToolBox
from src.obs import RunLogger
from src.recommender import load_songs
from src.retrieval import NoteRetriever, load_notes
from src.tool_loop import TOOLS, run_tool_loop


@pytest.fixture(scope="module")
def songs():
    return load_songs()


@pytest.fixture(scope="module")
def retriever():
    return NoteRetriever(load_notes())


@pytest.fixture
def logger(tmp_path):
    return RunLogger(run_id="tool-loop-test", log_dir=tmp_path, enabled=True)


@pytest.fixture
def tools(songs, retriever, logger):
    return ToolBox(songs, retriever, logger)


def tool_use(name, payload, block_id=None):
    return SimpleNamespace(
        type="tool_use",
        name=name,
        input=payload,
        id=block_id or f"toolu_{name}",
    )


def turn(blocks, stop_reason="tool_use"):
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        stop_details=None,
        usage=SimpleNamespace(input_tokens=50, output_tokens=10),
    )


class ScriptedClient:
    """Replays a list of prepared assistant turns, recording what it was sent."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self._turns:
            return turn([SimpleNamespace(type="text", text="done")], stop_reason="end_turn")
        return self._turns.pop(0)


class FailingClient:
    def __init__(self):
        self.messages = self

    def create(self, **kwargs):
        raise ConnectionError("network down")


# --- tool definitions -------------------------------------------------------------------


def test_the_four_tools_are_declared():
    assert {tool["name"] for tool in TOOLS} == {"retrieve_notes", "recommend", "validate", "finalize"}


def test_every_tool_schema_is_closed():
    """An open schema lets the model pass fields the dispatcher silently ignores."""
    for tool in TOOLS:
        assert tool["input_schema"]["additionalProperties"] is False
        assert tool["input_schema"]["required"]
        assert tool["description"]


# --- a full, well-behaved run ------------------------------------------------------------


def test_a_complete_loop_finalizes_a_playlist(tools, logger):
    lofi_ids = [2, 4, 9]
    client = ScriptedClient(
        [
            turn([tool_use("retrieve_notes", {"query": "lofi to study to", "k": 2})]),
            turn([tool_use("recommend", {"profile": {"genre": "lofi", "mood": "chill"}, "k": 3})]),
            turn([tool_use("validate", {"song_ids": lofi_ids, "profile": {"genre": "lofi"}, "k": 3})]),
            turn(
                [
                    tool_use(
                        "finalize",
                        {"song_ids": lofi_ids, "explanation": "Three quiet lofi tracks."},
                    )
                ]
            ),
        ]
    )

    result = run_tool_loop("lofi to study to", tools, client=client, logger=logger)

    assert result.finalized
    assert result.stopped_because == "finalized"
    assert result.tool_calls == ["retrieve_notes", "recommend", "validate", "finalize"]
    assert result.explanation == "Three quiet lofi tracks."
    assert result.picks, "the finalized playlist must carry real catalog rows"
    assert all(isinstance(score, float) for _, score, _ in result.picks)
    assert result.usage["input_tokens"] == 200


def test_the_loop_sends_tool_results_back_in_one_user_message(tools, logger):
    client = ScriptedClient(
        [turn([tool_use("recommend", {"profile": {"genre": "lofi"}, "k": 2})])]
    )
    run_tool_loop("lofi", tools, client=client, logger=logger)

    # Second request carries: the user request, the assistant turn, then one user message
    # holding every tool_result. Splitting them trains the model out of parallel calls.
    messages = client.requests[1]["messages"]
    assert messages[-1]["role"] == "user"
    assert all(block["type"] == "tool_result" for block in messages[-1]["content"])


def test_tool_results_carry_the_matching_tool_use_id(tools, logger):
    client = ScriptedClient(
        [turn([tool_use("catalog_check", {}, block_id="toolu_specific")])]
    )
    run_tool_loop("x", tools, client=client, logger=logger)
    result_block = client.requests[1]["messages"][-1]["content"][0]
    assert result_block["tool_use_id"] == "toolu_specific"


def test_the_request_declares_the_tools_and_the_model(tools, logger):
    from src.llm import CLAUDE_MODEL

    client = ScriptedClient([turn([SimpleNamespace(type="text", text="hi")], stop_reason="end_turn")])
    run_tool_loop("x", tools, client=client, logger=logger)
    sent = client.requests[0]
    assert sent["model"] == CLAUDE_MODEL
    assert sent["tools"] is TOOLS
    assert "retrieve_notes" in sent["system"]


def test_parallel_tool_calls_in_one_turn_are_all_executed(tools, logger):
    client = ScriptedClient(
        [
            turn(
                [
                    tool_use("retrieve_notes", {"query": "gym"}, block_id="a"),
                    tool_use("recommend", {"profile": {"genre": "rock"}, "k": 2}, block_id="b"),
                ]
            )
        ]
    )
    result = run_tool_loop("gym", tools, client=client, logger=logger)
    assert result.tool_calls == ["retrieve_notes", "recommend"]
    assert len(client.requests[1]["messages"][-1]["content"]) == 2


# --- the guardrail against invented songs ------------------------------------------------


def test_finalize_rejects_a_song_id_recommend_never_returned(tools, logger):
    """The guardrail against a hallucinated track reaching the user."""
    client = ScriptedClient(
        [
            turn([tool_use("recommend", {"profile": {"genre": "lofi"}, "k": 2})]),
            turn([tool_use("finalize", {"song_ids": [2, 9999], "explanation": "x"})]),
        ]
    )
    result = run_tool_loop("lofi", tools, client=client, logger=logger)
    shipped = [int(song["id"]) for song, _, _ in result.picks]
    assert 9999 not in shipped
    assert any("9999" in error for error in result.errors)


def test_validate_reports_an_unknown_song_id(tools, logger):
    client = ScriptedClient(
        [
            turn([tool_use("recommend", {"profile": {"genre": "lofi"}, "k": 2})]),
            turn([tool_use("validate", {"song_ids": [4242], "profile": {}, "k": 1})]),
        ]
    )
    run_tool_loop("lofi", tools, client=client, logger=logger)
    payload = json.loads(client.requests[2]["messages"][-1]["content"][0]["content"])
    assert payload["ok"] is False
    assert any(failure["code"] == "unknown_song" for failure in payload["failures"])


def test_recommend_clamps_whatever_profile_the_model_sends(tools, logger):
    client = ScriptedClient(
        [turn([tool_use("recommend", {"profile": {"energy": 7.5, "mode": "telepathy"}, "k": 99})])]
    )
    run_tool_loop("x", tools, client=client, logger=logger)
    payload = json.loads(client.requests[1]["messages"][-1]["content"][0]["content"])
    assert payload["clamped"], "out-of-range values must be reported back to the model"
    assert len(payload["songs"]) <= 10


# --- failure handling --------------------------------------------------------------------


def test_an_api_error_ends_the_loop_without_raising(tools, logger):
    result = run_tool_loop("x", tools, client=FailingClient(), logger=logger)
    assert not result.finalized
    assert "api_error" in result.stopped_because
    assert result.errors


def test_a_refusal_ends_the_loop(tools, logger):
    client = ScriptedClient([turn([SimpleNamespace(type="text", text="")], stop_reason="refusal")])
    result = run_tool_loop("x", tools, client=client, logger=logger)
    assert result.stopped_because == "refusal"
    assert not result.finalized


def test_a_paused_turn_is_resumed(tools, logger):
    client = ScriptedClient(
        [
            turn([SimpleNamespace(type="text", text="thinking")], stop_reason="pause_turn"),
            turn([tool_use("finalize", {"song_ids": [], "explanation": "none"})]),
        ]
    )
    result = run_tool_loop("x", tools, client=client, logger=logger)
    assert result.iterations == 2


def test_a_model_that_stops_without_finalizing_is_reported(tools, logger):
    client = ScriptedClient([turn([SimpleNamespace(type="text", text="I give up")], stop_reason="end_turn")])
    result = run_tool_loop("x", tools, client=client, logger=logger)
    assert not result.finalized
    assert "without finalizing" in result.stopped_because


def test_an_unknown_tool_name_is_reported_to_the_model(tools, logger):
    client = ScriptedClient([turn([tool_use("make_coffee", {})])])
    run_tool_loop("x", tools, client=client, logger=logger)
    payload = json.loads(client.requests[1]["messages"][-1]["content"][0]["content"])
    assert "unknown tool" in payload["error"]


def test_the_loop_respects_the_iteration_cap(tools, logger):
    """A model that never finalizes must still terminate."""
    forever = [turn([tool_use("catalog_stats", {})]) for _ in range(50)]
    result = run_tool_loop("x", tools, client=ScriptedClient(forever), logger=logger, max_iterations=3)
    assert result.iterations == 3
    assert "iteration_limit" in result.stopped_because


def test_every_tool_call_is_logged(tools, logger):
    client = ScriptedClient([turn([tool_use("retrieve_notes", {"query": "gym"})])])
    run_tool_loop("gym", tools, client=client, logger=logger)
    assert [event["tool"] for event in logger.by_kind("tool_loop_call")] == ["retrieve_notes"]
