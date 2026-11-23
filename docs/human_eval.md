# Human evaluation

The automated suite in [EVALUATION.md](../EVALUATION.md) measures properties that can be
computed: mean energy, artist repetition, running time, ordering, confidence. None of those
answer the only question that finally matters about a playlist — *would a person want to listen
to it?* That judgement cannot be automated, so it is recorded here instead.

## Status and honesty note

**The `Human verdict` column is deliberately empty.** Filling it in requires a person to read
each playlist and decide, and no one has done that yet. Inventing entries would make this
document worse than useless, because it would look exactly like a completed evaluation.

The `Model review` column *is* filled in. It is a structured self-assessment written by the
assistant that built the system, judging each playlist against the principles the notes
corpus itself states (so it is at least checkable against a written standard rather than a
vibe). It is **not** a substitute for human judgement, and it has the obvious conflict of
interest: the same process that produced the playlists produced the review.

To complete this: run the commands in the first column, read each playlist, and fill in
`Human verdict` with `pass` / `weak` / `fail` plus one sentence. The rubric is below.

## Rubric

Each playlist is judged on four questions, and a verdict of `pass` requires all four.

| # | Question | Why it matters |
|---|---|---|
| 1 | **Fit** — does the list answer the request as a person meant it? | The system optimises a proxy (scores); this checks the proxy against the intent. |
| 2 | **Coherence** — does it hold together as one listening session? | Five individually-good songs can still be an incoherent set. |
| 3 | **No wrong notes** — is any single track actively jarring? | One bad track in five is what a listener actually remembers. |
| 4 | **Honest confidence** — does the published number match how good it is? | Overstated confidence is the most damaging failure mode this system has. |

## Results

Generated against commit `8a4b382` on the deterministic offline planner, so each command
reproduces the exact playlist reviewed. Energy is shown as `e0.00`.

| # | Command | Playlist produced | Conf | Model review (not human) | Human verdict |
|---|---|---|---|---|---|
| 1 | `python -m src.app "something for the gym"` | Storm Runner (rock, e0.91); Gym Hero (pop, e0.93); Breakline (dnb, e0.95); Basement Warehouse (house, e0.88); Iron Lungs (metal, e0.98) | 0.77 high | **pass** — every track is above 0.88 energy and the genres are spread exactly as the workout note prescribes (genre is irrelevant, intensity is not). The strongest result in the set. | |
| 2 | `python -m src.app "i need to focus while coding, no vocals"` | Focus Flow (lofi, e0.40); Coffee Shop Stories (jazz, e0.37); Spacewalk Thoughts (ambient, e0.28); Nocturne in Grey (classical, e0.19); Paper Boats (folk, e0.31) | 0.77 high | **weak** — four of five are instrumental and correctly low-energy, but Paper Boats has English vocals, which is the one thing the focus note says to avoid. The 60% language threshold let it through. | |
| 3 | `python -m src.app "something gentle for a rainy sunday morning"` | Library Rain (lofi, e0.35); Spacewalk Thoughts (ambient, e0.28); Midnight Coding (lofi, e0.42); Coffee Shop Stories (jazz, e0.37); Paper Boats (folk, e0.31) | 0.80 high | **pass** — high acousticness throughout, energy tightly clustered 0.28–0.42, and the two lofi tracks are separated by the diversity penalty rather than adjacent. | |
| 4 | `python -m src.app "a house party playlist that builds"` | Rooftop Lights (indie pop, e0.76); Lagos Two Step (afrobeats, e0.78); Sunrise City (pop, e0.82); Verano Perdido (reggaeton, e0.85); Basement Warehouse (house, e0.88) | 0.68 medium | **pass** — a genuine build from 0.76 to 0.88, and every track is high-danceability rather than merely high-energy, which is the distinction the party note draws. Only one actual house track, which the medium confidence arguably under-reports. | |
| 5 | `python -m src.app "music for a long night drive on the motorway"` | Night Drive Loop (synthwave, e0.75); Concrete Verses (hip hop, e0.68); Bedroom Tape (bedroom pop, e0.48); Morning Praise (gospel, e0.71); Lagos Two Step (afrobeats, e0.78) | 0.73 high | **fail** — the first two are ideal, but **Morning Praise is a communal, uplifting gospel track in a list asked to be nocturnal and cinematic**, and it is jarring. It scored on energy closeness and produced texture while matching no mood or tag. Confidence of 0.73 overstates this list. See "Findings" below. | |
| 6 | `python -m src.app "my girlfriend dumped me"` | Paper Boats (folk, e0.31); Nocturne in Grey (classical, e0.19); Library Rain (lofi, e0.35); Spacewalk Thoughts (ambient, e0.28); Velvet Hours (r&b, e0.52) | 0.77 high | **pass** — matches the feeling instead of trying to fix it, which is the heartbreak note's central claim. Velvet Hours at 0.52 is the loosest fit and sits last. No cathartic or aggressive material, correctly. | |
| 7 | `python -m src.app "i cant get to sleep"` | Midnight Coding (lofi, e0.42); Coffee Shop Stories (jazz, e0.37); Library Rain (lofi, e0.35); Spacewalk Thoughts (ambient, e0.28); Nocturne in Grey (classical, e0.19) | 0.64 medium | **pass** — descends monotonically to the quietest track in the catalog, which is exactly what the sleep note asks for. Midnight Coding at 0.42 is higher than ideal for an opener; the medium confidence is appropriate. | |
| 8 | `python -m src.app "help me wake up on a monday"` | Morning Praise (gospel, e0.71); Sunrise City (pop, e0.82); Rooftop Lights (indie pop, e0.76); Lagos Two Step (afrobeats, e0.78); Verano Perdido (reggaeton, e0.85) | 0.85 high | **pass** — high-valence throughout and a broad upward trend, matching the morning note's "lead them rather than meet them". Highest confidence in the set, and defensibly so. | |
| 9 | `python -m src.app "half an hour of lo-fi to wind down"` | Velvet Hours (r&b, e0.52); Dust Road Home (country, e0.45); Midnight Coding (lofi, e0.42); Coffee Shop Stories (jazz, e0.37); Library Rain (lofi, e0.35); Paper Boats (folk, e0.31); Spacewalk Thoughts (ambient, e0.28); Nocturne in Grey (classical, e0.19) | 0.79 high | **weak** — the arc is perfect and the 32.8 minutes is on target, but reaching eight tracks forced in Velvet Hours and Dust Road Home, which scored 1.40 and 1.28 against a profile where the best match scored 7.47. Only two of eight are actually lo-fi. The duration constraint beat the quality bar. | |
| 10 | `python -m src.app "three upbeat spanish songs"` | Morning Praise (gospel, e0.71); Lagos Two Step (afrobeats, e0.78); Verano Perdido (reggaeton, e0.85) | 0.57 medium | **pass, as a failure handled well** — only one Spanish track exists, so the literal request is impossible. Relaxing the constraint, saying so in the notes, and dropping confidence to 0.57 is the right behaviour. A listener wanting Spanish music is still not served. | |
| 11 | `python -m src.app "i want to discover something obscure"` | Nocturne in Grey (classical, pop27); Spacewalk Thoughts (ambient, pop33); Morning Praise (gospel, pop37); Paper Boats (folk, pop41); Library Rain (lofi, pop44) | 0.49 medium | **pass** — the five least-popular tracks in the catalog, correctly ordered by novelty. Coherent only in obscurity, not in sound, which is the honest consequence of a request that specified nothing but novelty. | |
| 12 | `python -m src.app "play me something good"` | Nocturne in Grey (classical, e0.19); Midnight Coding (lofi, e0.42); Morning Praise (gospel, e0.71); Basement Warehouse (house, e0.88); Iron Lungs (metal, e0.98) | 0.38 low | **pass** — deliberately incoherent, and correctly so: a cold start should offer coverage to react to, not a confident guess. The 0.38 confidence and the printed cold-start note make the uncertainty visible. | |

## Summary

| Verdict | Count | Cases |
|---|---|---|
| pass | 8 | 1, 3, 4, 6, 7, 8, 11, 12 |
| weak | 3 | 2, 9, 10 (10 is a well-handled impossibility) |
| fail | 1 | 5 |

Model-reviewed pass rate: **8/12 clean, 1 outright failure.** Note the contrast with the
automated suite's 29/29: the automated suite checks measurable properties and the properties
*are* satisfied in case 5 — the gospel track is inside the energy window, breaks no artist
rule, and the list is the right length. It takes a listener to notice it is wrong.

That gap is the single most useful thing this document shows.

## Findings worth acting on

1. **Mood and tag mismatch is not penalised, only unrewarded** (case 5). A song that matches
   no mood and no tag can still rank highly by accumulating energy, tempo and texture points.
   The scorer has no way to express "this is actively the wrong feeling". A negative term for
   a direct mood conflict (`happy` against `moody`) would fix case 5; it was not added because
   it is a change to the Module 3 scoring weights and deserves its own measurement rather than
   being slipped in to make one case pass.
2. **A hard duration target can outrank quality** (case 9). The agent will keep adding songs
   to hit a requested running time with no floor on how badly a song fits. A `min_score`
   constraint in the critic would catch it, but on a 22-song catalog it would usually be
   unsatisfiable, so the honest fix is to report the weak tail rather than hide it.
3. **The 60% language threshold is too loose for `instrumental`** (case 2). For focus
   listening specifically, the notes treat vocals as a hard problem, not a preference. A
   per-context threshold would serve this better than one global constant.

None of these three were changed in response to this review, on purpose: each one is a tuning
decision that should be measured, and the review that found them is model-authored and
unconfirmed. They are recorded in [model_card.md](../model_card.md) as known limitations.

One defect *was* found by this exercise and fixed, because it was a clear bug rather than a
tuning question: case 11 originally returned the same list as case 12, because a profile of
nothing but `mode: discovery` was misclassified as having no scorable signal, which discarded
the novelty ordering the request had asked for. Fixed, with a regression test
(`test_discovery_request_ranks_by_novelty_rather_than_going_cold_start`).
