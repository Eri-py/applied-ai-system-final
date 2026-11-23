# 🎧 Model Card: VibeFinder 2.0

The card for the applied system in this repository. The card for the original Module 3
project is preserved unchanged at [`docs/model_card_v1.md`](docs/model_card_v1.md).

---

## 1. What this is

**VibeFinder 2.0** turns a plain-English listening request into a playlist drawn from a fixed
22-song catalog, together with the reason for every song, every correction it made along the
way, and a numeric confidence in the result.

It is not a model. It is a **system built around one**, and the distinction matters for
everything below:

| Component | What it is | Deterministic? |
|---|---|---|
| Retrieval | BM25 over 14 hand-written listening notes | yes |
| Planner | Claude `claude-opus-5-5` via structured JSON output | no |
| Planner fallback | Keyword + note-hint rules | yes |
| Scorer / ranker | The unchanged Module 3 `score_song` / `recommend_songs` | yes |
| Critic and repairs | Constraint checks and registered corrective actions | yes |
| Confidence | Weighted sum of four measured components | yes |
| Narrator | Claude, or text assembled from recorded reasons | no |

Only two steps involve a language model. Everything that decides *which songs you get* is
arithmetic I can read, which is why the same request returns a byte-identical playlist every
time, and why a bad answer can be traced to the component that caused it.

## 2. Intended use

**Intended.** A teaching and portfolio artefact. A worked example of putting retrieval,
agentic self-checking, guardrails and measured confidence around a small, fully legible
recommender, where every component is small enough to read in one sitting.

**Not intended.** Real music discovery (the catalog is 22 fictional songs), any decision about
a person, or any setting where the output is consumed without the explanation beside it. The
explanation is not decoration here — a playlist from this system without its confidence score
is actively misleading, because the system's most interesting property is that it knows when
it is guessing.

**Out of scope by design.** It refuses instruction-override attempts and requests that are
neither musical in wording nor recognisable as a listening situation. It has no users, no
history and no behavioural signal, so it cannot do collaborative filtering and does not
pretend to.

## 3. Data

**Song catalog** (`data/songs.csv`) — 22 fictional songs across 19 genres, 15 columns, written
by hand for Module 3. Fictional on purpose: the card does not characterise any real artist's
work, and I set the audio-feature values by hand rather than inferring them, so no hidden
model sits underneath the numbers.

**Listening-note corpus** (`data/notes/*.md`) — 14 notes, roughly 3,150 words, new in 2.0.
Eight describe listening contexts (workout, focus, sleep, party, commute, rainy day,
heartbreak, morning), three describe genre families, three cover ordering, diversity and cold
starts. Each carries prose plus a `hints:` block of structured defaults.

**The notes are the system's most consequential and least audited input.** They are my own
synthesis, written in my own voice, summarising claims about music psychology — tempo
entrainment near resting heart rate, the irrelevant speech effect, sad listeners preferring
sad music — that I believe are broadly supported but have not systematically sourced, and that
I have stated far more crisply in the notes than the underlying literature would justify. The
ablation shows these notes drive a 45-point swing in the system's measured pass rate. **An
unsourced corpus is doing most of the work**, and of everything in this project that is the
claim I am least able to back up.

## 4. How it decides

1. **Screen** the request (empty, too short, overlong, injection attempt).
2. **Retrieve** the most relevant notes by BM25; merge their hints, ignoring any note scoring
   below 35% of the top hit.
3. **Plan** a profile — Claude grounded in the retrieved prose, or the deterministic planner
   using the hints plus explicit request signals — then clamp it into legal ranges.
4. **Act**: score and rank the catalog. If nothing in the profile is scorable, take the
   cold-start path instead and return deliberate coverage.
5. **Check** against constraints no single song score can express: repeated artist, genre
   flooding, energy window, language share, running time, energy arc.
6. **Repair** one narrow action per failure and retry, up to five attempts.
7. **Report** the playlist, the reasons, the repairs, and a confidence with its components.

Full diagrams: [`diagrams/architecture.mmd`](diagrams/architecture.mmd) and
[`diagrams/agent_loop.mmd`](diagrams/agent_loop.mmd).

## 5. Biases and failure modes

### Inherited from Module 3, still present

- **Genre-spelling advantage.** Broad labels beat narrow ones for no musical reason: `pop`
  scores a full genre match where `bedroom pop` gets partial credit against a `pop` request.
- **The middle of the energy scale wins.** The catalog bunches around 0.3–0.5 and 0.7–0.9, so
  requests landing in those bands match widely and requests at the extremes match thinly.
- **Mood conflict is unrewarded but never penalised.** This is the big one, and it is the exact
  failure that **Module 3's own model card predicted in its Future Work section** and I did not
  fix: a song matching no mood and no tag can still rank highly by accumulating energy, tempo
  and texture points. Human review found it live: in a playlist asked to be nocturnal and
  cinematic, a communal gospel track ranks fourth and a sunny afrobeats track fifth
  ([`docs/human_eval.md`](docs/human_eval.md), case 5). Both pass every automated check.
  Fixing it means changing the Module 3 scoring weights, which deserves its own measurement
  rather than a patch to make one case pass.

### New in 2.0

- **The notes corpus is a bias vector, not just a knowledge source.** Every claim in it becomes
  a default applied to real requests. The heartbreak note's instruction to match the feeling
  rather than lift it is, I think, correct and well supported — but it is a judgement about
  what is good for a distressed person, encoded as a number (`energy: 0.28`), applied without
  asking. A listener who wants to be cheered up is served badly and is never offered the
  choice.
- **English-centred retrieval.** The BM25 index has no stemming and no synonyms beyond a
  hand-written table. "Exercising" does not match the workout note's "exercise"; a non-native
  phrasing or a typo degrades silently to a weaker profile and a lower confidence. The system
  will quietly serve worse results to people who phrase things differently from me.
- **The language constraint is near-unsatisfiable.** One Spanish track, one Yoruba track. Any
  non-English request gets relaxed. The relaxation is explained, which is the right behaviour,
  but the underlying service is still English-first.
- **Confidence measures the wrong thing more than I would like.** It separates under-specified
  requests from specified ones well (0.35 against 0.69). It barely separates runs that *failed*
  from runs that *passed* — 0.05 in the degraded configuration. It answers "was I told enough
  to do this well?" and not "did I get this one right?", and those read identically to a user.
- **Off-domain refusal is approximate.** It needs both no musical vocabulary and no
  keyword-backed note match, biased toward accepting. "My tax return is late" is refused and
  "i cant stop crying" is served, which is right — but that boundary rests on a threshold
  tuned against a handful of examples, and it will misjudge cases I have not thought of.

## 6. Evaluation

Full report: [EVALUATION.md](EVALUATION.md). Human judgement:
[`docs/human_eval.md`](docs/human_eval.md).

| Measurement | Result |
|---|---|
| Unit tests | 285 passed |
| Labelled cases | 29/29 passed, mean confidence 0.65 |
| Reproducibility (3 runs each) | 29/29 byte-identical |
| Retrieval ablation | 100% → **55%** pass rate; confidence 0.65 → 0.21; 13 cases break |
| Confidence: thin vs specified requests | 0.35 vs 0.69 |
| Confidence: failing vs passing runs | gap of 0.05 — weak |
| Human review of 12 playlists | 8 pass, 3 weak, 1 fail |

**Read the 29/29 sceptically.** The cases were written alongside the fixes they describe: I
found seven real defects by running the system and reading its output, and added the case that
would have caught each one as I fixed it. That makes the suite a regression guard, not a
quality measure. The ablation and the human review are the parts that tested the system against
something it was not tuned for, and both found real problems.

**The live Claude path is not verified end to end.** Tests with a fake client pin its request
shape — model id, closed schema, grounding content reaching the model, refusal handling,
beta-rejection retry — but no test here has called the real API, because the machine I built
this on had no key. Every published number comes from the deterministic planner. "We use
Claude" would otherwise be read as "and we tested that", and those are different claims.

## 7. Responsible-AI reflection

### How I collaborated with AI

I built this with Claude in an agentic coding session, and the division of labour was sharper
than I expected. It was fast and genuinely good at **inventory and scaffolding**: drafting the
14-note corpus, writing a dependency-free BM25 index, producing the vocabulary tables, and
generating the test suite — 285 tests is more than I would have written by hand, and the
coverage of the repair branches is better for it.

It was most useful as a **harness for my own judgement** in one specific way: it ran the system
after each change and showed me the output. I found every defect in this project that way,
reading output rather than code, because each component was individually correct when I read it.

Where I had to push back was on **what the system should do when it doesn't know**. The
defaults AI produces are confident defaults. Left alone, the system returned five songs and a
tidy explanation for "play me something good" exactly as it did for a precise request, and
nothing in the code was wrong — that was the design, and the design was dishonest.

**A suggestion I accepted.** Early on I was offered three ways to handle the model dependency:
require an API key, avoid models entirely, or run Claude with a deterministic offline
fallback. I took the third. I had been leaning toward the key-required version because it is
less code and the "real" integration looks better in a portfolio, and the argument that
changed my mind was reproducibility: a repo that cannot run without a secret cannot be checked
by a grader, cannot run in CI, and cannot support the reproducibility experiment that turned
out to be one of the project's strongest results. Writing a *real* fallback rather than a stub
cost noticeably more work and is the reason the ablation, the determinism test and the CI
pipeline all exist.

**A suggestion I rejected.** When the confidence calibration came back weak — 0.05 separation
between passing and failing runs — the obvious move was available and tempting: reweight the
four components until the number looked better, or quietly report only the thin-versus-specified
comparison, which is a genuinely good 0.34. I rejected both. Tuning weights against the 29
cases I had written would have been fitting the metric to the test set and would have produced
a confidence score that looked calibrated and measured nothing new. So EVALUATION.md reports
the 0.05 as a named weakness with a structural explanation (two of the four components collapse
together when retrieval is weak) and says what fixing it would actually require — held-out
human judgements to regress against, which this project does not have.

**A suggestion I revised rather than took whole.** The first off-domain guard refused anything
without a music word in it. Clean, one function, and it rejected "my girlfriend dumped me" —
the single request that best demonstrates why the notes corpus exists. The revision splits the
decision in two and defers it until after retrieval, so refusal requires both signals to be
absent. It is more code and a fuzzier boundary, and it is right.

### What I would not claim

That the playlists are good. Eight of twelve survived review, one failed outright, and that
review is **not independent** — the same process that produced the playlists produced the
assessment. [`docs/human_eval.md`](docs/human_eval.md) scores all twelve against a four-part
rubric and attributes every verdict to "Reviewer A", with the conflict of interest stated at the
top and a filled-in protocol and empty table for an independent second rater.

A harder limit sits underneath all of that: **the 22 songs are fictional, so there is no
audio, and nobody can evaluate these playlists by listening to them.** What the review does is read
each playlist's metadata against the request and judge whether the selection is defensible.
That is a weaker instrument than listening, and it still caught two things the 285 unit tests
and 29 labelled cases all missed — including the one case where every automated check passes
and two of five tracks are plainly the wrong feeling.

### Limitations

1. 22 fictional songs, and no audio — several constraints are unsatisfiable in principle, and
   no playlist this system produces can be assessed by listening to it.
2. The notes corpus is unsourced and is doing most of the work.
3. Confidence predicts under-specification, not incorrectness.
4. Mood conflict is still unpenalised — the failure Module 3 predicted and 2.0 did not fix.
5. A hard duration target can outrank song quality (visible in the per-song confidence).
6. Retrieval is English-centred, unstemmed, and degrades silently on unfamiliar phrasing.
7. The live Claude path is unverified against the real API.
8. No user model, no history, no learning. Every request starts from zero.

## 8. Future work

In the order I would actually do it:

1. **The conflict-penalty table**, carried over unfinished from Module 3's model card and now
   with a concrete failing case to measure against (`docs/human_eval.md`, case 5). It is the
   one result in this project I am least willing to defend.
2. **A score floor in the critic**, so a duration target cannot ship a 1.28-scoring track
   without at least flagging the tail as padding rather than recommendation.
3. **Get a second, independent rating** using the protocol at the end of
   [`docs/human_eval.md`](docs/human_eval.md) — about twenty minutes of someone else's time —
   then use those twelve verdicts as held-out labels to test whether confidence predicts
   anything about quality. They would be the only data in the project not produced by the
   system being measured, which makes this the only honest route to fixing weakness 3.
4. **Stem the retrieval index and source the notes**, in that order — the first is an
   afternoon, the second is the real debt.
5. **Run the live path and the tool loop over the full case set** and publish the comparison
   table EVALUATION.md currently leaves blank.
