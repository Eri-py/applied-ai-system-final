# AI Interactions Log

> **Stretch features only.** Core-project AI use (research, dataset generation, scoring
> critique) is summarised in section 9 of `model_card.md`. This file covers the three stretch
> features I attempted: advanced song features (SF8), multiple scoring modes via a design
> pattern (SF10), and the diversity/fairness penalty.

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
- "Add three columns to every row, old and new: `popularity` 0–100, `release_decade`, and
  `mood_tags` as semicolon-separated descriptive tags. Don't change the existing ten songs'
  original values."
- "Now update `load_songs` and `score_song` so the three new columns are read with the right
  types and can earn points. `mood_tags` should become a list, and tag matches should be worth
  less individually than a mood match but be able to add up."

**What did the agent generate or change?**

- `data/songs.csv`: 12 new rows (ids 11–22) and three new columns across all 22 rows.
- `src/recommender.py`: `INT_COLUMNS` extended with `popularity` / `release_decade`, a
  `_split_tags` helper, and three new scoring terms (shared tags, decade match, novelty bonus).

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
