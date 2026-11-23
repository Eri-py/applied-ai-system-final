# VibeFinder 2.0 — an applied AI system that explains itself

[![tests](https://github.com/Eri-py/applied-ai-system-final/actions/workflows/ci.yml/badge.svg)](https://github.com/Eri-py/applied-ai-system-final/actions/workflows/ci.yml)

**You describe a situation in plain English. It builds a playlist, checks its own work, fixes
what it got wrong, and tells you how much to trust the result.**

```console
$ python -m src.app "my girlfriend dumped me"

--- RETRIEVED NOTES ----------------------------------------------------------
    8.23  Heartbreak, grief and sitting with a hard feeling  [context-heartbreak]

--- PLAYLIST -----------------------------------------------------------------
  #  title               artist          genre        energy    bpm  len      score    conf
---  ------------------  --------------  ---------  --------  -----  -----  -------  ------
  1  Paper Boats         Wren & Oak      folk           0.31     82  4:19      6.14    0.77
  2  Nocturne in Grey    Ilse Brandt     classical      0.19     64  5:52      6.1     0.76
  3  Library Rain        Paper Lanterns  lofi           0.35     72  2:48      2.55    0.32
  4  Spacewalk Thoughts  Orbit Bloom     ambient        0.28     60  5:11      2.44    0.3
  5  Velvet Hours        Nia Sol         r&b            0.52     74  3:41      2.37    0.3

--- CONFIDENCE ---------------------------------------------------------------
  0.77  [###############.....]  HIGH
```

That request contains no musical word at all — no genre, no mood, not even "song". The system
answers it because of a retrieval layer over a corpus of written listening notes, one of which
says that people in distress reliably choose sad music and that substituting cheerful songs
makes the output worse while appearing kind. The system reads that note, derives a low-energy
acoustic profile from it, and never offers a metal track.

---

## The project this extends

**Base project: Module 3 — [VibeFinder 1.0, a music recommender simulation](https://github.com/Eri-py/ai110-module3show-musicrecommendersimulation-starter).**

VibeFinder 1.0 was a content-based recommender you could read end to end. It loaded a 22-song
catalog from a CSV, scored every song against a hand-written taste profile (genre, mood, vibe
tags, energy, tempo, acousticness, decade, language, length), and printed a ranked top-k list
with the reason for every point it awarded. It had no machine learning on purpose — every
number traced back to a line in `src/recommender.py` — so that the places where real
recommenders quietly go wrong (filter bubbles, cold starts, popularity bias) were visible by
hand. Its interface was a fixed set of six Python dictionaries written by me.

**What it could not do:** accept a request from a human being. `{"genre": "lofi", "energy":
0.4}` is not how anyone describes what they want to hear, and the gap between "a rainy Sunday
morning" and `energy=0.35, acousticness>0.6, tempo≈78` is exactly the knowledge the original
project had nowhere to put.

### What 2.0 adds

| | VibeFinder 1.0 (Module 3) | VibeFinder 2.0 (this repo) |
|---|---|---|
| **Input** | A Python dict you edit by hand | Plain English |
| **Knowledge** | The 22-song CSV | The CSV **plus** a 14-note corpus of written listening knowledge, retrieved per request |
| **Planning** | None — you wrote the profile | Retrieval + Claude (or a deterministic planner) derives it |
| **Quality control** | Trust the score | A critic checks properties no score can express, and the agent repairs what fails |
| **Honesty** | A ranked list | A published confidence with four measured components, and a cold-start path that refuses to fake precision |
| **Safety** | None needed | Input screening, injection refusal, profile clamping, output sanitising |
| **Evidence** | 16 unit tests | 285 tests, 29 labelled evaluation cases, three experiments, JSONL run logs |

The Module 3 scoring engine is **unchanged and still central** — `src/recommender.py` is the
same file, and every playlist above is produced by its `score_song` and `recommend_songs`.
Everything new wraps it.

---

## Architecture

**[View both diagrams rendered →](diagrams/README.md)** (GitHub draws them inline.)

Source: [`diagrams/architecture.mmd`](diagrams/architecture.mmd) (the whole system) and
[`diagrams/agent_loop.mmd`](diagrams/agent_loop.mmd) (one real run as a sequence). Both are
Mermaid source. [`diagrams/README.md`](diagrams/README.md) is generated from them by
`python diagrams/build_readme.py` and gated in CI, so it cannot drift. To export an image:
`mmdc -i diagrams/architecture.mmd -o assets/architecture.png -b transparent -s 2`.

The request flows through five stages.

**1 — Guardrails** (`src/guardrails.py`). Screen before spending anything: empty, too short,
overlong (truncated, not refused), and instruction-override attempts, matched against a
unicode-normalised copy so full-width lookalikes don't slip through. Refusals are a returned
value, not an exception, because the caller has to log them and the evaluation harness has to
assert on them.

**2 — Plan** (`src/retrieval.py` + `src/llm.py`). A dependency-free BM25 index retrieves the
most relevant listening notes. Each note carries two things: **prose**, handed to Claude as
grounding context, and a **`hints:` block** of structured defaults that seeds the profile
directly. That second form is what makes retrieval load-bearing rather than decorative — the
catalog knows a song's tempo, but nothing in it says which tempo a rainy Sunday wants. The
planner then proposes a profile, which is clamped into the ranges `score_song` assumes.

**3 — Act** (`src/agent.py`). The Module 3 recommender scores and ranks the catalog. If the
profile has no scorable preference at all, a separate cold-start path returns deliberate
coverage instead.

**4 — Check and repair** (`src/agent.py`). A critic tests what no single song score can
express — a repeated artist, one genre flooding the list, a song outside the energy window,
total running time against a requested duration, and whether the energy arc matches the shape
the request implies. Each failure has one narrow registered repair. Bounded at five attempts,
so an unsatisfiable constraint ends with the failure reported rather than looping.

**5 — Report** (`src/confidence.py` + `src/app.py`). A confidence score from four measured
components, a summary, and every repair the agent made, all printed. Every event also lands in
a JSONL run log that the evaluation harness reads back.

### Where the model is, and where it deliberately is not

A model is used for exactly two jobs: turning free text into a structured profile, and writing
the closing paragraph. **Retrieval, scoring, ranking, checking and repairing are all
deterministic Python.** That split is the main architectural decision in the project: the parts
that must be reproducible and testable don't call a model, and the parts a model is genuinely
better at don't pretend to be deterministic. It is why `python -m src.app "music for the gym"`
returns a byte-identical playlist every time, and why the repairs can be unit-tested.

`src/tool_loop.py` contains the opposite arrangement — a genuine Claude tool-use loop where the
model decides which of the four tools to call and when the playlist is good enough — so the two
designs can be compared rather than argued about. Run it with `--tool-loop`.

### Files

| Path | Role |
|---|---|
| `src/recommender.py` | **Module 3, unchanged.** Scoring, ranking, diversity penalties, five scoring modes. |
| `src/retrieval.py` | BM25 index over the notes; frontmatter parsing; hint merging. |
| `src/guardrails.py` | Input screening, profile clamping, output sanitising. |
| `src/llm.py` | Claude backend, deterministic offline backend, resilient wrapper. |
| `src/agent.py` | The tools, the critic, the repairs, the loop. |
| `src/confidence.py` | The four-component confidence model. |
| `src/tool_loop.py` | Model-driven tool-use loop, for comparison. |
| `src/obs.py` | JSONL run logging. |
| `src/app.py` | CLI and rendering. |
| `src/main.py` | **Module 3, unchanged.** The original six-profile demo. |
| `data/notes/*.md` | The retrieval corpus: 14 notes, ~3,150 words. |
| `data/songs.csv` | **Module 3, unchanged.** 22 songs, 15 columns. |
| `evaluation/` | 29 labelled cases and the harness that runs them. |
| `tests/` | 285 tests. |

---

## Setup

Needs Python 3.10+. **No API key is required** — the system runs fully offline on a
deterministic planner, and all 285 tests and all published evaluation numbers reproduce that
way.

```bash
git clone https://github.com/Eri-py/applied-ai-system-final.git
cd applied-ai-system-final

python -m venv .venv
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\activate             # Windows

pip install -r requirements.txt
```

Verify the install:

```bash
python -m pytest -q                # expect: 285 passed
python -m src.app "something for the gym"
```

### Optional: the live Claude path

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # Windows: $env:ANTHROPIC_API_KEY="sk-ant-..."
python -m src.app "something for a long drive"            # Claude plans the profile
python -m src.app "something for a long drive" --tool-loop  # Claude drives the tools
```

The planner line at the top of every run says which backend produced it. With a key present,
any API failure — expired key, rate limit, network drop, refusal — degrades to the
deterministic planner, reports the reason, and reduces the published confidence by 10%.

### Commands

```bash
python -m src.app "<request>"            # build a playlist
  -k 3                                   # force a song count
  --mode discovery                        # force a scoring strategy
  --offline                               # ignore any API key
  --no-retrieval                          # the RAG ablation (see below)
  --tool-loop                             # let Claude drive the tools (needs a key)
  --verbose                               # trace every event to stderr
  --json                                  # machine-readable output

python -m evaluation.run_eval            # 29 cases + three experiments
python -m evaluation.run_eval --write    # regenerate EVALUATION.md
python -m src.main                       # the original Module 3 demo, unchanged
bash assets/regenerate.sh                # regenerate the committed command output
python diagrams/build_readme.py          # regenerate the rendered diagram page
```

Exit codes: `0` playlist produced and passed its checks, `1` constraints left unsatisfied,
`2` refused by a guardrail.

---

## Sample interactions

Three runs below, pasted verbatim. Six more — including both refusals and the ablation side by
side — are in [`assets/sample-output.md`](assets/sample-output.md), regenerable with
`bash assets/regenerate.sh` and verified byte-identical across runs.

### 1. A well-specified request

Retrieval supplies the numbers the request doesn't state. "Gentle" is the only intensity word
given; the energy target of 0.30, the 78 bpm, the acoustic preference and the vibe tags all
come from the rainy-day note.

```console
$ python -m src.app "something gentle for a rainy sunday morning"

VibeFinder 2.0  |  request: "something gentle for a rainy sunday morning"
planner: offline (deterministic planner; no ANTHROPIC_API_KEY found)  |  run: <run-id>

--- RETRIEVED NOTES ----------------------------------------------------------
    9.21  Rainy days, grey weather and staying in  [context-rainy-day]
    4.59  Mornings, waking up and starting the day  [context-morning]

--- DERIVED PROFILE ----------------------------------------------------------
  arc              flat
  energy           0.3
  k                5
  likes_acoustic   True
  mode             mood_first
  mood             chill
  mood_tags        ['rainy', 'nostalgic', 'cosy']
  tempo_bpm        78

  why: Matched the note 'Rainy days, grey weather and staying in'; which set arc, likes_acoustic, mode, mood_tags, tempo_bpm; and the request itself specified energy, mood.

--- PLAYLIST -----------------------------------------------------------------
  #  title                artist          genre      energy    bpm  len      score    conf
---  -------------------  --------------  -------  --------  -----  -----  -------  ------
  1  Library Rain         Paper Lanterns  lofi         0.35     72  2:48      6.14    0.8
  2  Spacewalk Thoughts   Orbit Bloom     ambient      0.28     60  5:11      4.75    0.62
  3  Midnight Coding      LoRoom          lofi         0.42     78  2:34      4.68    0.61
  4  Coffee Shop Stories  Slow Stereo     jazz         0.37     90  4:28      3.47    0.45
  5  Paper Boats          Wren & Oak      folk         0.31     82  4:19      3.23    0.42

  total running time: 19 min 20 sec

--- WHY EACH SONG ------------------------------------------------------------
  1. Library Rain (6.14)
       - mood match: chill (+2.50)
       - shared vibe: nostalgic, rainy (+1.20)
       - energy 0.35 vs target 0.30 (+0.90)
       - tempo 72 vs target 78 bpm (+0.85)
       - acoustic texture (0.86 acousticness) (+0.69)

--- AGENT LOOP ---------------------------------------------------------------
  attempt 1: k=5 order=score diversify=True -> PASS

--- CONFIDENCE ---------------------------------------------------------------
  0.80  [################....]  HIGH
       constraints    1.00
       margin         0.71
       retrieval      1.00
       specificity    0.56
```

### 2. The agent catching and fixing its own mistake

"Half an hour" sizes the playlist to eight tracks; "wind down" demands a descending energy
arc. The first attempt is musically right and ordered wrong. The critic catches it — an
ordering failure is invisible in per-song scores and obvious to a listener in fifteen seconds —
and the repair re-orders the list.

```console
$ python -m src.app "half an hour of lo-fi to wind down"

--- PLAYLIST -----------------------------------------------------------------
  #  title                artist          genre        energy    bpm  len      score    conf
---  -------------------  --------------  ---------  --------  -----  -----  -------  ------
  1  Velvet Hours         Nia Sol         r&b            0.52     74  3:41      1.4     0.15
  2  Dust Road Home       Hallie Rae      country        0.45     96  3:56      1.28    0.14
  3  Midnight Coding      LoRoom          lofi           0.42     78  2:34      5.47    0.58
  4  Coffee Shop Stories  Slow Stereo     jazz           0.37     90  4:28      2.31    0.24
  5  Library Rain         Paper Lanterns  lofi           0.35     72  2:48      6.63    0.7
  6  Paper Boats          Wren & Oak      folk           0.31     82  4:19      2.07    0.22
  7  Spacewalk Thoughts   Orbit Bloom     ambient        0.28     60  5:11      7.47    0.79
  8  Nocturne in Grey     Ilse Brandt     classical      0.19     64  5:52      3.27    0.34

  total running time: 32 min 49 sec

--- AGENT LOOP ---------------------------------------------------------------
  attempt 1: k=8 order=score diversify=True -> FAIL
       x arc_violation
       > re-ordered the playlist into a descend energy arc
  attempt 2: k=8 order=descend diversify=True -> PASS

--- CONFIDENCE ---------------------------------------------------------------
  0.79  [################....]  HIGH
       constraints    0.95
       margin         0.50
       retrieval      0.90
       specificity    0.89

--- SUMMARY ------------------------------------------------------------------
  8 songs covering ambient, classical, country, folk, jazz, lofi, r&b. The
  strongest match is 'Spacewalk Thoughts' by Orbit Bloom, on mood match:
  chill (+2.50), scoring 7.47. The list opens with 'Velvet Hours' instead,
  to shape the energy arc the request asked for.
```

The full JSONL log for this exact run is committed at
[`assets/sample-run-winddown.jsonl`](assets/sample-run-winddown.jsonl) — 15 events, each
timed. Note also what the system does *not* hide: tracks 1 and 2 scored 1.40 and 1.28 against
a best match of 7.47. The duration constraint forced them in, and their per-song confidence
(0.15, 0.14) says so.

### 3. A request that specifies nothing

The dangerous case. A playlist built from "play me something good" looks exactly like one built
from a precise request — five songs, five explanations, same formatting — and the thin one is
dangerous precisely because it is invisible. So the system refuses to fake it: every song would
score 0.00 against an empty profile, so instead of ranking by a tie-break dressed up as a
ranking, it returns coverage across the catalog and publishes a low confidence.

```console
$ python -m src.app "play me something good"

--- RETRIEVED NOTES ----------------------------------------------------------
    5.72  Vague requests, cold starts and asking for less  [theory-cold-start]
    1.82  Deep work, studying and concentration  [context-focus]

--- DERIVED PROFILE ----------------------------------------------------------
  k                5
  mode             balanced

  why: Matched the note 'Vague requests, cold starts and asking for less'; which set mode.

--- PLAYLIST -----------------------------------------------------------------
  #  title               artist          genre        energy    bpm  len      score    conf
---  ------------------  --------------  ---------  --------  -----  -----  -------  ------
  1  Nocturne in Grey    Ilse Brandt     classical      0.19     64  5:52         0       0
  2  Midnight Coding     LoRoom          lofi           0.42     78  2:34         0       0
  3  Morning Praise      The Upper Room  gospel         0.71    108  4:48         0       0
  4  Basement Warehouse  Kari Vex        house          0.88    126  6:42         0       0
  5  Iron Lungs          Blackvault      metal          0.98    168  4:34         0       0

  total running time: 24 min 30 sec

--- CONFIDENCE ---------------------------------------------------------------
  0.38  [########............]  LOW
       constraints    1.00
       margin         0.00
       retrieval      0.71
       specificity    0.00
  note: the request specified very little, so the ranking rests on default weights
  note: cold start: the request set no scorable preference, so these songs were chosen to span the catalog rather than to match a profile
```

Note the second retrieved note scored 1.82 and contributed **nothing**. The focus note defines
an energy target of 0.40 and an instrumental-only filter, and an earlier version of this system
inherited both — so "play me something good" came back as a confident-looking focus playlist.
Hints are now ignored below 35% of the top hit's score, which is why the profile above is two
lines long instead of eight.

Five genres, energy from 0.19 to 0.98. Deliberately incoherent, and honest about why.

---

## Design decisions

**The loop is Python; the model plans.** The alternative — hand Claude the tools and let it
drive — is implemented too (`src/tool_loop.py`), and the comparison is the point. A
model-driven loop handles requests no keyword rule anticipates; a Python loop is reproducible,
unit-testable, free, and cannot forget to call the validator. I made the Python loop the
default because the properties I most needed were testability and reproducibility, and kept
the model-driven version so the trade-off is visible rather than asserted. *Trade-off:* the
default planner's coverage is bounded by a hand-written vocabulary, and a request phrased
outside it degrades to whatever retrieval alone can supply.

**Retrieval carries structured hints, not just prose.** The textbook RAG shape is "retrieve
passages, stuff them in a prompt". That shape cannot work offline and makes retrieval's
contribution unmeasurable. Giving each note a `hints:` block means retrieval changes the
*profile*, which changes the scoring, which changes the output — a causal path I can ablate
and measure. The ablation below is only possible because of this choice. *Trade-off:* the
hints are hand-authored, so the corpus is a maintained artefact, not a scraped one.

**The critic is separate from the scorer.** `score_song` judges one song in isolation and
structurally cannot see "three songs by the same artist" or "this list ends louder than it
starts". Those are properties of the set. Keeping them in a separate critic means I can add a
constraint without touching the Module 3 weights, and it is where most real playlist failures
turned out to live. *Trade-off:* two places now encode what "good" means, and they can drift —
the critic's energy window is deliberately pinned to the scorer's `energy_tolerance` to limit
that.

**Confidence is measured, never self-reported.** Asking a model "how confident are you?"
produces a number correlated with its own fluency. All four components here are computed from
the run's own data. *Trade-off:* the weights are my judgement, and the calibration experiment
shows the score is much better at "was I told enough?" than at "did I get this right?".

**Refusals are values, not exceptions.** Every guardrail returns a verdict the caller logs and
the harness asserts on. Exceptions would have made the adversarial cases untestable.

**Off-domain is decided after retrieval, not before.** Judging on vocabulary alone refused
"my girlfriend dumped me" — a request with no musical word that the corpus answers precisely.
Refusal now needs *both* signals absent: no music vocabulary *and* no keyword-backed note
match. *Trade-off:* the boundary is approximate, and it is biased toward accepting, because
letting an odd request through costs a low-confidence playlist while a false refusal costs the
feature.

**The offline backend is a real planner, not a stub.** It had to be, for the repo to be
runnable, testable and CI-verifiable without credentials. It is also what makes the
reproducibility experiment meaningful.

---

## Testing summary

**285 unit tests pass; 29 of 29 labelled evaluation cases pass; reproducibility is 29/29
across three runs each. With the retrieval layer switched off, the pass rate falls to 55% and
mean confidence from 0.65 to 0.21 — 13 cases fail that otherwise pass. Confidence separates
vague requests from specified ones by 0.34, but separates passing from failing runs by only
0.05, which is a real weakness.** Full report: [EVALUATION.md](EVALUATION.md).

| Measurement | Result |
|---|---|
| Unit tests (`pytest`) | 285 passed |
| Labelled cases (`evaluation/run_eval.py`) | 29/29 passed, mean confidence 0.65 |
| Reproducibility (3 runs per case) | 29/29 byte-identical |
| **Ablation: retrieval on** | **100% pass, mean confidence 0.65** |
| **Ablation: retrieval off** | **55% pass, mean confidence 0.21** |
| Calibration: thin vs specified requests | 0.35 vs 0.69 (gap 0.34) |
| Calibration: failing vs passing runs | gap 0.05 — weak |
| Human review of 12 playlists | 8 pass, 3 weak, 1 fail — scored against a 4-part rubric ([docs/human_eval.md](docs/human_eval.md)) |

### What worked

The check-and-repair loop earns its place. Arc violations, impossible language constraints and
duration mismatches all get caught and fixed on real requests, and the repairs are visible in
the output rather than buried. The ablation gave the clearest result in the project: a 45-point
pass-rate swing is not a subtle contribution, and it settles the question of whether the RAG
layer is doing work.

### What didn't

**The 29/29 is a regression guard, not evidence of quality,** and EVALUATION.md says so. The
cases were written alongside the fixes they describe — I found six real defects by running the
system by hand and added the case that would have caught each one. A suite that passes
everything it was written against proves only that it still passes.

The honest failures are these:

1. **Confidence doesn't predict wrongness.** It predicts under-specification. Two of its four
   components collapse together when retrieval is weak, so passing and failing runs score
   within 0.05 of each other in that regime. Fixing it needs held-out human judgements to
   regress against, which the project doesn't have.
2. **Human review found a failure the automated suite cannot see.** A gospel track ranks into
   a night-drive playlist (case 5 in `docs/human_eval.md`) and is genuinely jarring. It passes
   every automated check: inside the energy window, no repeated artist, right length. Mood and
   tag mismatch is unrewarded but never *penalised*, so a song can accumulate energy and
   texture points while being the wrong feeling entirely. Not fixed, because it is a change to
   the Module 3 scoring weights and deserves its own measurement rather than being slipped in
   to make one case pass.
3. **A hard duration target can outrank quality.** Sample interaction 2 above ships two tracks
   scoring 1.40 and 1.28 to reach 30 minutes. Visible in the per-song confidence, but still
   shipped.
4. **The live Claude path is unverified end to end.** Its request shape is pinned by tests
   with a fake client — model id, closed schema, grounding content, refusal handling, fallback
   retry — but no test in this repo has called the real API, because the machine it was built
   on had no key. `EVALUATION.md` states this rather than implying coverage it doesn't have.

### Defects found by testing, and fixed

Each of these was found by running the system, not by reading it, and each has a regression
test:

| Defect | Fix |
|---|---|
| A faint retrieval hit injected invented numeric targets into a vague request | Hints now floored at 35% of the top hit's score |
| The heartbreak note didn't retrieve for common phrasings ("dumped", "girlfriend") | Keywords extended |
| A cold-start request drove the repair loop to exclude almost the whole catalog chasing zero scores | Explicit cold-start path; zero-score exclusion only when something better exists |
| Off-domain refusal rejected "my girlfriend dumped me" | Decision deferred until after retrieval, needs both signals absent |
| An unset `-k` read as an explicit song count, silently disabling duration sizing | Check the value, not the key |
| `mode: discovery` alone was misread as having no scorable signal, discarding the novelty ranking the user asked for | Scoring modes with a novelty weight now count as signal |
| The summary named the opening track as the best match — backwards after an arc re-order | Name the highest-scoring song, and say why the list opens elsewhere |

---

## Reflection

The thing I'd carry into any future system is that **the interesting failures live between the
components, not inside them.** Every unit was correct when I wrote it. The bugs were all
seams: retrieval handing the planner a number it had no right to be confident about, the
planner handing the critic a profile that made every score zero, the arc re-orderer handing the
narrator a list whose first element no longer meant what the narrator assumed. Unit tests
found none of those. Running the thing and reading the output found all of them.

The second thing is that **the honest answer is a feature, and it has to be designed in.** The
cold-start path, the published confidence and the relaxation notes all exist because the
default behaviour of a system like this is to produce a confident-looking answer regardless of
whether it has grounds for one — and that failure is invisible to the user, which makes it the
worst kind. Deciding what the system should do when it doesn't know turned out to be a larger
share of the work than making it work when it does.

> The graded responsible-AI reflection — how I collaborated with AI, one suggestion I accepted
> and one I rejected, bias analysis and the system's limitations — is in
> **[model_card.md](model_card.md)**, with the full collaboration log in
> **[ai_interactions.md](ai_interactions.md)**. Portfolio copy and a five-minute demo script
> are in **[docs/portfolio.md](docs/portfolio.md)**.

---

## Repository map

```
applied-ai-system-final/
├── README.md                  this file
├── EVALUATION.md              generated test + experiment report
├── model_card.md              intended use, biases, limitations, reflection
├── ai_interactions.md         AI collaboration log
├── requirements.txt
├── data/
│   ├── songs.csv              Module 3 catalog, unchanged
│   └── notes/                 the retrieval corpus (14 notes)
├── src/                       the system (see Files above)
├── evaluation/                cases.py, run_eval.py, results.json
├── tests/                     285 tests
├── diagrams/
│   ├── architecture.mmd       Mermaid source — the whole system
│   ├── agent_loop.mmd         Mermaid source — one real run
│   ├── README.md              both diagrams, rendered by GitHub (generated)
│   └── build_readme.py        generates that page from the .mmd sources
├── assets/
│   ├── sample-output.md       nine reproducible command outputs
│   ├── sample-run-winddown.jsonl   a full JSONL run log
│   └── regenerate.sh          regenerates sample-output.md
├── docs/
│   ├── human_eval.md          human evaluation: 12 scored playlists + findings
│   ├── rubric_coverage.md     requirement-by-requirement coverage map
│   ├── portfolio.md           portfolio copy and a demo script
│   └── model_card_v1.md       the Module 3 model card, preserved
└── .github/workflows/ci.yml   tests + evaluation + report staleness check
```

---

Built for CodePath AI110, Module 5 — *Show What You Know: Applied AI System*.
Extends [Module 3: VibeFinder 1.0](https://github.com/Eri-py/ai110-module3show-musicrecommendersimulation-starter).
