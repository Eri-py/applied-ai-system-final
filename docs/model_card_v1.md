# 🎧 Model Card: VibeFinder 1.0 (Module 3) — superseded

> This is the model card for the **original Module 3 project**, kept unchanged for reference.
> The card for the system in this repository is [`model_card.md`](../model_card.md) at the
> repository root. Section 8 ("Future Work") of this document predicted the mood-conflict
> failure that human review of VibeFinder 2.0 went on to find — see
> [`docs/human_eval.md`](human_eval.md), case 5.

## 1. Model Name

**VibeFinder 1.0** — a content-based music recommender simulation.

---

## 2. Intended Use

VibeFinder takes a written-down taste profile and returns the 5 songs from a 22-song catalog
that best fit it, with a reason attached to every point it awarded.

- **What it generates:** a ranked shortlist, plus an explanation per song ("genre match: pop
  (+2.00); energy 0.82 vs target 0.80 (+1.44)").
- **What it assumes about the user:** that they can name a genre, a mood, a rough energy level
  (0.0–1.0) and whether they like acoustic music — and that this is stable. It assumes the
  profile is *honest and complete*, which real users are not.
- **Who it is for:** classroom exploration. It is a teaching instrument for seeing how data
  becomes a ranking, not a product. There are no real users, no accounts and no feedback loop.

---

## 3. How the Model Works

Imagine a judge with a scorecard, sitting with a stack of 22 song cards and one card
describing the listener.

The judge picks up a song and goes down the scorecard. Same genre as the listener asked for?
Two points. Not the same, but a close relative — "indie pop" when they asked for "pop"? One
point. Same mood? One more point. Any of the little vibe words matching ("sleepy",
"aggressive", "nostalgic")? Four tenths of a point each, up to about one point in total.

Then the two sliding scales. For energy, the judge does **not** reward loud songs — it rewards
*close* songs. The listener who asked for calm (0.40) gets full marks for a 0.42 song and
nothing at all for a 0.95 one. Tempo works the same way in beats per minute, but only if the
listener bothered to name one. Finally, if the listener said they like acoustic music, the
judge pays them a fraction of a point proportional to how acoustic the song is — and if they
said they don't, it pays the mirror image.

Every song gets a total and a list of reasons. Then a second person — the referee — lines all
22 up from highest to lowest and takes the top five. The referee does one extra thing the judge
cannot: if an artist or a genre has already been picked, the next song from that artist loses
1.5 points and the next song from that genre loses 0.75, just for the purposes of making the
list. That is what stops a top-5 from being the same artist five times.

**Changes from the starter logic:** the starter had empty function bodies. On top of the
suggested recipe (genre +2 / mood +1 / energy similarity) I added partial genre credit, vibe
tags, tempo and acousticness terms, a popularity-based novelty bonus, five named scoring modes
the CLI can switch between, and the artist/genre diversity penalty.

---

## 4. Data

`data/songs.csv` — 22 fictional songs, 15 columns.

- **Original columns:** `id`, `title`, `artist`, `genre`, `mood`, `energy`, `tempo_bpm`,
  `valence`, `danceability`, `acousticness`.
- **Columns I added (5):** `popularity` (0–100), `release_decade`, `mood_tags`
  (semicolon-separated descriptive tags such as `nostalgic;sleepy;focused`), `language`
  (`english` / `instrumental` / `spanish` / `yoruba`) and `duration_sec`. All five are scored,
  not just stored.
- **Rows I added:** 12, taking the catalog from 10 to 22, specifically to add genres and moods
  the starter had none of — afrobeats, hip hop, classical, metal, country, reggaeton, r&b,
  folk, drum and bass, gospel, bedroom pop, house, and the moods `melancholy`, `romantic` and
  `energetic`.
- **Genres:** 19 distinct labels across 22 songs. **Moods:** 9. **Decades:** 1990s–2020s,
  heavily skewed to 2020 (10 of 22). **Languages:** 12 English, 8 instrumental, 1 Spanish,
  1 Yoruba. **Lengths:** 142–402 seconds.

**What is missing from this dataset as a picture of musical taste:** almost everything. One
song per genre for most genres, so genre-level conclusions are really song-level conclusions.
No non-English-language metadata beyond a couple of titles. No live vs studio, no album
context, no song length, no release year (only a decade bucket). `energy` spans 0.19
to 0.98 but bunches in the middle, so the extremes of the scale are thin.
And the whole catalog was invented by me and an AI assistant, which means its "genres" are
tidier and more separable than real metadata ever is.

---

## 5. Strengths

- **Coherent, well-specified profiles get genuinely sensible answers.** The lofi profile
  returns `Library Rain`, `Midnight Coding`, `Spacewalk Thoughts`, `Coffee Shop Stories`,
  `Dust Road Home` — not one of those would be out of place on a 1am study playlist, and the
  last two aren't even lofi. That is content-based filtering working as intended: it found the
  *vibe* past the label.
- **The energy term behaves.** In every profile that named a genre the catalog actually
  has, the rank-1 song was within **0.03** of the target energy. The distance scoring does the job it was written for.
- **Every result is auditable.** Nothing in the output is unexplained, which is how I found all
  the problems in section 6.
- **Graceful degradation.** Missing preferences, unknown genres and unknown tags are skipped
  rather than crashing; the system scores what it has.
- **The diversity penalty earns its keep.** Comparing `--no-diversity` to the default on the
  pop profile, it is the only reason the top 5 is not pop, pop, pop.

---

## 6. Limitations and Bias

**The weakness I would fix first: VibeFinder cannot handle a conflicted user, and it does not
admit it.** The `sad_banger` profile asks for something coherent to a human and impossible to
my scoring rule — melancholy, acoustic, and 0.90 energy at 170 bpm, i.e. "a sad song I can
cry to at the gym". No song in the catalog is all of those, so the score degenerates into
"whatever wins the most *separate* terms", and the answer comes back **`Gym Hero`** — an
0.93-energy pop workout track whose mood is `intense` and whose acousticness is 0.05, the
precise opposite of two of the three things the user asked for. It got there on +2.00 for
genre and +1.41 for energy alone, which was enough to beat songs that actually matched the
melancholy. A weighted sum has no idea that "melancholy" and "hype" are in tension; it just
adds up whatever it can find. Worse, the explanation it prints is *technically true for every
line* while being a bad recommendation overall, which is exactly the failure mode that is hard
to catch in a big system. (Running the same profile under `--mode mood_first` returns
`Nocturne in Grey` — classical, melancholy, 0.97 acousticness — so the catalog *does* hold a
better answer; the default weights simply cannot reach it.)

Other limitations, in rough order of how much they distort the output:

- **Genre monopoly on a tiny catalog.** +2.00 for genre against a best observed total of
  6.91 means roughly 30% of a winning score comes from one string comparison. For the
  pop user, the only reason non-pop songs appear at all is the diversity penalty.
- **Broad labels beat narrow ones, for spelling reasons.** The partial-match rule rewards
  shared *words*: `pop` earns half credit from `indie pop` and `bedroom pop`, so a user who
  says "pop" effectively has three genres while a user who says "afrobeats" has exactly one
  and can never score a genre point from anything else. Users of genres with compound English
  names are structurally advantaged over users of genres without them.
- **The energy-gap cliff punishes people with extreme taste.** The term dies at a gap of 0.5,
  so a user targeting 0.5 energy earns energy points from all 22 songs, while a user targeting
  0.95 earns them from 15 and a user targeting 0.1 from 10. "I want the gentlest possible
  music" and "I want the most
  intense possible music" are both served worse than "I want something middling", purely
  because of where the catalog's numbers happen to sit.
- **Total cold start.** The `empty` profile scores every song **0.00** and the tie-break falls
  through to alphabetical title order, so a brand new user is shown `Basement Warehouse`,
  `Bedroom Tape`, `Breakline`… This is a real failure dressed up as a result: the list looks
  like a recommendation and is actually the alphabet. A real system would fall back to
  popularity or to editorial playlists.
- **Popularity bias is available on request.** `discovery` mode deliberately inverts it, but
  the `popularity` weight exists and in `balanced` mode is set to 0 — so the default is
  popularity-blind, which is itself a choice: the obscure classical piece and the hit are
  treated as equals, which no real platform would do.
- **The language term serves English speakers and nobody else.** 20 of the 22 songs are either
  English or instrumental, so those two preferences find plenty; a user who sets
  `language="spanish"` can earn that +0.60 from exactly one song in the catalog and
  `language="yoruba"` likewise. The scoring code treats all languages identically — the
  unfairness is entirely in the data, which is precisely how it happens in real catalogs, and
  it is invisible unless you count the rows.
- **Filter bubble by construction.** The profile never updates. Whatever genre the user typed
  on day one is the genre that wins +2.00 forever. There is no exploration term, no decay, no
  randomness — if this ran in production, the only songs a user would ever see outside their
  genre are the ones the diversity penalty lets through.
- **Features it ignores entirely:** lyrics, vocals, `valence` and `danceability` (in the data
  but unscored), release year, artist similarity, and anything the user has actually listened
  to. Language and length are scored, but only as an exact string match and a distance — the
  system has no idea that Spanish and Portuguese are closer to each other than to Yoruba.

---

## 7. Evaluation

### Profiles tested

| Profile | What it tests |
|---------|---------------|
| `happy_pop` | The baseline: a coherent, fully-specified profile. |
| `chill_lofi` | Low energy and acoustic preference — the opposite corner of the space. |
| `intense_rock` | High energy plus a tempo target, to see tempo do any work at all. |
| `sad_banger` | **Adversarial:** internally contradictory (melancholy + acoustic + 0.9 energy @ 170bpm). |
| `empty` | **Adversarial:** cold start, no preferences whatsoever. |
| `instrumental_study` | The two newest features: `language` and `duration_sec`. |
| `unknown_genre` | **Adversarial:** a genre (`polka`) that does not exist in the catalog. |

### What I looked for

Whether rank 1 was defensible to a human; whether the explanation matched the song; whether any
single song dominated across unrelated profiles; and whether the adversarial profiles produced
*something* rather than crashing or returning nonsense.

### The adversarial runs

```
=== Adversarial — wants to cry at 180 bpm (sad mood, 0.9 energy) ===
Profile: genre=pop, mood=melancholy, energy=0.9, tempo_bpm=170, likes_acoustic=True, mood_tags=['melancholy', 'hype']
Mode: balanced | diversity penalty: on

╭─────┬────────────────┬───────────────┬───────────────┬─────────┬──────────┬─────────┬────────────────────────────────────────────────╮
│   # │ Title          │ Artist        │ Genre         │ Mood    │   Energy │   Score │ Why                                            │
├─────┼────────────────┼───────────────┼───────────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   1 │ Gym Hero       │ Max Pulse     │ pop           │ intense │     0.93 │    3.90 │ genre match: pop (+2.00); shared vibe: hype    │
│     │                │               │               │         │          │         │ (+0.40); energy 0.93 vs target 0.90 (+1.41);   │
│     │                │               │               │         │          │         │ tempo 132 vs target 170 bpm (+0.05); acoustic  │
│     │                │               │               │         │          │         │ texture (0.05 acousticness) (+0.04)            │
├─────┼────────────────┼───────────────┼───────────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   2 │ Breakline      │ Static Pilot  │ drum and bass │ intense │     0.95 │    2.70 │ shared vibe: hype (+0.40); energy 0.95 vs      │
│     │                │               │               │         │          │         │ target 0.90 (+1.35); tempo 174 vs target 170   │
│     │                │               │               │         │          │         │ bpm (+0.90); acoustic texture (0.06            │
│     │                │               │               │         │          │         │ acousticness) (+0.05)                          │
├─────┼────────────────┼───────────────┼───────────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   3 │ Sunrise City   │ Neon Echo     │ pop           │ happy   │     0.82 │    2.65 │ genre match: pop (+2.00); energy 0.82 vs       │
│     │                │               │               │         │          │         │ target 0.90 (+1.26); acoustic texture (0.18    │
│     │                │               │               │         │          │         │ acousticness) (+0.14); diversity penalty       │
│     │                │               │               │         │          │         │ (-0.75)                                        │
├─────┼────────────────┼───────────────┼───────────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   4 │ Rooftop Lights │ Indigo Parade │ indie pop     │ happy   │     0.76 │    2.36 │ related genre: indie pop ~ pop (+1.00); energy │
│     │                │               │               │         │          │         │ 0.76 vs target 0.90 (+1.08); acoustic texture  │
│     │                │               │               │         │          │         │ (0.35 acousticness) (+0.28)                    │
├─────┼────────────────┼───────────────┼───────────────┼─────────┼──────────┼─────────┼────────────────────────────────────────────────┤
│   5 │ Iron Lungs     │ Blackvault    │ metal         │ intense │     0.98 │    2.23 │ energy 0.98 vs target 0.90 (+1.26); tempo 168  │
│     │                │               │               │         │          │         │ vs target 170 bpm (+0.95); acoustic texture    │
│     │                │               │               │         │          │         │ (0.03 acousticness) (+0.02)                    │
╰─────┴────────────────┴───────────────┴───────────────┴─────────┴──────────┴─────────┴────────────────────────────────────────────────╯
```

```
=== Adversarial — a brand new user who has told us nothing ===
Profile: no preferences given
Mode: balanced | diversity penalty: on

╭─────┬─────────────────────┬──────────────┬───────────────┬───────────┬──────────┬─────────┬──────────────────────────────────────────╮
│   # │ Title               │ Artist       │ Genre         │ Mood      │   Energy │   Score │ Why                                      │
├─────┼─────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼──────────────────────────────────────────┤
│   1 │ Basement Warehouse  │ Kari Vex     │ house         │ energetic │     0.88 │    0.00 │ nothing in this song matches the profile │
├─────┼─────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼──────────────────────────────────────────┤
│   2 │ Bedroom Tape        │ june//static │ bedroom pop   │ moody     │     0.48 │    0.00 │ nothing in this song matches the profile │
├─────┼─────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼──────────────────────────────────────────┤
│   3 │ Breakline           │ Static Pilot │ drum and bass │ intense   │     0.95 │    0.00 │ nothing in this song matches the profile │
├─────┼─────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼──────────────────────────────────────────┤
│   4 │ Coffee Shop Stories │ Slow Stereo  │ jazz          │ relaxed   │     0.37 │    0.00 │ nothing in this song matches the profile │
├─────┼─────────────────────┼──────────────┼───────────────┼───────────┼──────────┼─────────┼──────────────────────────────────────────┤
│   5 │ Concrete Verses     │ Dex Marrow   │ hip hop       │ moody     │     0.68 │    0.00 │ nothing in this song matches the profile │
╰─────┴─────────────────────┴──────────────┴───────────────┴───────────┴──────────┴─────────┴──────────────────────────────────────────╯
```

```
=== Adversarial — loves a genre the catalog does not have (polka) ===
Profile: genre=polka, mood=happy, energy=0.5, likes_acoustic=False
Mode: balanced | diversity penalty: on

╭─────┬────────────────┬────────────────┬───────────┬────────┬──────────┬─────────┬─────────────────────────────────────────────╮
│   # │ Title          │ Artist         │ Genre     │ Mood   │   Energy │   Score │ Why                                         │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼─────────────────────────────────────────────┤
│   1 │ Morning Praise │ The Upper Room │ gospel    │ happy  │     0.71 │    2.33 │ mood match: happy (+1.00); energy 0.71 vs   │
│     │                │                │           │        │          │         │ target 0.50 (+0.87); produced texture (0.42 │
│     │                │                │           │        │          │         │ acousticness) (+0.46)                       │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼─────────────────────────────────────────────┤
│   2 │ Lagos Two Step │ Ayo Komolafe   │ afrobeats │ happy  │     0.78 │    2.27 │ mood match: happy (+1.00); energy 0.78 vs   │
│     │                │                │           │        │          │         │ target 0.50 (+0.66); produced texture (0.24 │
│     │                │                │           │        │          │         │ acousticness) (+0.61)                       │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼─────────────────────────────────────────────┤
│   3 │ Rooftop Lights │ Indigo Parade  │ indie pop │ happy  │     0.76 │    2.24 │ mood match: happy (+1.00); energy 0.76 vs   │
│     │                │                │           │        │          │         │ target 0.50 (+0.72); produced texture (0.35 │
│     │                │                │           │        │          │         │ acousticness) (+0.52)                       │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼─────────────────────────────────────────────┤
│   4 │ Sunrise City   │ Neon Echo      │ pop       │ happy  │     0.82 │    2.20 │ mood match: happy (+1.00); energy 0.82 vs   │
│     │                │                │           │        │          │         │ target 0.50 (+0.54); produced texture (0.18 │
│     │                │                │           │        │          │         │ acousticness) (+0.66)                       │
├─────┼────────────────┼────────────────┼───────────┼────────┼──────────┼─────────┼─────────────────────────────────────────────┤
│   5 │ Verano Perdido │ Luz Caliente   │ reggaeton │ happy  │     0.85 │    2.16 │ mood match: happy (+1.00); energy 0.85 vs   │
│     │                │                │           │        │          │         │ target 0.50 (+0.45); produced texture (0.11 │
│     │                │                │           │        │          │         │ acousticness) (+0.71)                       │
╰─────┴────────────────┴────────────────┴───────────┴────────┴──────────┴─────────┴─────────────────────────────────────────────╯
```

### Comparing the profiles, pair by pair

- **`happy_pop` vs `chill_lofi`** — barely a song in common, which is the headline result: the
  two profiles sit at opposite ends of the energy scale (0.80 vs 0.38) and the catalog sorts
  itself accordingly. Pop gets `Sunrise City` (0.82 energy, produced, sunny); lofi gets
  `Library Rain` (0.35, acoustic, rainy). The `likes_acoustic` flip is doing visible work too:
  the same acousticness column that earns `Gym Hero` +0.76 for the pop user is worth almost
  nothing to them if they'd said they liked acoustic. In plain terms: these two users are
  asking for different *rooms*, and the system puts them in different rooms.
- **`happy_pop` vs `intense_rock`** — both want high energy (0.80 vs 0.92), and this is where
  the overlap shows: **`Gym Hero` appears in both top 5s.** It is pop (so the pop user's +2.00
  genre match applies), its mood is `intense` (so the rock user's +1.00 mood match applies),
  and at 0.93 energy it is near both targets. This is the "why does Gym Hero follow me
  everywhere" effect, and the answer is unglamorous: a song that scores *somewhat* on many
  terms beats a song that scores *perfectly* on one, because the rule is addition. For a
  non-programmer: the scorecard gives out points for being roughly right about lots of things,
  and `Gym Hero` is roughly right about almost everything — loud, upbeat, polished, popular —
  so it keeps collecting consolation points no matter who is asking.
- **`intense_rock` vs `sad_banger`** — both high energy, and both end up in the same loud
  corner of the catalog (`Gym Hero`, `Breakline`, `Iron Lungs`), even though one asked for
  aggression and the other for melancholy. The mood term (1.00) simply is not strong enough to
  overcome energy (1.47) plus genre (2.00). This is the clearest evidence that my weights make
  *intensity* the real organising axis of the system, whatever the mood column says.
- **`unknown_genre` vs `happy_pop`** — the polka user gets a top 5 made entirely of `happy`
  songs with mid-range energy, scoring 2.16–2.33 instead of 3.12–5.90. The system behaves
  correctly (it quietly drops a term it cannot score) but the *scores are not comparable
  across profiles* — a 2.33 here means "the best of a bad situation", and nothing in the output
  says so. A production system would need a confidence floor below which it says "we don't
  know you well enough yet" instead of ranking anyway.
- **`chill_lofi` vs `instrumental_study`** — nearly the same request (lofi, low energy,
  acoustic) with two extra constraints: no vocals, and keep it under about three minutes. The
  lists overlap but reorder: `Library Rain` drops from 1st to 2nd and `Focus Flow` takes the
  top spot, because it is the only song that is lofi *and* `focused` *and* instrumental *and*
  142 seconds long. `Dust Road Home` — English, and the only song in the lofi profile's top 5
  with vocals — is the one result that falls out entirely. The honest
  caveat is visible in the explanations: the length term contributes +0.47 to the winner but
  only +0.01 to `Coffee Shop Stories` at 268 seconds, so beyond two minutes off-target it is
  effectively off, and the two new terms are worth at most 1.10 of a ~7.00 total. They refine;
  they never overrule genre.
- **`empty` vs everything else** — all zeros, alphabetical order. The only profile whose output
  is meaningless, and the only one whose output *looks* exactly as authoritative as the others.

### What surprised me

1. **Re-weighting barely moved rank 1.** Doubling energy and quartering genre
   (`--mode energy_focused`) left `Sunrise City` on top. A song that is best on every axis is
   immune to re-weighting; the experiment only reshuffled ranks 3–5. I had assumed weights were
   the main lever, and for the top of the list they mostly aren't — the data's shape is.
2. **The cold-start output is dishonest rather than empty.** I expected a blank list or an
   error. Getting a confident-looking alphabetical top 5 with score `0.00` printed next to it
   was a much better lesson than a crash would have been.
3. **Most of the bias came from arithmetic, not from any field I chose.** Nothing scores
   language or region, yet broad-English-compound genres get an advantage and mid-range energy
   users get better coverage, both purely as side effects of numbers picked for other reasons.

---

## 8. Future Work

1. **Penalise conflicts instead of only rewarding matches.** Build a small table of opposing
   tags (`melancholy` ↔ `hype`, `sleepy` ↔ `aggressive`) and subtract when a song hits one side
   while the user asked for the other. That alone would have kept `Gym Hero` away from the
   `sad_banger` profile.
2. **Normalise and report confidence.** Divide by the maximum score the profile could possibly
   have earned, so scores are comparable between users, and refuse to rank below a floor —
   showing "we need more from you" instead of alphabetical noise for the cold-start user.
3. **Learn from behaviour.** Take likes and skips, nudge `target_energy` and the tag weights
   toward what the user actually plays, and add an explicit exploration slot (one of the five
   results chosen for distance from the profile rather than closeness) so the bubble has a leak
   in it by design.
4. **Use the unused columns.** `valence` and `danceability` are sitting in the CSV; treating
   mood as a point in (valence, energy, danceability) space instead of a string would make
   genre labels much less load-bearing.

---

## 9. Personal Reflection

**Biggest learning moment.** Writing the energy term the obvious way first — adding
`song["energy"]` to the score — and watching the loudest song in the catalog win every profile,
including the ones asking for calm. The code was correct; my definition of "good" was wrong.
Rewriting it as a distance (`1 − gap/tolerance`) fixed it in a line. I now believe the hard
part of a recommender is not the ranking machinery but deciding, precisely, what counts as a
good answer — and that you cannot see your own mistake there by re-reading the code, only by
looking at the output and asking whether it is embarrassing.

**Where AI helped, and where I had to check it.** It was genuinely useful for breadth: naming
the collaborative-vs-content distinction properly, generating 12 plausible catalog rows across
genres I don't listen to, and suggesting the Strategy-pattern idea that became the
`ScoringMode` registry. It was also confidently wrong in ways I had to catch. It proposed
scoring energy as a plain sum (the bug above) and, separately, as `1 - abs(gap)` with no
tolerance, which makes the term so flat it never changes a ranking. The clearest catch was in
the length term: the generated code computed the closeness `fit` correctly and then awarded
`weights.duration` instead of `weights.duration * fit`, so **every** song got the full +0.50
no matter how long it was. The code ran, the tests I had at the time passed, and the printed
explanation read `length 352s vs target 150s (+0.50)` — a line that is self-evidently wrong
only if you actually read the output. I found it by reading the output. There is now a test
(`test_duration_term_dies_off_outside_the_tolerance`) that pins all three cases. It wanted to drop the
diversity penalty into `score_song`, where it cannot work — a single song has no idea what else
is in the list, so that logic has to live in the ranking step. And its first pass at the "bias"
section listed generic textbook harms rather than the two biases actually present in my file
(the genre-spelling advantage and the energy cliff), which I only found by reading my own
output table. The pattern: good at inventory and vocabulary, unreliable about whether a
specific number does what I want in *this* system.

**What surprised me about simple algorithms.** They don't feel simple from the outside.
Twenty-two rows, nine addition rules and a sort produce output that reads like taste — the lofi
list in particular is a playlist I would actually use, including the three songs on it that
aren't lofi. That is the uncomfortable part. If nine lines of arithmetic can pass for
understanding my taste, then the confidence I feel about a real recommender "getting me" is not
evidence of much, and neither is the explanation printed next to it: every reason `Gym Hero`
gave the melancholy user was true, and the recommendation was still bad.

**What I would try next.** The conflict-penalty table from section 8, first, because it fixes
the one result I am least willing to defend. Then the explicit exploration slot — deliberately
reserving one of the five results for a song *far* from the profile, to see whether a filter
bubble you build a hole into on purpose still closes itself.
