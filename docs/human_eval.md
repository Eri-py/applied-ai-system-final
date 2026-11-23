# Human evaluation

The automated suite in [EVALUATION.md](../EVALUATION.md) measures properties that can be
computed: mean energy, artist repetition, running time, ordering, confidence. None of those
answer the question that finally matters about a playlist — *is this the right set of songs for
what was asked?* That judgement needs a reader, so it is recorded here.

## What "human evaluation" can honestly mean for this system

**The 22 songs in this catalog are fictional. There is no audio.** `Library Rain` by
`Paper Lanterns` is a row in a CSV, not a recording. So nobody — not me, not a peer, not a
grader — can evaluate these playlists by listening to them, and any document claiming they did
would be fabricated.

What a person *can* do, and what this document records, is **read each playlist's metadata
against the request and judge whether the selection is defensible**: is a communal, uplifting
gospel track the right fourth song for "a long night drive on the motorway"? That question is
answerable from the data, it is exactly the judgement the automated suite cannot make, and it
is where this system's real failures turned out to live.

That is a weaker form of evaluation than listening, and it is labelled as such throughout. It
is not weak enough to be worthless: it found two things the 285 unit tests and 29 labelled
cases all missed.

### Who wrote these verdicts

| | |
|---|---|
| **Reviewer A** | The assistant that built the system, reading playlist metadata against the principles stated in `data/notes/`. **All 12 verdicts below are Reviewer A's.** |
| **Conflict of interest** | Direct and unmitigated: the same process that produced the playlists produced the review. Treat it as a structured self-assessment, not an independent audit. |
| **Reviewer B** | Open. The protocol for a second, independent rater is at the end of this document, with a table ready to fill in and an agreement calculation. This is the single most valuable thing anyone could add to this repository. |

Judging against the notes corpus rather than against taste is deliberate: it makes each verdict
checkable against something written down. When Reviewer A calls a track "the wrong feeling",
the claim is that it conflicts with a specific sentence in a specific note, and that can be
disputed by reading the note.

## Rubric

Four criteria per playlist. A verdict of **pass** requires all four; **weak** means one
criterion is marked `~`; **fail** means any criterion is marked `✗`.

| # | Criterion | The question | Why it matters |
|---|---|---|---|
| 1 | **Fit** | Does the list answer the request as a person meant it? | The system optimises a proxy (scores). This checks the proxy against the intent. |
| 2 | **Coherence** | Does it hold together as one listening session? | Five individually-defensible songs can still be an incoherent set. |
| 3 | **No wrong notes** | Is any single track actively out of place? | One bad track in five is what a listener actually remembers. |
| 4 | **Honest confidence** | Does the published number match how good the list is? | Overstated confidence is the most damaging failure mode this system has. |

Marks: `✓` met · `~` partially met · `✗` not met.

## Scorecard

All 12 reproduce exactly from the commands shown, on the deterministic planner
(`VIBEFINDER_OFFLINE=1`).

| # | Request | Conf | 1 Fit | 2 Coh | 3 Notes | 4 Honest | Verdict (Reviewer A) |
|---|---|---|---|---|---|---|---|
| 1 | `something for the gym` | 0.77 high | ✓ | ✓ | ✓ | ✓ | **pass** |
| 2 | `i need to focus while coding, no vocals` | 0.77 high | ✓ | ~ | ~ | ~ | **weak** |
| 3 | `something gentle for a rainy sunday morning` | 0.80 high | ✓ | ✓ | ✓ | ✓ | **pass** |
| 4 | `a house party playlist that builds` | 0.68 med | ✓ | ✓ | ✓ | ✓ | **pass** |
| 5 | `music for a long night drive on the motorway` | 0.73 high | ~ | ✗ | ✗ | ✗ | **fail** |
| 6 | `my girlfriend dumped me` | 0.77 high | ✓ | ✓ | ✓ | ✓ | **pass** |
| 7 | `i cant get to sleep` | 0.64 med | ✓ | ✓ | ✓ | ✓ | **pass** |
| 8 | `help me wake up on a monday` | 0.85 high | ✓ | ✓ | ✓ | ✓ | **pass** |
| 9 | `half an hour of lo-fi to wind down` | 0.79 high | ~ | ✓ | ~ | ~ | **weak** |
| 10 | `three upbeat spanish songs` | 0.57 med | ~ | ✓ | ✓ | ✓ | **weak** |
| 11 | `i want to discover something obscure` | 0.49 med | ✓ | ~ | ✓ | ✓ | **pass** |
| 12 | `play me something good` | 0.38 low | ✓ | ✗ | ✓ | ✓ | **pass** |

Cases 11 and 12 carry a `~` and a `✗` and still pass, because in both the apparent defect is
the correct behaviour: a discovery list is coherent only in its obscurity, and a cold-start
list is *supposed* to be incoherent. Both are explained below.

**Totals: 8 pass · 3 weak · 1 fail.**

## Case notes

### 1. `something for the gym` — pass (0.77 high)

```
5.77  Storm Runner        rock           e0.91  intense
5.42  Gym Hero            pop            e0.93  intense
4.64  Breakline           drum and bass  e0.95  intense
4.56  Basement Warehouse  house          e0.88  energetic
4.43  Iron Lungs          metal          e0.98  intense
```

The strongest result in the set. Every track is above 0.88 energy, four of five are `intense`,
and the genres span rock, pop, dnb, house and metal — exactly as the workout note prescribes
("genre is close to irrelevant: metal, drum and bass, house and hard pop all serve the same
function"). Nothing acoustic. Confidence well earned.

### 2. `i need to focus while coding, no vocals` — weak (0.77 high)

```
7.52  Focus Flow           lofi       e0.40  focused     instrumental
3.00  Coffee Shop Stories  jazz       e0.37  relaxed     instrumental
2.60  Spacewalk Thoughts   ambient    e0.28  chill       instrumental
2.56  Nocturne in Grey     classical  e0.19  melancholy  instrumental
2.52  Paper Boats          folk       e0.31  melancholy  english  <-- vocals
```

**Fit ✓** — correctly low-energy, and the top pick is the catalog's purpose-built focus track,
scoring 7.52 against a next-best of 3.00.

**Coherence `~`, wrong notes `~`** — two problems. `Paper Boats` has English vocals and the
request said "no vocals" explicitly. The focus note is unusually firm here: the irrelevant
speech effect is "the single strongest rule for a focus playlist". Four of five instrumental
clears the critic's 60% language threshold, so nothing flagged it. Separately, `Nocturne in
Grey` and `Paper Boats` are both `melancholy` — defensible as background, but a sad list is not
what "focus" asked for.

**Honest confidence `~`** — 0.77 "high" for a list that breaks the one explicit instruction in
the request is overstated. *Finding 3.*

### 3. `something gentle for a rainy sunday morning` — pass (0.80 high)

```
6.14  Library Rain         lofi     e0.35  acousticness 0.86
4.75  Spacewalk Thoughts   ambient  e0.28  acousticness 0.92
4.68  Midnight Coding      lofi     e0.42  acousticness 0.71
3.47  Coffee Shop Stories  jazz     e0.37  acousticness 0.89
3.23  Paper Boats          folk     e0.31  acousticness 0.94
```

High acousticness throughout, energy tightly clustered 0.28–0.42, and the two lofi tracks are
separated rather than adjacent because of the diversity penalty. The rainy-day note asks for
warmth and containment, "nostalgic, tender and cosy rather than grieving", and that is what
this is. The best playlist in the set on coherence.

### 4. `a house party playlist that builds` — pass (0.68 medium)

```
4.16  Rooftop Lights      indie pop  e0.76  danceability 0.82
3.87  Lagos Two Step      afrobeats  e0.78  danceability 0.93
4.59  Sunrise City        pop        e0.82  danceability 0.79
4.24  Verano Perdido      reggaeton  e0.85  danceability 0.95
6.60  Basement Warehouse  house      e0.88  danceability 0.96
```

A genuine build, 0.76 → 0.88, and note the list is deliberately *not* in score order — the arc
re-ordering put the 6.60 track last. Every track has danceability above 0.79, which is the
distinction the party note draws: what people dance to is "a strong, regular, predictable
downbeat", not raw energy. Only one actual house track, but "house party" names the event
rather than the genre, which is the right reading. The medium confidence is if anything
pessimistic.

### 5. `music for a long night drive on the motorway` — **fail** (0.73 high)

```
4.71  Night Drive Loop  synthwave    e0.75  moody  nocturnal, cinematic, melancholy
4.04  Concrete Verses   hip hop      e0.68  moody  gritty, reflective, nocturnal
3.02  Bedroom Tape      bedroom pop  e0.48  moody  melancholy, nostalgic, intimate
2.82  Morning Praise    gospel       e0.71  happy  uplifting, hopeful, communal   <-- wrong
2.66  Lagos Two Step    afrobeats    e0.78  happy  sunny, romantic, danceable     <-- wrong
```

The first three are ideal — this is exactly what the commute note describes, and `Night Drive
Loop` is the best match in the catalog for the request.

Then it falls over. `Morning Praise` is a communal, uplifting gospel track and `Lagos Two Step`
is a sunny, danceable afrobeats track, in a playlist asked to be nocturnal and cinematic. Both
are `mood: happy` against a `moody` profile. Both share zero tags with the request. Neither
matches the genre. They rank anyway, because they sit close to the 0.68 energy target and score
on produced texture — **accumulating points for what they get right while being the wrong
feeling entirely.**

*(My first pass at this review named only the gospel track. Reading the full tag data for this
version showed the afrobeats track has the same defect. Two of five is the accurate figure.)*

**Honest confidence ✗** — 0.73 "high" for a list where 40% of the tracks are the wrong mood is
the most overstated number in the set, and it is overstated in the direction that matters.

This playlist passes **every** automated check: all five inside the energy window, no artist
repeats, correct length, every score positive. *Finding 1.*

### 6. `my girlfriend dumped me` — pass (0.77 high)

```
6.14  Paper Boats         folk       e0.31  melancholy  tender, rainy, reflective
6.10  Nocturne in Grey    classical  e0.19  melancholy  melancholy, tender, rainy
2.55  Library Rain        lofi       e0.35  chill
2.44  Spacewalk Thoughts  ambient    e0.28  chill
2.37  Velvet Hours        r&b        e0.52  romantic    sensual, nocturnal, tender
```

The system matches the feeling instead of trying to fix it, which is the heartbreak note's
central and most counter-intuitive claim. The top two are the catalog's two genuinely
melancholy tracks and they score far clear of the rest (6.14 and 6.10 against 2.55). No
cathartic or aggressive material, which the note specifically warns against mixing in unasked.

`Velvet Hours` is `romantic` rather than melancholy and is the loosest fit — arguably a poor
choice for a breakup. It sits last and scores 2.37. Not enough to mark down.

### 7. `i cant get to sleep` — pass (0.64 medium)

```
4.72  Midnight Coding      lofi       e0.42  78 bpm
2.31  Coffee Shop Stories  jazz       e0.37  90 bpm
5.88  Library Rain         lofi       e0.35  72 bpm
7.47  Spacewalk Thoughts   ambient    e0.28  60 bpm
3.27  Nocturne in Grey     classical  e0.19  64 bpm
```

Descends monotonically to the quietest, slowest track in the catalog, which is precisely what
the sleep note asks for: "the last track should be the quietest thing in the list". All
instrumental. Took two attempts — the arc repair fired.

The 0.42 opener is above the note's 0.22 target and `Coffee Shop Stories` at 90 bpm breaks its
80 bpm ceiling. The medium confidence correctly reflects a good-not-perfect list.

### 8. `help me wake up on a monday` — pass (0.85 high)

```
4.63  Morning Praise   gospel     e0.71  valence 0.90  uplifting, hopeful, communal
4.45  Sunrise City     pop        e0.82  valence 0.84  euphoric, sunny, uplifting
4.34  Rooftop Lights   indie pop  e0.76  valence 0.81  sunny, romantic, uplifting
4.07  Lagos Two Step   afrobeats  e0.78  valence 0.88  sunny, romantic, danceable
3.74  Verano Perdido   reggaeton  e0.85  valence 0.79  sunny, flirty, danceable
```

Every track is `happy`, every valence is above 0.79, and the tags are `sunny` / `uplifting` /
`hopeful`. The morning note's point is that valence does the work here rather than energy, and
that is what got selected. Highest confidence in the set, defensibly.

Note that `Morning Praise` is the *right* answer here and the wrong answer in case 5 — the same
track, correctly placed once and misplaced once. That is a clean illustration of what the mood
penalty in finding 1 would fix, and of why the fix has to be a conflict term rather than a
blanket demotion of that track.

### 9. `half an hour of lo-fi to wind down` — weak (0.79 high)

```
1.40  Velvet Hours         r&b        e0.52   <-- padding
1.28  Dust Road Home       country    e0.45   <-- padding
5.47  Midnight Coding      lofi       e0.42
2.31  Coffee Shop Stories  jazz       e0.37
6.63  Library Rain         lofi       e0.35
2.07  Paper Boats          folk       e0.31
7.47  Spacewalk Thoughts   ambient    e0.28
3.27  Nocturne in Grey     classical  e0.19
```

The arc is perfect (0.52 → 0.19, ending on the quietest track) and 32.8 minutes is inside the
15% tolerance on 30. Two attempts, with the arc repair visible in the output.

**Fit `~`, wrong notes `~`** — reaching eight tracks forced in `Velvet Hours` (1.40) and
`Dust Road Home` (1.28) against a best match of 7.47. Only two of eight are actually lo-fi, and
the request named lo-fi. The duration constraint beat the quality bar.

**Honest confidence `~`** — 0.79 overall is too high, *but* the per-song confidences are honest:
0.15 and 0.14 for the two weak tracks. The system is transparent about which songs it is unsure
of while being overconfident about the list as a whole. *Finding 2.*

### 10. `three upbeat spanish songs` — weak (0.57 medium), handled well

```
3.86  Morning Praise   gospel     english  <-- not spanish
3.83  Lagos Two Step   afrobeats  yoruba   <-- not spanish
3.81  Verano Perdido   reggaeton  spanish
```

**Fit `~` by necessity.** The catalog holds exactly one Spanish track, so "three upbeat Spanish
songs" is impossible. The system detects the shortfall, relaxes the language constraint, states
why in the confidence notes, and drops to 0.57. All three are genuinely upbeat (energy
0.71–0.85, all `happy`), so the surviving half of the request is served well.

This is the best *failure handling* in the set — and a listener wanting Spanish music is still
not served. Marked weak rather than pass because the output does not match the request; the
behaviour given the constraint is correct.

### 11. `i want to discover something obscure` — pass (0.49 medium)

```
1.09  Nocturne in Grey    classical  popularity 27
1.00  Spacewalk Thoughts  ambient    popularity 33
0.95  Morning Praise      gospel     popularity 37
0.89  Paper Boats         folk       popularity 41
0.84  Library Rain        lofi       popularity 44
```

The five least-popular tracks in the catalog, in ascending popularity order. Exactly right.

**Coherence `~` is the correct outcome, not a defect** — classical, ambient, gospel, folk and
lofi have nothing in common but obscurity, which is the honest consequence of a request that
specified novelty and nothing else. The medium confidence reflects having been told one thing
only.

This case previously returned the identical playlist to case 12. A profile of nothing but
`mode: discovery` was misclassified as having no scorable signal, so the cold-start path
discarded the novelty ordering the request had explicitly asked for. **Found by this review**,
fixed, regression test added
(`test_discovery_request_ranks_by_novelty_rather_than_going_cold_start`).

### 12. `play me something good` — pass (0.38 low)

```
0.00  Nocturne in Grey    classical  e0.19
0.00  Midnight Coding     lofi       e0.42
0.00  Morning Praise      gospel     e0.71
0.00  Basement Warehouse  house      e0.88
0.00  Iron Lungs          metal      e0.98
```

**Coherence `✗` is the design, not a failure.** Five genres, energy spanning 0.19 to 0.98, every
score 0.00. Against an empty profile every song scores identically, so ranking them would be an
alphabetical tie-break wearing a ranking's clothes. The system returns coverage instead,
publishes 0.38 LOW, and prints a note saying the songs were chosen to span the catalog rather
than to match a profile.

The most important row in this table. An earlier version answered this request with a
confident-looking five-song focus playlist, because a note matched on the single word "good".

## Findings

Ranked by how much they matter.

### 1. Mood conflict is unrewarded but never penalised — **not fixed**

The cause of the only outright failure (case 5) and of the weaker halves of cases 2 and 6. A
song that matches no mood and shares no tags can still rank by accumulating energy, tempo and
texture points. The scorer can express "this is not the right feeling" only as an absence of
points, never as a cost.

A conflict table (`happy` ↔ `moody`, `aggressive` ↔ `sleepy`) subtracting on a direct clash
would fix case 5, and it is the first item in this project's future work.

**Not fixed here deliberately.** It changes the Module 3 scoring weights that every other result
in this project depends on, and it deserves its own before-and-after measurement rather than
being slipped in to make one case pass. Logged as limitation 4 in
[`../model_card.md`](../model_card.md).

Worth noting: **Module 3's own model card predicted this exact failure** in its Future Work
section, before any of these playlists existed — see [`model_card_v1.md`](model_card_v1.md) §8,
item 1.

### 2. A hard duration target can outrank song quality — not fixed

Case 9. The agent will keep adding tracks to hit a requested running time with no floor on how
badly a track fits. A `min_score` constraint in the critic would catch it, but on a 22-song
catalog it would frequently be unsatisfiable, so the honest fix is to report the weak tail
rather than suppress it — which the per-song confidence already does. Promoting that into a
printed warning would be a small, safe improvement.

### 3. The language threshold is too loose where the request is explicit — not fixed

Case 2. A global 60% share lets one English track into a list that said "no vocals". For focus
listening the notes treat vocals as a hard constraint rather than a preference, so a
per-context threshold would serve better than one global constant.

### What was fixed as a result of this review

One item, because it was an unambiguous bug rather than a tuning decision: the case 11
discovery-mode misclassification described above. The other three findings are judgement calls
that should be measured, ideally by a reviewer who is not me.

---

## Protocol for an independent second rater

Reviewer A's verdicts have a direct conflict of interest. A second rater is the
highest-value addition this document could receive, and it takes about twenty minutes.

1. Install, and pin the deterministic planner so you see the same playlists:
   ```bash
   pip install -r requirements.txt
   export VIBEFINDER_OFFLINE=1      # Windows: $env:VIBEFINDER_OFFLINE="1"
   ```
2. For each of the 12 requests in the scorecard, run `python -m src.app "<request>"`.
3. **Read the request, then the playlist, then the four rubric criteria — in that order.** Do
   not read Reviewer A's case note until you have marked your own four criteria, or you will be
   grading their reasoning rather than the playlist.
4. Fill in the table below. One sentence per case is enough.
5. Compute agreement: count the cases where your verdict matches Reviewer A's, divide by 12.
   Any case where the verdicts differ is more informative than any case where they agree — write
   down *why*.

| # | Request | Your verdict (pass/weak/fail) | One sentence | Agrees with A? |
|---|---|---|---|---|
| 1 | `something for the gym` | | | |
| 2 | `i need to focus while coding, no vocals` | | | |
| 3 | `something gentle for a rainy sunday morning` | | | |
| 4 | `a house party playlist that builds` | | | |
| 5 | `music for a long night drive on the motorway` | | | |
| 6 | `my girlfriend dumped me` | | | |
| 7 | `i cant get to sleep` | | | |
| 8 | `help me wake up on a monday` | | | |
| 9 | `half an hour of lo-fi to wind down` | | | |
| 10 | `three upbeat spanish songs` | | | |
| 11 | `i want to discover something obscure` | | | |
| 12 | `play me something good` | | | |

**Agreement with Reviewer A: ___ / 12.** Disagreements, and why:

### What a second rating would unlock

The confidence score currently separates under-specified requests from well-specified ones by
0.34, and separates runs that *passed* from runs that *failed* by only 0.05
([EVALUATION.md](../EVALUATION.md), experiment 3). It predicts under-specification, not
incorrectness.

Twelve independent verdicts are twelve labels. Correlating published confidence against them is
the only honest route to fixing that weakness, because they would be the only data in this
project not produced by the system being measured.

---

## The headline

The automated suite scores **29/29**. Reviewer A scores these twelve playlists **8 pass, 3 weak,
1 fail**.

Both numbers are correct. In case 5 — the outright failure — every automated check passes: the
gospel and afrobeats tracks are inside the energy window, no artist repeats, the list is the
right length, every score is positive. The properties the suite measures are genuinely
satisfied. It takes a reader to notice that two of the five songs are the wrong feeling.

That gap between 29/29 and 8/12 is the most useful thing in this document.
