# 🎵 VibeFinder 1.0 — Music Recommender Simulation

**VibeFinder 1.0** is a content-based music recommender you can read end to end. It loads a
22-song catalog from a CSV, compares every song against a written-down "taste profile"
(genre, mood, vibe tags, energy, tempo, acoustic preference, decade), gives each song a
numeric score, and prints a ranked top-k list **with the reason for every point it awarded**.

There is no machine learning here on purpose. Every number in the output can be traced back
to a line in `src/recommender.py`, which is the whole point: it makes the places where a real
recommender would quietly go wrong — filter bubbles, cold starts, popularity bias — visible.

## Architecture

| File | Role |
|------|------|
| `data/songs.csv` | The catalog: 22 songs, 13 columns. |
| `src/recommender.py` | All the logic: `load_songs`, `score_song`, `recommend_songs`, the `ScoringMode` registry, and the `Song` / `UserProfile` / `Recommender` object layer. |
| `src/main.py` | CLI. Runs six taste profiles, five scoring modes, prints a table per profile. |
| `tests/test_recommender.py` | 13 `pytest` tests over the scoring and ranking rules. |
| `model_card.md` | Intended use, data, biases, evaluation, reflection. |

---

## How The System Works

### What real platforms do

Spotify and YouTube do not run on one algorithm. They blend at least two families:

- **Collaborative filtering** asks *"who else behaves like you?"*. It ignores what a song
  sounds like and looks only at the behaviour matrix — likes, skips, repeats, saves, playlist
  co-occurrence. If a thousand people who play the songs you play also play a song you have
  never heard, that song gets pushed to you. It is powerful because taste is social, but it is
  useless for a song nobody has played yet (the **cold-start** problem), and it amplifies what
  is already popular.
- **Content-based filtering** asks *"what is this song like?"*. It compares attributes — genre,
  tempo, energy, valence, acousticness, and in modern systems the raw audio embedding — against
  a profile of what the user already likes. It can recommend a song released five minutes ago,
  but it tends to keep handing you more of the same thing, which is where **filter bubbles**
  come from.

The real data involved is wider than either: explicit signals (likes, follows, saves), implicit
signals (skips in the first 30 seconds, repeats, completion rate, time of day, device), audio
features (tempo, key, loudness, energy, danceability), and text (genre tags, playlist titles,
lyrics).

**VibeFinder is purely content-based**, because that is the half you can actually inspect by
hand. It has no users, so it has no behaviour to collaborate on.

### What my version prioritises

A `Song` uses: `genre`, `mood`, `mood_tags`, `energy`, `tempo_bpm`, `acousticness`,
`popularity`, `release_decade` (and carries `valence` / `danceability` in the data for future
work). A `UserProfile` stores: `favorite_genre`, `favorite_mood`, `favorite_tags`,
`target_energy`, `target_tempo`, `likes_acoustic`, `favorite_decade`, and the scoring `mode`.

The order of importance is deliberate: **genre is the strongest single signal, energy is the
strongest numeric one, and mood sits between them.** Genre is how people actually describe
taste out loud ("I'm a rock person"), but energy is what makes a song usable *right now* — the
same person wants 0.9 energy in the gym and 0.3 energy at midnight. So genre wins a tie, but a
song two genres away with exactly the right energy can still beat a same-genre song with the
wrong one.

### The Algorithm Recipe (`balanced` mode)

| Rule | Points | Why |
|------|--------|-----|
| Exact genre match | **+2.00** | Strongest declared signal. |
| Related genre (shares a word, e.g. `indie pop` ~ `pop`) | **+1.00** | The catalog mixes broad and narrow labels; half credit is fairer than zero. |
| Mood match | **+1.00** | Mood is coarse — only six values — so it is worth less than genre. |
| Each shared vibe tag | **+0.40**, capped at **+1.20** | Fine-grained separation between two songs with the same headline mood. |
| Energy closeness | **+1.50 × (1 − gap / 0.5)**, floored at 0 | A *distance* score, not "higher is better". |
| Tempo closeness (only if the user gave a target) | **+1.00 × (1 − gap / 40 bpm)**, floored at 0 | Same idea in BPM. |
| Acoustic fit | **+0.80 × acousticness** if they like acoustic, else **+0.80 × (1 − acousticness)** | Turns a yes/no preference into a slider. |
| Decade match | **+0.50** | Small nudge, never decisive. |
| Same artist already picked | **−1.50 each time** | Diversity penalty, applied during ranking. |
| Same genre already picked | **−0.75 each time** | Diversity penalty, applied during ranking. |

**Why energy is a distance score.** The naive version — `score += song["energy"]` — means the
loudest song in the catalog wins every single profile. The fix is to score the *gap*:
`1.5 × (1 − |song_energy − target_energy| / 0.5)`. A user who wants 0.40 gets full marks for a
0.40 song and nothing for a 0.95 one. Tolerance `0.5` means the term dies out once a song is
half the scale away, so energy can order the near-misses without ever out-shouting genre.

**Scoring rule vs ranking rule.** They answer different questions. The *scoring rule*
(`score_song`) is a judge: it looks at one song in isolation and returns a number plus the
reasons behind it. It knows nothing about the other songs. The *ranking rule*
(`recommend_songs`) is a referee: it runs the judge over the whole catalog, sorts by score, and
decides what the user actually sees — how many results, how ties break, and whether the list as
a whole is any good. Diversity only exists at the ranking level, because "too many songs by
the same artist" is not a property any single song has. Splitting them also means I can change
the weights without touching the ranking, and add the diversity penalty without touching the
maths.

### Data flow

```
data/songs.csv ──load_songs()──> [ {song dict}, ... ]   (numbers parsed, tags split)
                                        │
user profile dict ──────────────────────┤
                                        ▼
                            for every song: score_song()
                            → (score, ["genre match: pop (+2.00)", ...])
                                        │
                                        ▼
                  recommend_songs(): sorted() desc, then greedy
                  re-ranking with artist/genre diversity penalties
                                        │
                                        ▼
                      top k (song, score, explanation) → table
```

### Biases I expected before building it

- Genre at +2.00 would dominate a 22-song catalog and bury perfect mood/energy matches in
  other genres.
- Broad labels (`pop`) would beat narrow ones (`indie pop`, `bedroom pop`) for no musical reason.
- A user whose target energy is near 0.5 would match almost everything; a user at 0.1 or 1.0
  would match almost nothing, because the catalog is bunched in the middle.

All three showed up, though the third was milder than I expected — the catalog is wide enough
that even a 0.95 target still finds 15 songs inside the energy window. See the experiments
below and the model card.

---

## Getting Started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Mac or Linux
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### Run

```bash
python -m src.main                                   # all six profiles, balanced mode
python -m src.main --profile chill_lofi              # one profile
python -m src.main --mode energy_focused             # a different scoring strategy
python -m src.main --no-diversity -k 10              # raw ranking, ten results
python -m pytest                                     # the tests
```

Modes: `balanced`, `genre_first`, `mood_first`, `energy_focused`, `discovery`.
Profiles: `happy_pop`, `chill_lofi`, `intense_rock`, `sad_banger`, `empty`, `unknown_genre`.

---

## Sample Recommendation Output

`python -m src.main --profile happy_pop`:

```
=== High-Energy Pop — the starter profile ===
Profile: genre=pop, mood=happy, energy=0.8, likes_acoustic=False, mood_tags=['sunny', 'uplifting']
Mode: balanced | diversity penalty: on

╭─────┬────────────────┬───────────────┬───────────┬─────────┬──────────┬─────────┬───────────────────────────────────────────────╮
│   # │ Title          │ Artist        │ Genre     │ Mood    │   Energy │   Score │ Why                                           │
├─────┼────────────────┼───────────────┼───────────┼─────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   1 │ Sunrise City   │ Neon Echo     │ pop       │ happy   │     0.82 │    5.90 │ genre match: pop (+2.00); mood match: happy   │
│     │                │               │           │         │          │         │ (+1.00); shared vibe: sunny, uplifting        │
│     │                │               │           │         │          │         │ (+0.80); energy 0.82 vs target 0.80 (+1.44);  │
│     │                │               │           │         │          │         │ produced texture (0.18 acousticness) (+0.66)  │
├─────┼────────────────┼───────────────┼───────────┼─────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   2 │ Rooftop Lights │ Indigo Parade │ indie pop │ happy   │     0.76 │    4.70 │ related genre: indie pop ~ pop (+1.00); mood  │
│     │                │               │           │         │          │         │ match: happy (+1.00); shared vibe: sunny,     │
│     │                │               │           │         │          │         │ uplifting (+0.80); energy 0.76 vs target 0.80 │
│     │                │               │           │         │          │         │ (+1.38); produced texture (0.35 acousticness) │
│     │                │               │           │         │          │         │ (+0.52)                                       │
├─────┼────────────────┼───────────────┼───────────┼─────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   3 │ Verano Perdido │ Luz Caliente  │ reggaeton │ happy   │     0.85 │    3.46 │ mood match: happy (+1.00); shared vibe: sunny │
│     │                │               │           │         │          │         │ (+0.40); energy 0.85 vs target 0.80 (+1.35);  │
│     │                │               │           │         │          │         │ produced texture (0.11 acousticness) (+0.71)  │
├─────┼────────────────┼───────────────┼───────────┼─────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   4 │ Lagos Two Step │ Ayo Komolafe  │ afrobeats │ happy   │     0.78 │    3.45 │ mood match: happy (+1.00); shared vibe: sunny │
│     │                │               │           │         │          │         │ (+0.40); energy 0.78 vs target 0.80 (+1.44);  │
│     │                │               │           │         │          │         │ produced texture (0.24 acousticness) (+0.61)  │
├─────┼────────────────┼───────────────┼───────────┼─────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   5 │ Gym Hero       │ Max Pulse     │ pop       │ intense │     0.93 │    3.12 │ genre match: pop (+2.00); energy 0.93 vs      │
│     │                │               │           │         │          │         │ target 0.80 (+1.11); produced texture (0.05   │
│     │                │               │           │         │          │         │ acousticness) (+0.76); diversity penalty      │
│     │                │               │           │         │          │         │ (-0.75)                                       │
╰─────┴────────────────┴───────────────┴───────────┴─────────┴──────────┴─────────┴───────────────────────────────────────────────╯
```

`python -m src.main --profile chill_lofi`:

```
=== Chill Lofi — studying at 1am ===
Profile: genre=lofi, mood=chill, energy=0.38, likes_acoustic=True, mood_tags=['sleepy', 'nostalgic']
Mode: balanced | diversity penalty: on

╭─────┬─────────────────────┬────────────────┬─────────┬─────────┬──────────┬─────────┬────────────────────────────────────────────────╮
│   # │ Title               │ Artist         │ Genre   │ Mood    │   Energy │   Score │ Why                                            │
├─────┼─────────────────────┼────────────────┼─────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   1 │ Library Rain        │ Paper Lanterns │ lofi    │ chill   │     0.35 │    5.90 │ genre match: lofi (+2.00); mood match: chill   │
│     │                     │                │         │         │          │         │ (+1.00); shared vibe: nostalgic, sleepy        │
│     │                     │                │         │         │          │         │ (+0.80); energy 0.35 vs target 0.38 (+1.41);   │
│     │                     │                │         │         │          │         │ acoustic texture (0.86 acousticness) (+0.69)   │
├─────┼─────────────────────┼────────────────┼─────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   2 │ Midnight Coding     │ LoRoom         │ lofi    │ chill   │     0.42 │    5.00 │ genre match: lofi (+2.00); mood match: chill   │
│     │                     │                │         │         │          │         │ (+1.00); shared vibe: nostalgic, sleepy        │
│     │                     │                │         │         │          │         │ (+0.80); energy 0.42 vs target 0.38 (+1.38);   │
│     │                     │                │         │         │          │         │ acoustic texture (0.71 acousticness) (+0.57);  │
│     │                     │                │         │         │          │         │ diversity penalty (-0.75)                      │
├─────┼─────────────────────┼────────────────┼─────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   3 │ Spacewalk Thoughts  │ Orbit Bloom    │ ambient │ chill   │     0.28 │    3.34 │ mood match: chill (+1.00); shared vibe: sleepy │
│     │                     │                │         │         │          │         │ (+0.40); energy 0.28 vs target 0.38 (+1.20);   │
│     │                     │                │         │         │          │         │ acoustic texture (0.92 acousticness) (+0.74)   │
├─────┼─────────────────────┼────────────────┼─────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   4 │ Coffee Shop Stories │ Slow Stereo    │ jazz    │ relaxed │     0.37 │    2.58 │ shared vibe: nostalgic (+0.40); energy 0.37 vs │
│     │                     │                │         │         │          │         │ target 0.38 (+1.47); acoustic texture (0.89    │
│     │                     │                │         │         │          │         │ acousticness) (+0.71)                          │
├─────┼─────────────────────┼────────────────┼─────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   5 │ Dust Road Home      │ Hallie Rae     │ country │ relaxed │     0.45 │    2.28 │ shared vibe: nostalgic (+0.40); energy 0.45 vs │
│     │                     │                │         │         │          │         │ target 0.38 (+1.29); acoustic texture (0.74    │
│     │                     │                │         │         │          │         │ acousticness) (+0.59)                          │
╰─────┴─────────────────────┴────────────────┴─────────┴─────────┴──────────┴─────────┴────────────────────────────────────────────────╯
```

`python -m src.main --profile intense_rock`:

```
=== Deep Intense Rock — gym and traffic ===
Profile: genre=rock, mood=intense, energy=0.92, tempo_bpm=155, likes_acoustic=False, mood_tags=['aggressive', 'driving']
Mode: balanced | diversity penalty: on

╭─────┬────────────────────┬──────────────┬───────────────┬───────────┬──────────┬─────────┬────────────────────────────────────────────────╮
│   # │ Title              │ Artist       │ Genre         │ Mood      │   Energy │   Score │ Why                                            │
├─────┼────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   1 │ Storm Runner       │ Voltline     │ rock          │ intense   │     0.91 │    6.91 │ genre match: rock (+2.00); mood match: intense │
│     │                    │              │               │           │          │         │ (+1.00); shared vibe: aggressive, driving      │
│     │                    │              │               │           │          │         │ (+0.80); energy 0.91 vs target 0.92 (+1.47);   │
│     │                    │              │               │           │          │         │ tempo 152 vs target 155 bpm (+0.93); produced  │
│     │                    │              │               │           │          │         │ texture (0.10 acousticness) (+0.72)            │
├─────┼────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   2 │ Iron Lungs         │ Blackvault   │ metal         │ intense   │     0.98 │    4.17 │ mood match: intense (+1.00); shared vibe:      │
│     │                    │              │               │           │          │         │ aggressive (+0.40); energy 0.98 vs target 0.92 │
│     │                    │              │               │           │          │         │ (+1.32); tempo 168 vs target 155 bpm (+0.68);  │
│     │                    │              │               │           │          │         │ produced texture (0.03 acousticness) (+0.78)   │
├─────┼────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   3 │ Breakline          │ Static Pilot │ drum and bass │ intense   │     0.95 │    4.09 │ mood match: intense (+1.00); shared vibe:      │
│     │                    │              │               │           │          │         │ driving (+0.40); energy 0.95 vs target 0.92    │
│     │                    │              │               │           │          │         │ (+1.41); tempo 174 vs target 155 bpm (+0.53);  │
│     │                    │              │               │           │          │         │ produced texture (0.06 acousticness) (+0.75)   │
├─────┼────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   4 │ Gym Hero           │ Max Pulse    │ pop           │ intense   │     0.93 │    4.05 │ mood match: intense (+1.00); shared vibe:      │
│     │                    │              │               │           │          │         │ aggressive (+0.40); energy 0.93 vs target 0.92 │
│     │                    │              │               │           │          │         │ (+1.47); tempo 132 vs target 155 bpm (+0.43);  │
│     │                    │              │               │           │          │         │ produced texture (0.05 acousticness) (+0.76)   │
├─────┼────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   5 │ Basement Warehouse │ Kari Vex     │ house         │ energetic │     0.88 │    2.40 │ energy 0.88 vs target 0.92 (+1.38); tempo 126  │
│     │                    │              │               │           │          │         │ vs target 155 bpm (+0.28); produced texture    │
│     │                    │              │               │           │          │         │ (0.07 acousticness) (+0.74)                    │
╰─────┴────────────────────┴──────────────┴───────────────┴───────────┴──────────┴─────────┴────────────────────────────────────────────────╯
```

The three adversarial profiles (`sad_banger`, `empty`, `unknown_genre`) are in
[`model_card.md`](model_card.md), along with the comparisons between them.

---

## Experiments You Tried

### 1. Weight shift — double energy, quarter genre (`--mode energy_focused`)

Energy went 1.5 → 3.0 with a tighter 0.35 tolerance, genre went 2.0 → 0.5, mood 1.0 → 0.5.
Same profile, same catalog:

```
=== High-Energy Pop — the starter profile ===
Profile: genre=pop, mood=happy, energy=0.8, likes_acoustic=False, mood_tags=['sunny', 'uplifting']
Mode: energy_focused | diversity penalty: on

╭─────┬────────────────┬────────────────┬───────────┬────────┬──────────┬─────────┬───────────────────────────────────────────────╮
│   # │ Title          │ Artist         │ Genre     │ Mood   │   Energy │   Score │ Why                                           │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   1 │ Sunrise City   │ Neon Echo      │ pop       │ happy  │     0.82 │    4.88 │ genre match: pop (+0.50); mood match: happy   │
│     │                │                │           │        │          │         │ (+0.50); shared vibe: sunny, uplifting        │
│     │                │                │           │        │          │         │ (+0.40); energy 0.82 vs target 0.80 (+2.83);  │
│     │                │                │           │        │          │         │ produced texture (0.18 acousticness) (+0.66)  │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   2 │ Rooftop Lights │ Indigo Parade  │ indie pop │ happy  │     0.76 │    4.33 │ related genre: indie pop ~ pop (+0.25); mood  │
│     │                │                │           │        │          │         │ match: happy (+0.50); shared vibe: sunny,     │
│     │                │                │           │        │          │         │ uplifting (+0.40); energy 0.76 vs target 0.80 │
│     │                │                │           │        │          │         │ (+2.66); produced texture (0.35 acousticness) │
│     │                │                │           │        │          │         │ (+0.52)                                       │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   3 │ Lagos Two Step │ Ayo Komolafe   │ afrobeats │ happy  │     0.78 │    4.14 │ mood match: happy (+0.50); shared vibe: sunny │
│     │                │                │           │        │          │         │ (+0.20); energy 0.78 vs target 0.80 (+2.83);  │
│     │                │                │           │        │          │         │ produced texture (0.24 acousticness) (+0.61)  │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   4 │ Verano Perdido │ Luz Caliente   │ reggaeton │ happy  │     0.85 │    3.98 │ mood match: happy (+0.50); shared vibe: sunny │
│     │                │                │           │        │          │         │ (+0.20); energy 0.85 vs target 0.80 (+2.57);  │
│     │                │                │           │        │          │         │ produced texture (0.11 acousticness) (+0.71)  │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼───────────────────────────────────────────────┤
│   5 │ Morning Praise │ The Upper Room │ gospel    │ happy  │     0.71 │    3.39 │ mood match: happy (+0.50); shared vibe:       │
│     │                │                │           │        │          │         │ uplifting (+0.20); energy 0.71 vs target 0.80 │
│     │                │                │           │        │          │         │ (+2.23); produced texture (0.42 acousticness) │
│     │                │                │           │        │          │         │ (+0.46)                                       │
╰─────┴────────────────┴────────────────┴───────────┴────────┴──────────┴─────────┴───────────────────────────────────────────────╯
```

**Result: different, not better.** `Sunrise City` still won, because it is simultaneously the
right genre, mood *and* energy — when one song is best on every axis, re-weighting cannot
dethrone it. What changed is the tail: `Gym Hero` (pop, but 0.93 energy against a 0.80 target)
fell out of the top 5 entirely, and `Morning Praise` (gospel, 0.71) climbed in. That is the
honest trade — the list got more consistent in *feel* and less loyal to the user's stated
genre. For a workout playlist that is an improvement; for someone who said "I only listen to
pop" it is a worse answer to the question they asked.

### 2. Turning the diversity penalty off (`--no-diversity`)

With penalties on, `Gym Hero` (a second pop song, after `Sunrise City`) drops from rank 3 to
rank 5 and loses 0.75 points, letting `Verano Perdido` (reggaeton) and `Lagos Two Step`
(afrobeats) up the list. Without them the top of the list is pop, pop, pop. On a 22-song
catalog the penalty is the difference between a playlist and an echo.

### 3. Discovery mode on the lofi profile (`--mode discovery`)

Adding a `+1.5 × (1 − popularity/100)` novelty bonus and dropping genre to 1.0 pushed
`Paper Boats` (folk, popularity 41) into the top 5 — a song the balanced recipe never surfaces
for this user. The scores compress, though: when every song can earn up to +1.5 for being
obscure, the gap between a great match and a mediocre one shrinks, so one more experiment would
be to make the novelty bonus a multiplier instead of an addition.

---

## Limitations and Risks

- **22 songs.** Every conclusion here is about a catalog smaller than one playlist. Most genres
  have a single representative, so "the system doesn't like jazz" and "there is one jazz song"
  are impossible to tell apart.
- **No behaviour, no learning.** VibeFinder never sees a skip, a replay or a thumbs-down. The
  profile is whatever the user typed, forever.
- **Cold start is total.** A profile with no preferences scores every song 0.00 and falls back
  to alphabetical order (see the model card). A real system would fall back to popularity.
- **It does not hear anything.** No lyrics, no language, no vocals, no production. Two songs
  with identical numbers are identical to VibeFinder even if one is in Yoruba and one is a
  death-metal cover.
- **Genre strings are compared as text.** `rock` and `metal` share no word, so they score as
  total strangers, while `pop` and `indie pop` are near-neighbours by spelling rather than sound.

Full treatment in [**model_card.md**](model_card.md).

---

## Reflection

The thing that actually changed how I think about this was writing the energy term twice. The
first version added `song["energy"]` to the score, and the whole catalog collapsed onto one
answer: the loudest song won every profile, including the ones asking for calm. It wasn't a bug
in the code — the code did exactly what I wrote — it was a bug in what I had decided "good"
meant. Swapping it for a distance term (`1 − gap/tolerance`) fixed it in one line. That gap
between "the program is correct" and "the objective is correct" is, as far as I can tell, where
most of the real damage in recommender systems lives, and you cannot find it by reading the
code. You find it by looking at the output and asking whether it is embarrassing.

The bias side turned out to be mostly arithmetic, which I did not expect. Nothing in
`recommender.py` mentions popularity, language or region, and yet the system still has a
structural preference: broad genre labels beat narrow ones, because `pop` matches `indie pop`
while `afrobeats` matches nothing; mid-range energy users match more of the catalog than
extreme ones, because that is where the songs happen to sit; and a 2.0 genre weight on a tiny
catalog is enough to guarantee that a user who says "pop" will be shown pop until they
manually say otherwise. None of that was a decision I made — each one is a side effect of a
number I picked for a different reason, interacting with the shape of the data. The diversity
penalty is the only thing in the file that pushes back, and it only works because it operates
at the ranking level, where it can see the whole list. Scaled up, with real behaviour data
feeding the profile, those same side effects are what a filter bubble is made of.

The personal reflection on the process, including where the AI was useful and where I had to
override it, is in section 9 of the model card.
