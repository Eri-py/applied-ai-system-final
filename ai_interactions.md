# AI Interactions Log

> **Two parts.** [Part 2](#part-2--module-5-vibefinder-20) logs the AI collaboration that
> built the applied system in this repository. [Part 1](#part-1--module-3-vibefinder-10)
> below it is the original Module 3 log, kept unchanged, covering the three stretch features
> I attempted there: advanced song features (SF8), multiple scoring modes via a design
> pattern (SF10), and the diversity/fairness penalty.
>
> The graded responsible-AI reflection is in section 7 of [`model_card.md`](model_card.md).

---

## Part 2 — Module 5 (VibeFinder 2.0)

This part logs the AI collaboration that produced the applied system in this repository: an
agentic coding session with Claude, extending the Module 3 recommender into a retrieval-backed,
self-checking system. The graded reflection drawn from it is section 7 of
[`model_card.md`](model_card.md).

I have logged this the way it actually went, including the parts where the first answer was
wrong, because the pattern of *what kind* of thing it got wrong is the useful content.

---

### Decision 1 — what to extend, and whether to depend on an API key

Before any code, I was asked to settle two things, and both changed the shape of the project.

**Which base project.** Module 1 (the Streamlit guessing game), Module 2 (PawPal+, the pet-care
scheduler) and Module 3 (VibeFinder) were all candidates. The argument for Module 3 was that it
already had the raw material an applied system needs: a CSV catalog that doubles as a retrieval
corpus, a `score_song` function that is ready-made as an agent tool, and an existing model card
and test suite. The argument against Module 1 was decisive — most of the final system would
have been new code sitting *beside* the original rather than extending it, which is not what
"evolve an earlier prototype" means.

**Whether to require an API key.** Three options: require one, avoid models entirely, or run
Claude with a deterministic offline fallback.

I took the fallback option, and this is the decision I would defend hardest. My instinct was
the key-required version — it is much less code, and a "real" integration reads better. What
changed my mind:

- A repo that cannot run without a secret cannot be checked by a grader.
- It cannot run in CI, so there is no continuous evidence that anything works.
- It cannot support a reproducibility experiment, because nothing is reproducible.

Writing the offline backend as a *real planner* rather than a stub was substantially more work
(it is the keyword tables and hint-merging logic in `src/llm.py`). It is also the single reason
the retrieval ablation, the determinism test and the CI pipeline all exist, and the ablation
turned out to be the strongest result in the project.

**Prompt that settled it:** I asked for the trade-offs rather than a recommendation, and the
reproducibility argument was not one I had thought of.

---

### Task 1 — the retrieval corpus

**What task did I give the agent?**

Write a corpus of listening notes that encodes the knowledge the catalog cannot hold: which
tempo a workout wants, why lyrics hurt concentration, what "rainy day" actually means as a
texture request. Each note needed prose (to ground a model) and a structured `hints:` block (to
seed the profile directly, so retrieval works offline and its contribution is measurable).

**Prompts used:**

- "Write 14 notes in `data/notes/`. Eight listening contexts, three genre families, three on
  ordering/diversity/cold starts. Frontmatter with `id`, `title`, `kind`, `keywords` and a
  `hints:` block whose keys match the profile fields the scorer already reads. The hints have
  to be musically defensible, not round numbers — if the workout note says 145 bpm, the prose
  should say why that band."
- "The notes must align with the actual 22-song catalog. Don't write a note about a genre that
  isn't in `songs.csv`."
- "Make the keyword lists cover how people really phrase these things, not the formal word."

**What it got right.** The prose is the strongest thing the AI produced in this project. The
focus note's framing of the irrelevant speech effect, the party note's distinction between
energy and danceability, and the heartbreak note's point that substituting cheerful music makes
the output worse while appearing kind are all better than what I would have written, and the
third one directly determines the system's behaviour on its best demo case.

**What I had to fix — and this is the important one.** The last instruction above was not
followed well enough, and I only found out by testing retrieval directly rather than reading
the notes. `"my girlfriend dumped me"` retrieved **nothing**: the heartbreak note's keywords
listed `heartbreak, heartbroken, breakup, sad, grief` — the formal vocabulary — and not
`dumped`, `girlfriend`, `boyfriend`, `ex`, `crying`, which is what people type. The note was
well written and unreachable.

This set the pattern for the whole session: **the AI's prose was reliably good and its coverage
of real-world phrasing was reliably optimistic.**

---

### Task 2 — retrieval, and a bug that would have been invisible

**Prompt:** "Write a BM25 index over the notes, no third-party dependency. Boost keyword-field
matches over body prose. Merge the hints of the retrieved notes into one profile."

**What it got right.** The index itself, first time: correct IDF, length normalisation, a
keyword-field boost, deterministic tie-breaking on note id. Genuinely good code and I did not
need to touch the maths.

**What I had to fix.** The hint merging. The first version merged hints from every retrieved
note, with the top hit winning any key it also defined. That sounds right and is wrong. Testing
`"play me something good"` produced this:

```
Q: play me something good
     theory-cold-start 5.68
     context-focus 1.81
     hints: {'mode': 'balanced', 'mood': 'focused', 'energy': 0.4,
             'likes_acoustic': True, 'language': 'instrumental', ...}
```

The cold-start note only defines `mode`, so the focus note — which matched on the single word
"good" appearing once in its prose — supplied an energy target of 0.40 and an instrumental-only
filter. A request that specified *nothing* was being answered with a confident, specific focus
playlist, and every number in the explanation would have been true.

That is precisely the false-precision failure the cold-start note itself warns about, produced
by the retriever. The fix is a floor: a note contributes hints only if it scored at least 35% of
the top hit. I would not have found this by reading the code — the code does what it says.

---

### Task 3 — the agent loop, and two more output-only bugs

**Prompt:** "Plan, act, check, repair. The critic checks what no single song score can express:
repeated artist, genre flooding, energy window, language share, running time, energy arc. One
narrow registered repair per failure code. Bounded."

**What it got right.** The critic/repair split, and the insight that an ordering failure is
invisible in per-song scores. The arc check is the most satisfying part of the system to watch
work.

**Two bugs found by running it, not reading it:**

1. **The cold-start death spiral.** `"play me something good"` yields a profile with nothing
   scorable, so every song scores exactly 0.00, so the critic raised `zero_score` on all five
   picks, so the repair excluded them — and repeated that until it had excluded almost the
   entire catalog, returning two songs scoring 0.00 after five attempts. Every component behaved
   as specified. The fix was two things: an explicit cold-start path that returns deliberate
   coverage across genres and the energy range, and a guard so a `zero_score` exclusion is only
   attempted when a better song actually exists.

2. **The off-domain guard refusing the best demo case.** The first guard refused any request
   with no music vocabulary in it — clean, one function, and it rejected `"my girlfriend dumped
   me"`, the single request that best shows why the notes corpus exists. I revised rather than
   accepted: the decision is now deferred until after retrieval and needs *both* signals absent
   (no musical wording **and** no keyword-backed note match). More code, fuzzier boundary, and
   right. I measured the threshold against real strengths rather than guessing — "i cant stop
   crying" scores 0.46 and is served, "my tax return is late" scores 0.38 and is refused.

---

### Task 4 — the evaluation harness, and a result I chose not to improve

**Prompt:** "29 labelled cases across happy, situation, constraint, thin, adversarial and edge
categories. Assert behavioural properties, not exact playlists. Then three experiments:
reproducibility, a retrieval ablation, and whether the confidence score is worth publishing."

**What it got right.** The ablation design, which produced the best evidence in the project —
turning the notes off drops the pass rate from 100% to 55% and mean confidence from 0.65 to
0.21, with 13 named cases that break. Before that number existed, "this project uses RAG" was
an assertion.

**What I rejected.** The calibration experiment came back weak: confidence separates
under-specified requests from specified ones by 0.34, but separates *failing* from *passing*
runs by only 0.05. Two tempting moves were available — reweight the four components until the
number improved, or report only the flattering comparison.

I rejected both, and this is the other decision I would defend hardest. Tuning the weights
against the same 29 cases I had written would be fitting the metric to the test set: the score
would look calibrated and would measure nothing it had not already been shown. So EVALUATION.md
reports the 0.05 as a named weakness, explains it structurally (two of the four components
collapse together whenever retrieval is weak, so they depress passing and failing runs alike),
and states what fixing it would actually need — held-out human judgements to regress against,
which this project does not have.

**I also made the harness say so about itself.** The suite passes 29/29, and that number is
close to meaningless on its own, because the cases were written alongside the fixes they
describe. EVALUATION.md states this in its summary rather than letting the 100% speak.

---

### Task 5 — human review, which found what the tests could not

**Prompt:** "Build the human-evaluation document. Rubric, all 12 playlists, verdicts."

**What I had to insist on.** The verdict column stays empty. An AI-authored "human evaluation"
is worse than none, because it looks exactly like a completed one. `docs/human_eval.md` now has
a model-authored review column, clearly labelled with its conflict of interest, and an empty
human column with the protocol for filling it in.

**What the exercise found anyway.** Two things, and neither was findable by the automated suite:

1. **A real bug.** `"i want to discover something obscure"` returned the identical playlist to
   `"play me something good"`. A profile of nothing but `mode: discovery` was being classified
   as having no scorable signal — but `score_song` in discovery mode awards a novelty score to
   every song, so it was perfectly rankable. The cold-start path was discarding the exact
   ordering the user had asked for. Fixed; it now returns the five least-popular tracks, ordered
   by novelty.

2. **A failure I chose not to fix.** A communal, uplifting gospel track ranks fourth in a
   playlist asked to be nocturnal and cinematic. It passes every automated check — inside the
   energy window, no repeated artist, correct length — and a listener notices immediately.
   The cause is that mood and tag *mismatch* is unrewarded but never penalised, so a song can
   accumulate energy and texture points while being the wrong feeling entirely. I left it,
   because it means changing the Module 3 scoring weights and that deserves its own
   measurement rather than a patch to make one case pass. It is logged as limitation 4 in the
   model card — and it is the same failure Module 3's own model card predicted in its Future
   Work section and I did not get to.

---

### Task 6 — writing it up, and one last bug

Writing the README surfaced the final defect, which says something about documentation as a
testing technique. Pasting the wind-down example in, I read the generated summary:

> 'Velvet Hours' by Nia Sol **leads** on energy 0.52 vs target 0.22 (+0.40), scoring 1.40.

Velvet Hours scored 1.40. The best match in that playlist scored 7.47. The narrator was using
`picks[0]` as "the lead", which is correct until an energy arc re-orders the list — after which
the first track is whatever the arc needed to open with, and in a wind-down list that is the
*loudest* song and often the weakest match. The summary was describing the playlist backwards.
It now names the highest-scoring song and explains why the list opens elsewhere.

**One thing I could not do.** Exporting the Mermaid diagrams to PNG needed a package install
that was not permitted in the session, so `diagrams/*.mmd` ship as source only. This is what the
brief asks for anyway — it explicitly says a PNG alone is insufficient and the source file is
required — and the render command is in the README for anyone who wants the image.

---

### The pattern, across eight defects

Every defect in this project turned up by **running the system**, seven of them from reading
its output and the eighth from a CI job going red. Not one came from reading the code. In each
case the component was individually correct and the seam between two components was wrong:
retrieval handing the planner a number it had no right to be confident about; the planner
handing the critic a profile that made every score zero; the arc re-orderer handing the
narrator a list whose first element no longer meant what the narrator assumed.

The eighth is worth a line of its own, because it is the one I would have sworn was fine. A
test asserting that 50 run ids are unique failed on one Python version and passed on the other
two, which looks like flakiness and was really a design fault: the id was a one-second
timestamp plus four hex characters, so two runs starting in the same second collided about 1.9%
of the time, and a collision meant the second run opening the first one's log file and erasing
it. The flaky test was right and my id was too narrow. Logs now open exclusively instead of
truncating, so even a collision cannot destroy evidence.

The AI was consistently strong at **structure and prose** — the BM25 index, the critic/repair
split, the notes themselves — and consistently optimistic about **how real inputs behave**:
real phrasings, degenerate profiles, and what happens on the second pass through a loop. It
also defaults to confidence. Left alone it produced a system that answered "play me something
good" with the same assured five-song list it gave a precise request, and nothing in the code
was wrong; the design was dishonest, and deciding what the system should do when it does not
know turned out to be a bigger share of the work than making it work when it does.

---

## Part 1 — Module 3 (VibeFinder 1.0)

---

## Agentic Workflow (SF8) — advanced song features

**What task did you give the agent?**

Expand `data/songs.csv` from the 10 starter rows to a catalog wide enough to actually test a
recommender, add new attribute columns beyond the starter's audio features, and update
`src/recommender.py` so the new columns are parsed and scored rather than ignored.

**Prompts used:**

- "Here is `data/songs.csv`. Generate 12 more rows in exactly this CSV format. Cover genres and
  moods that are completely absent from the current 10 — I want at least one each of afrobeats,
  hip hop, classical, metal, country, reggaeton, r&b, folk, drum and bass, gospel and house, and
  moods other than happy/chill/intense/relaxed/moody/focused. Keep energy, valence,
  danceability and acousticness on 0.0–1.0 and make them musically plausible for the genre
  (classical piano should not have acousticness 0.1)."
- "Add five columns to every row, old and new: `popularity` 0–100, `release_decade`,
  `mood_tags` as semicolon-separated descriptive tags, `language`, and `duration_sec`. Don't
  change the existing ten songs' original values."
- "Now update `load_songs` and `score_song` so the five new columns are read with the right
  types and can earn points. `mood_tags` should become a list, and tag matches should be worth
  less individually than a mood match but be able to add up."

**What did the agent generate or change?**

- `data/songs.csv`: 12 new rows (ids 11–22) and five new columns across all 22 rows
  (`popularity`, `release_decade`, `mood_tags`, `language`, `duration_sec`).
- `src/recommender.py`: `INT_COLUMNS` extended with `popularity` / `release_decade` /
  `duration_sec`, a `_split_tags` helper, and five new scoring terms (shared tags, decade
  match, novelty bonus, language match, length closeness).
- `src/main.py`: an `instrumental_study` profile that exercises `language` and `duration_sec`.

**What did you verify or fix manually?**

- **Type parsing.** I checked by hand that `load_songs()` returns `float` for energy and `int`
  for `tempo_bpm` / `popularity` / `release_decade` — the first version left everything as
  strings for the new columns, so `popularity / 100` would have thrown. There is now a test
  for it (`test_load_songs_converts_numbers_and_tags`).
- **Uncapped tag points.** The first scoring version awarded +0.4 per shared tag with no cap,
  which let a song with four matching tags out-earn a genre match. I added
  `min(weight * n, max_tag)` so tags can refine a ranking but never overturn it.
- **Plausibility of the generated data.** I corrected several values by hand: the generated
  metal track had acousticness 0.30, the classical piece had danceability 0.55, and two of the
  new songs had been given the artist name of an existing one.
- **Popularity scale.** The agent generated popularity values clustered in the 70s–90s, which
  would have made the `discovery` mode pointless. I spread them from 27 to 91.
- **A real bug in the length term.** The generated code computed the closeness correctly and
  then awarded `weights.duration` rather than `weights.duration * fit`, so every song received
  the full +0.50 regardless of length — a 352-second track scored the same as a 150-second one
  against a 150-second target. Nothing crashed and the suite was green; the only symptom was
  the explanation line `length 352s vs target 150s (+0.50)`, which I noticed while reading the
  table. Fixed, and covered by `test_duration_term_dies_off_outside_the_tolerance`.
- **"Instrumental" as a wildcard.** The first language rule let `instrumental` match any
  preference, on the theory that a song with no words suits everyone. That silently gave 8 of
  22 songs a free +0.60 for every user, so I made it an ordinary value that only matches a user
  who actually asked for it — there is a test for that too.
- **Backwards compatibility.** I checked that adding the two terms left all six pre-existing
  profiles' output byte-identical (they name neither preference, so the terms are skipped), and
  wrote `test_new_features_are_ignored_when_the_user_omits_them` to keep it that way.

---

## Design Pattern (SF10) — multiple scoring modes

**Which design pattern did you use?**

A lightweight **Strategy pattern**. Each ranking strategy is a frozen `ScoringMode` dataclass
holding one set of weights, and they live in the `SCORING_MODES` registry. `score_song` looks
its weights up through `get_mode()` instead of hard-coding numbers, so swapping strategy is a
string: `python -m src.main --mode energy_focused`.

**How did AI help you brainstorm or implement it?**

I attached `recommender.py` and asked for ways to support several ranking strategies without
duplicating the scoring maths. It offered three: (1) subclass a `Scorer` base class per
strategy, (2) pass a weights dict into `score_song`, (3) a registry of named weight objects.
It initially recommended (1), the textbook Strategy implementation with a class and a
`score()` method per mode. I went with (3) instead, because every one of my strategies differs
*only* in its numbers — five subclasses would have been five copies of the same function body
with different constants, which is exactly the duplication I was trying to avoid. The AI's
useful contribution was pointing out that whichever option I chose, the mode had to be
resolvable from a plain string so the CLI and the tests could name one without importing it.

**How does the pattern appear in your final code?**

- `ScoringMode` (frozen dataclass) and `SCORING_MODES` in `src/recommender.py`.
- `get_mode()` accepts either a name or a `ScoringMode`, so callers can pass either.
- `score_song(..., mode=...)` and `recommend_songs(..., mode=...)` thread it through; a mode can
  also be set per-profile via the `"mode"` key.
- `src/main.py` exposes the registry as `--mode` choices, so adding a sixth strategy means
  adding one entry to the dict and nothing else.
- `test_scoring_modes_change_the_winner` and `test_discovery_mode_rewards_unknown_songs` pin
  the behaviour.

---

## Diversity and Fairness Logic

**The prompt:**

"In `recommend_songs`, I want a rule that stops the top k being dominated by one artist or
genre. Penalise a song if an artist already appears in the list being built, and penalise it
less for a repeated genre. Where should this logic live — in `score_song` or in the ranking
step — and why?"

**What came back, and what I changed:**

The first suggestion applied the penalty inside `score_song`, which cannot work: `score_song`
sees one song and has no idea what else has been picked. When I pushed back it agreed and
proposed the greedy re-ranking loop that is now in `recommend_songs` — pick the best song,
record its artist and genre, then re-evaluate everyone else with `-1.50` per prior song by the
same artist and `-0.75` per prior song in the same genre, and repeat.

I kept the loop but changed two things. The penalty is **cumulative** rather than a one-off
flag, so a third song by the same artist is discounted twice as hard as the second. And the
penalty is written into the printed explanation (`diversity penalty (-0.75)`) rather than
applied silently — if the displayed score doesn't match the reasons above it, the output stops
being auditable, which is the whole premise of the project. `test_diversity_penalty_breaks_up_
repeated_artists` checks the before/after, and `--no-diversity` turns it off for comparison.

---

## Visual Summary Table

`render_table()` in `src/main.py` uses `tabulate` with `tablefmt="rounded_grid"` and wraps the
reasons column with `textwrap` so the explanation stays readable inside the cell. The import is
inside the function with an `ImportError` fallback to plain text, so the simulation still runs
if `tabulate` isn't installed — the AI's version imported it at module top level, which would
have made a formatting library a hard dependency of the logic.
