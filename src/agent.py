"""The agent: plan, act, check its own work, repair, and report.

This is the component that turns the Module 3 recommender from a scoring function into a
system. The loop is four steps:

1. **Plan** -- retrieve listening notes for the request, hand them plus the request to the
   language layer, and clamp the profile it proposes into legal ranges.
2. **Act** -- call the recommender tool to build a candidate playlist.
3. **Check** -- run the critic: a set of constraints the playlist must satisfy that no single
   song score can express (no repeated artist, no song outside the energy window, total
   running time near what was asked for, the energy arc in the right shape).
4. **Repair** -- for each failure, take the specific corrective action registered for it, and
   go back to step 2. Bounded, so a constraint that cannot be satisfied ends the loop with the
   failure reported rather than looping forever.

Two deliberate design choices:

- **The loop is Python, not a model.** Steps 2-4 are deterministic, which is what makes the
  repairs testable and the runs reproducible. The model is used where language is genuinely
  the hard part (step 1) and nowhere else. A model-driven version of the same loop is in
  `src/tool_loop.py` for comparison.
- **The critic is separate from the scorer.** `score_song` judges one song alone and cannot
  see "three songs by the same artist" or "this list ends louder than it starts". Those are
  properties of the set, so they need their own check, and that check is where most real
  playlist failures live.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from src import confidence as confidence_mod
from src.guardrails import (
    GuardrailVerdict,
    check_request,
    clamp_profile,
    off_domain_verdict,
    sanitise_text,
)
from src.llm import build_backend
from src.obs import RunLogger, logging_enabled, new_run_id
from src.recommender import get_mode, load_songs, recommend_songs
from src.retrieval import DEFAULT_NOTES_DIR, Hit, NoteRetriever, load_notes

MAX_ITERATIONS = 5

# How far a song's energy may sit from the target before it counts as an outlier. Matches the
# `energy_tolerance` the balanced scoring mode uses, so the critic and the scorer agree on
# what "close" means.
ENERGY_WINDOW = 0.35

# A playlist asked to run 30 minutes is accepted between 25.5 and 34.5 minutes. Tighter than
# this and the critic rejects lists that are musically fine; looser and "30 minutes" stops
# meaning anything.
DURATION_TOLERANCE = 0.15

# At least this share of a playlist must match a language the user explicitly named.
LANGUAGE_MIN_SHARE = 0.6


@dataclass
class Failure:
    """One thing wrong with a candidate playlist."""

    code: str
    detail: str
    severity: str = "hard"
    song_id: Optional[int] = None

    def as_dict(self) -> Dict:
        return {
            "code": self.code,
            "detail": self.detail,
            "severity": self.severity,
            "song_id": self.song_id,
        }


@dataclass
class Verdict:
    """The critic's report on one candidate playlist."""

    failures: List[Failure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def codes(self) -> List[str]:
        return [failure.code for failure in self.failures]

    def as_dict(self) -> Dict:
        return {"ok": self.ok, "failures": [f.as_dict() for f in self.failures]}


@dataclass
class State:
    """What the loop is allowed to change between attempts.

    Keeping the mutable knobs in one object is what makes a repair auditable: the log records
    the state before and after, so "why did attempt 3 differ from attempt 2" has an answer.
    """

    profile: Dict
    k: int
    excluded: List[int] = field(default_factory=list)
    diversify: bool = True
    order: str = "score"
    relaxations: List[str] = field(default_factory=list)
    cold_start: bool = False


# Profile fields that give `score_song` something to actually score. If none of them is set,
# every song in the catalog scores exactly 0.00 and the ranking is decided entirely by the
# alphabetical tie-break -- see `_has_scoring_signal`.
SCORING_SIGNAL_FIELDS = (
    "genre",
    "mood",
    "energy",
    "mood_tags",
    "tempo_bpm",
    "language",
    "decade",
    "likes_acoustic",
    "duration_sec",
)


def _has_scoring_signal(profile: Dict) -> bool:
    """True if the profile gives the scorer at least one thing to reward.

    The scoring mode counts too, not just the preference fields: `discovery` carries a
    novelty weight, which awards every song a score derived from its popularity, so a
    profile of nothing but `mode: discovery` is genuinely rankable. Missing that sent
    "I want to discover something obscure" down the cold-start path, which threw away the
    novelty ordering the request had explicitly asked for.
    """
    if any(profile.get(field_name) not in (None, "", []) for field_name in SCORING_SIGNAL_FIELDS):
        return True
    weights = get_mode(profile.get("mode"))
    return bool(weights.novelty or weights.popularity)


@dataclass
class PlaylistResult:
    """Everything one run produced, including how it got there."""

    request: str
    ok: bool
    picks: List[Tuple[Dict, float, str]] = field(default_factory=list)
    profile: Dict = field(default_factory=dict)
    hits: List[Hit] = field(default_factory=list)
    verdict: Verdict = field(default_factory=Verdict)
    confidence: Optional[confidence_mod.ConfidenceReport] = None
    summary: str = ""
    rationale: str = ""
    backend: str = "offline"
    backend_detail: str = ""
    degraded: bool = False
    degrade_reason: str = ""
    iterations: int = 0
    attempts: List[Dict] = field(default_factory=list)
    guardrail: Optional[GuardrailVerdict] = None
    refusal: str = ""
    cold_start: bool = False
    clamp_notes: List[str] = field(default_factory=list)
    run_id: str = ""
    log_path: Optional[str] = None
    total_seconds: int = 0

    @property
    def refused(self) -> bool:
        return bool(self.refusal)


# --------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------


class ToolBox:
    """The agent's tool surface, with every call logged.

    These are the same four tools the model-driven loop in `src/tool_loop.py` is given, so
    the two loops are genuinely comparable: same catalog, same scorer, same retriever,
    different thing deciding what to call.
    """

    def __init__(self, songs: List[Dict], retriever: NoteRetriever, logger: RunLogger):
        self.songs = songs
        self.retriever = retriever
        self.logger = logger
        self.calls = 0

    def _log(self, tool: str, args: Dict, summary) -> None:
        self.calls += 1
        self.logger.event("tool_call", tool=tool, args=args, result=summary)

    def retrieve_notes(self, query: str, k: int = 3) -> List[Hit]:
        """Finds the listening notes most relevant to a request."""
        hits = self.retriever.search(query, k=k)
        self._log(
            "retrieve_notes",
            {"query": query[:120], "k": k},
            [{"id": hit.id, "score": hit.score} for hit in hits],
        )
        return hits

    def recommend(
        self,
        profile: Dict,
        k: int,
        excluded: Sequence[int] = (),
        diversify: bool = True,
    ) -> List[Tuple[Dict, float, str]]:
        """Scores and ranks the catalog, skipping any excluded song ids."""
        pool = [song for song in self.songs if int(song["id"]) not in set(excluded)]
        prefs = {key: value for key, value in profile.items() if not key.startswith("_")}
        picks = recommend_songs(prefs, pool, k=k, mode=prefs.get("mode"), diversify=diversify)
        self._log(
            "recommend",
            {"k": k, "excluded": list(excluded), "diversify": diversify, "mode": prefs.get("mode")},
            [{"id": song["id"], "title": song["title"], "score": score} for song, score, _ in picks],
        )
        return picks

    def next_candidate_score(self, profile: Dict, chosen_ids: Sequence[int]) -> Optional[float]:
        """The score of the best song *not* chosen -- the margin the confidence model needs."""
        pool = [song for song in self.songs if int(song["id"]) not in set(chosen_ids)]
        if not pool:
            return None
        prefs = {key: value for key, value in profile.items() if not key.startswith("_")}
        ranked = recommend_songs(prefs, pool, k=1, mode=prefs.get("mode"), diversify=False)
        return ranked[0][1] if ranked else None

    def diverse_sample(self, k: int) -> List[Tuple[Dict, float, str]]:
        """A deliberately spread-out sample, for a request that specified nothing.

        This is the cold-start answer prescribed by `data/notes/theory-cold-start.md`: with no
        stated preference there is nothing to rank, so ranking anyway just hands the user
        whatever the default weights happen to favour. Coverage is more useful -- a list
        spanning several genres and the whole energy range gives the listener something to
        react to, and the next request is then informative.

        Deterministic: one representative per genre (the most popular, title as tie-break),
        sorted by energy, then evenly spaced samples across that range.
        """
        by_genre: Dict[str, Dict] = {}
        for song in sorted(self.songs, key=lambda s: (str(s["genre"]), -int(s["popularity"]), str(s["title"]))):
            by_genre.setdefault(str(song["genre"]), song)

        reps = sorted(by_genre.values(), key=lambda s: (float(s["energy"]), str(s["title"])))
        if k >= len(reps):
            chosen = reps
        else:
            step = (len(reps) - 1) / (k - 1) if k > 1 else 0.0
            seen: List[int] = []
            chosen = []
            for index in range(k):
                position = round(index * step)
                while position in seen and position < len(reps) - 1:
                    position += 1
                seen.append(position)
                chosen.append(reps[position])

        picks = [
            (
                song,
                0.0,
                f"cold start: chosen to span the catalog ({song['genre']}, energy "
                f"{float(song['energy']):.2f}) because the request set no preferences",
            )
            for song in chosen
        ]
        self._log(
            "diverse_sample",
            {"k": k},
            [{"id": song["id"], "title": song["title"]} for song, _, _ in picks],
        )
        return picks

    def has_positive_alternative(self, profile: Dict, excluded: Sequence[int]) -> bool:
        """Whether any not-yet-excluded song still scores above zero.

        Guards the `zero_score` repair: excluding a zero-scoring song only helps if something
        better can take its place. Without this check, a profile that scores every song at
        zero drives the loop to exclude the entire catalog one attempt at a time.
        """
        pool = [song for song in self.songs if int(song["id"]) not in set(excluded)]
        if not pool:
            return False
        prefs = {key: value for key, value in profile.items() if not key.startswith("_")}
        ranked = recommend_songs(prefs, pool, k=1, mode=prefs.get("mode"), diversify=False)
        return bool(ranked) and ranked[0][1] > 0

    def inspect_song(self, song_id: int) -> Optional[Dict]:
        """Returns one catalog row by id."""
        found = next((song for song in self.songs if int(song["id"]) == int(song_id)), None)
        self._log("inspect_song", {"song_id": song_id}, found["title"] if found else None)
        return found

    def catalog_stats(self) -> Dict:
        """Summary of what is actually available, so the agent can size its requests."""
        energies = [float(song["energy"]) for song in self.songs]
        stats = {
            "songs": len(self.songs),
            "genres": sorted({str(song["genre"]) for song in self.songs}),
            "mean_duration_sec": round(sum(int(s["duration_sec"]) for s in self.songs) / len(self.songs)),
            "energy_min": min(energies),
            "energy_max": max(energies),
        }
        self._log("catalog_stats", {}, {"songs": stats["songs"]})
        return stats


# --------------------------------------------------------------------------------------
# The critic
# --------------------------------------------------------------------------------------


def check_playlist(picks: List[Tuple[Dict, float, str]], profile: Dict, state: State) -> Verdict:
    """Checks a candidate playlist against every constraint the request implies.

    Returns every failure found rather than the first, so one pass through the loop can fix
    several independent problems instead of rediscovering them one attempt at a time.
    """
    failures: List[Failure] = []
    target_k = state.k

    if not picks:
        return Verdict([Failure("empty", "no song scored above zero for this profile")])

    if len(picks) < target_k:
        failures.append(
            Failure(
                "size_short",
                f"asked for {target_k} songs, got {len(picks)}",
                severity="hard",
            )
        )

    # A zero or negative score means nothing in the song matched the profile; the diversity
    # penalty can also push a weak pick below zero. Either way it is filler, not a
    # recommendation, and shipping it is worse than returning a shorter list.
    #
    # Skipped on a cold start, where every score is zero *by construction* -- the profile set
    # no preferences, so there is nothing to match and a zero score is the honest answer
    # rather than a fault to repair.
    if not state.cold_start:
        for song, score, _ in picks:
            if score <= 0:
                failures.append(
                    Failure(
                        "zero_score",
                        f"'{song['title']}' scored {score:.2f}, nothing in it matches the profile",
                        song_id=int(song["id"]),
                    )
                )

    artists: Dict[str, int] = {}
    for song, _, _ in picks:
        key = str(song["artist"]).lower()
        artists[key] = artists.get(key, 0) + 1
    for artist, count in artists.items():
        if count > 1:
            failures.append(
                Failure("artist_repeat", f"{count} songs by the same artist ({artist})")
            )

    genre_cap = max(2, math.ceil(target_k / 2))
    genres: Dict[str, int] = {}
    for song, _, _ in picks:
        key = str(song["genre"]).lower()
        genres[key] = genres.get(key, 0) + 1
    for genre, count in genres.items():
        if count > genre_cap:
            failures.append(
                Failure(
                    "genre_flood",
                    f"{count} of {len(picks)} songs are {genre}, cap for this size is {genre_cap}",
                    severity="soft",
                )
            )

    target_energy = profile.get("energy")
    if target_energy is not None:
        for song, _, _ in picks:
            gap = abs(float(song["energy"]) - float(target_energy))
            if gap > ENERGY_WINDOW:
                failures.append(
                    Failure(
                        "energy_outlier",
                        f"'{song['title']}' at energy {float(song['energy']):.2f} is "
                        f"{gap:.2f} from the {float(target_energy):.2f} target",
                        song_id=int(song["id"]),
                    )
                )

    wanted_language = profile.get("language")
    if wanted_language:
        matches = sum(
            1 for song, _, _ in picks if str(song.get("language", "")).lower() == str(wanted_language).lower()
        )
        share = matches / len(picks)
        if share < LANGUAGE_MIN_SHARE:
            failures.append(
                Failure(
                    "language_mismatch",
                    f"only {matches}/{len(picks)} songs are {wanted_language} "
                    f"({share:.0%}, needs {LANGUAGE_MIN_SHARE:.0%})",
                )
            )

    total_minutes = profile.get("total_minutes")
    if total_minutes:
        actual = sum(int(song["duration_sec"]) for song, _, _ in picks) / 60.0
        low = total_minutes * (1 - DURATION_TOLERANCE)
        high = total_minutes * (1 + DURATION_TOLERANCE)
        if actual < low:
            failures.append(
                Failure("duration_under", f"{actual:.1f} min of music, asked for ~{total_minutes} min")
            )
        elif actual > high:
            failures.append(
                Failure("duration_over", f"{actual:.1f} min of music, asked for ~{total_minutes} min")
            )

    # Arc is a property of the ordering, invisible to every per-song score. Only `build` and
    # `descend` impose an order; `flat` asks for cohesion, which the energy window covers.
    arc = profile.get("arc", "flat")
    if arc in ("build", "descend") and len(picks) >= 3:
        energies = [float(song["energy"]) for song, _, _ in picks]
        if arc == "build" and energies[-1] < energies[0]:
            failures.append(
                Failure(
                    "arc_violation",
                    f"asked for a build but the list ends lower than it starts "
                    f"({energies[0]:.2f} to {energies[-1]:.2f})",
                    severity="soft",
                )
            )
        if arc == "descend" and energies[-1] > energies[0]:
            failures.append(
                Failure(
                    "arc_violation",
                    f"asked for a wind-down but the list ends higher than it starts "
                    f"({energies[0]:.2f} to {energies[-1]:.2f})",
                    severity="soft",
                )
            )

    return Verdict(failures)


# --------------------------------------------------------------------------------------
# Repairs
# --------------------------------------------------------------------------------------


def repair(
    failures: List[Failure],
    state: State,
    picks: List[Tuple[Dict, float, str]],
    can_improve=None,
) -> List[str]:
    """Applies one corrective action per failure. Returns a description of what it did.

    An empty return means nothing could be done, which ends the loop -- the alternative is
    retrying an identical request and calling it progress.

    Each action is the narrowest change that could fix its failure, so the next attempt
    differs from this one in a way that is easy to attribute in the log.

    `can_improve(profile, excluded)` is an optional predicate answering "is there still a
    better song available". Dropping a song is only progress if something can replace it, so
    without it a profile that scores everything at zero would exclude the whole catalog.
    """
    actions: List[str] = []
    handled: set = set()

    for failure in failures:
        code = failure.code
        if code in handled and code not in ("zero_score", "energy_outlier"):
            continue
        handled.add(code)

        if code in ("zero_score", "energy_outlier") and failure.song_id is not None:
            if can_improve is not None and not can_improve(state.profile, state.excluded):
                continue
            if failure.song_id not in state.excluded:
                state.excluded.append(failure.song_id)
                actions.append(f"excluded song {failure.song_id} ({code})")

        elif code == "artist_repeat":
            if not state.diversify:
                state.diversify = True
                actions.append("re-enabled the artist/genre diversity penalty")

        elif code == "genre_flood":
            if not state.diversify:
                state.diversify = True
                actions.append("re-enabled the diversity penalty to break up the genre")

        elif code == "language_mismatch":
            # The catalog may simply not hold enough songs in that language. Rather than
            # loop, drop the language constraint and record the relaxation so the user is
            # told why their request was not met literally.
            language = state.profile.pop("language", None)
            if language:
                state.relaxations.append(
                    f"dropped the '{language}' language requirement: the 22-song catalog "
                    f"does not hold enough {language} tracks to fill this playlist"
                )
                actions.append(f"relaxed the language constraint ({language})")

        elif code == "duration_under":
            if state.k < 10:
                state.k += 1
                actions.append(f"added a song to reach the requested running time (k={state.k})")

        elif code == "duration_over":
            if state.k > 1:
                state.k -= 1
                actions.append(f"removed a song to reach the requested running time (k={state.k})")

        elif code == "arc_violation":
            arc = state.profile.get("arc", "flat")
            if state.order == "score":
                state.order = arc
                actions.append(f"re-ordered the playlist into a {arc} energy arc")

        elif code == "size_short":
            if state.diversify:
                # The diversity penalty can starve a short catalog of eligible songs; giving
                # it up is worse than returning fewer songs, so it is the last thing tried.
                state.diversify = False
                actions.append("disabled the diversity penalty to fill the requested size")
            elif state.excluded:
                restored = state.excluded.pop(0)
                actions.append(f"restored excluded song {restored} to fill the requested size")

    return actions


def apply_order(picks: List[Tuple[Dict, float, str]], order: str) -> List[Tuple[Dict, float, str]]:
    """Re-sorts a playlist into an energy arc. `score` leaves it in ranking order."""
    if order == "build":
        return sorted(picks, key=lambda row: (float(row[0]["energy"]), row[0]["title"]))
    if order == "descend":
        return sorted(picks, key=lambda row: (-float(row[0]["energy"]), row[0]["title"]))
    return picks


# --------------------------------------------------------------------------------------
# The agent
# --------------------------------------------------------------------------------------


class VibeAgent:
    """Runs one request end to end."""

    def __init__(
        self,
        songs: Optional[List[Dict]] = None,
        retriever: Optional[NoteRetriever] = None,
        backend=None,
        backend_detail: str = "",
        logger: Optional[RunLogger] = None,
        use_retrieval: bool = True,
        max_iterations: int = MAX_ITERATIONS,
    ):
        self.songs = songs if songs is not None else load_songs()
        self.retriever = retriever if retriever is not None else NoteRetriever(load_notes(DEFAULT_NOTES_DIR))
        self.logger = logger or RunLogger(run_id=new_run_id(), enabled=logging_enabled())
        if backend is None:
            backend, backend_detail = build_backend(logger=self.logger)
        self.backend = backend
        self.backend_detail = backend_detail
        self.use_retrieval = use_retrieval
        self.max_iterations = max_iterations
        self.tools = ToolBox(self.songs, self.retriever, self.logger)

    def run(self, request: str, overrides: Optional[Dict] = None) -> PlaylistResult:
        """Plan, act, check, repair, report.

        `overrides` pins profile fields after planning (used by the CLI's `-k` / `--mode`),
        so an explicit instruction from the user beats whatever the planner inferred.
        """
        logger = self.logger
        result = PlaylistResult(
            request=request,
            ok=False,
            backend=getattr(self.backend, "name", "offline"),
            backend_detail=self.backend_detail,
            run_id=logger.run_id,
        )

        logger.event("request_received", request=request[:500], backend=self.backend_detail)

        # --- Guardrails -----------------------------------------------------------------
        guard = check_request(request)
        result.guardrail = guard
        logger.event("guardrail", ok=guard.ok, code=guard.code, warnings=guard.warnings)
        if guard.refused:
            result.refusal = guard.message
            logger.event("refused", code=guard.code, message=guard.message)
            result.total_seconds = logger.elapsed_ms // 1000
            result.log_path = str(logger.close() or "")
            return result

        cleaned = guard.cleaned

        # --- Plan -----------------------------------------------------------------------
        hits = self.tools.retrieve_notes(cleaned, k=3) if self.use_retrieval else []
        if not self.use_retrieval:
            logger.event("retrieval_skipped", reason="--no-retrieval ablation")
        strength = self.retriever.strength(hits) if hits else 0.0
        result.hits = hits
        logger.event(
            "retrieved",
            strength=strength,
            notes=[{"id": hit.id, "title": hit.title, "score": hit.score} for hit in hits],
        )

        # The off-domain decision is deferred until retrieval has reported: a request with no
        # musical vocabulary is still legitimate if the notes recognise the situation it
        # describes. Only when both signals are absent is it refused.
        off_domain = off_domain_verdict(
            guard, strength, keyword_hit=bool(hits and hits[0].keyword_hit)
        )
        if off_domain is not None:
            result.guardrail = off_domain
            result.refusal = off_domain.message
            logger.event("refused", code=off_domain.code, message=off_domain.message, strength=strength)
            result.total_seconds = logger.elapsed_ms // 1000
            result.log_path = str(logger.close() or "")
            return result

        try:
            plan = self.backend.plan(cleaned, hits)
        except Exception as error:  # noqa: BLE001 - last-resort net; ResilientBackend handles most
            logger.error("plan", error)
            from src.llm import OfflineBackend

            plan = OfflineBackend().plan(cleaned, hits)
            plan.degraded = True
            plan.degrade_reason = f"{type(error).__name__}: {error}"

        proposed = dict(plan.profile)
        if overrides:
            # Applied before clamping so an override is range-checked like anything else.
            proposed.update({k: v for k, v in overrides.items() if v is not None})
            logger.event("cli_override", overrides={k: v for k, v in overrides.items() if v is not None})

        profile, clamp_notes = clamp_profile(proposed)
        result.clamp_notes = clamp_notes
        result.degraded = plan.degraded
        result.degrade_reason = plan.degrade_reason
        result.rationale = sanitise_text(plan.rationale, limit=400)
        logger.event(
            "planned",
            backend=plan.backend,
            model=plan.model,
            degraded=plan.degraded,
            profile={k: v for k, v in profile.items() if not k.startswith("_")},
            clamped=clamp_notes,
            usage=plan.usage,
        )

        # A requested running time implies a song count: the catalog averages ~4 minutes a
        # track, so asking for 30 minutes and leaving k at its default of 5 would fail the
        # duration check on the first attempt every time. Sizing it here means the loop
        # starts from a sane guess and the repair only has to fine-tune.
        state = State(profile=profile, k=int(profile.get("k", 5)))

        # Cold start: the request (and the notes) gave the scorer nothing to reward, so every
        # song would score 0.00 and the "ranking" would be the alphabetical tie-break wearing
        # a ranking's clothes. Switch to coverage instead, and say so in the output.
        state.cold_start = not _has_scoring_signal(profile)
        if state.cold_start:
            logger.event(
                "cold_start",
                reason="request and retrieved notes set no scorable preference",
                fields_checked=list(SCORING_SIGNAL_FIELDS),
            )

        # `overrides` arrives from the CLI with a key per flag whether or not the flag was
        # given, so an unset `-k` shows up as {"k": None}. Testing for the key alone made
        # every CLI run look like it had an explicit song count, which silently disabled the
        # duration sizing below -- the loop still converged, by repairing one song at a time,
        # but it took three attempts where it should take one.
        k_was_explicit = "k" in (plan.profile.get("_sources") or {}) or (overrides or {}).get("k") is not None
        if profile.get("total_minutes") and not k_was_explicit:
            mean_duration = self.tools.catalog_stats()["mean_duration_sec"]
            estimated = max(1, min(10, round(profile["total_minutes"] * 60 / mean_duration)))
            if estimated != state.k:
                logger.event("sized_for_duration", minutes=profile["total_minutes"], k=estimated)
                state.k = estimated

        # --- Act / check / repair -------------------------------------------------------
        picks: List[Tuple[Dict, float, str]] = []
        verdict = Verdict()
        for iteration in range(1, self.max_iterations + 1):
            result.iterations = iteration
            if state.cold_start:
                raw = self.tools.diverse_sample(k=state.k)
            else:
                raw = self.tools.recommend(
                    state.profile, k=state.k, excluded=state.excluded, diversify=state.diversify
                )
            picks = apply_order(raw, state.order)
            verdict = check_playlist(picks, state.profile, state)

            attempt = {
                "iteration": iteration,
                "k": state.k,
                "order": state.order,
                "diversify": state.diversify,
                "excluded": list(state.excluded),
                "picks": [song["title"] for song, _, _ in picks],
                "ok": verdict.ok,
                "failures": verdict.codes,
            }
            logger.event("attempt", **attempt)

            if verdict.ok:
                result.attempts.append(attempt)
                break

            actions = repair(
                verdict.failures, state, picks, can_improve=self.tools.has_positive_alternative
            )
            attempt["repairs"] = actions
            result.attempts.append(attempt)
            logger.event(
                "repair",
                iteration=iteration,
                failures=[f.as_dict() for f in verdict.failures],
                actions=actions,
            )
            if not actions:
                logger.event("repair_exhausted", iteration=iteration, remaining=verdict.codes)
                break
        else:
            logger.event("iteration_limit", limit=self.max_iterations, remaining=verdict.codes)

        # --- Report ---------------------------------------------------------------------
        result.picks = picks
        result.profile = state.profile
        result.verdict = verdict
        result.ok = verdict.ok and bool(picks)
        result.cold_start = state.cold_start

        runner_up = self.tools.next_candidate_score(
            state.profile, [int(song["id"]) for song, _, _ in picks]
        )
        report = confidence_mod.score_run(
            retrieval_strength=strength,
            profile=state.profile,
            picks=picks,
            failures=verdict.failures,
            iterations=result.iterations,
            runner_up_score=runner_up,
            degraded=result.degraded,
        )
        for relaxation in state.relaxations:
            report.notes.append(relaxation)
        if state.cold_start:
            report.notes.append(
                "cold start: the request set no scorable preference, so these songs were "
                "chosen to span the catalog rather than to match a profile"
            )
        result.confidence = report
        logger.event("confidence", **report.as_dict())

        try:
            summary, narration = self.backend.narrate(cleaned, state.profile, picks, report.value)
            result.summary = sanitise_text(summary)
            if narration.degraded and not result.degraded:
                result.degraded = True
                result.degrade_reason = narration.degrade_reason
        except Exception as error:  # noqa: BLE001
            logger.error("narrate", error)
            result.summary = ""

        logger.event(
            "final",
            ok=result.ok,
            iterations=result.iterations,
            confidence=report.value,
            band=report.band,
            picks=[{"id": song["id"], "title": song["title"], "score": score} for song, score, _ in picks],
            unresolved=verdict.codes,
            tool_calls=self.tools.calls,
        )
        result.total_seconds = logger.elapsed_ms // 1000
        result.log_path = str(logger.close() or "")
        return result
