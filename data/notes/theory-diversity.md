---
id: theory-diversity
title: Diversity, filter bubbles and repetition
kind: theory
keywords: diversity, diverse, variety, varied, repetition, repetitive, same artist, filter bubble, bubble, discovery, discover, new, fresh, different, range, obscure, underground
hints:
  mode: discovery
---
Two distinct failures get called repetitive. The first is within-list repetition: the
same artist or the same genre filling a short playlist. This is a ranking failure, not a
scoring failure - no single song is wrong, the combination is - and it is fixed with a
greedy diversity penalty applied while the list is assembled, discounting each additional
song from an artist or genre already chosen.

The second is across-session narrowing, the filter bubble. A purely content-based system
converges: it recommends what resembles what you liked, so the profile tightens, so the
recommendations narrow further. Content-based systems cannot escape this on their own because
they have no outside signal pulling them sideways. Collaborative signal is what usually
breaks it, and a system without users cannot collaborate.

The partial defence available to a content-based system is a novelty term: a bonus inversely
proportional to popularity, which pushes obscure material up without throwing out relevance.
This trades measurable accuracy for exposure, and that trade should be stated rather than
hidden - it is a product decision, not a technical one. A listener asking to discover
something new is explicitly consenting to it; a listener asking for a workout playlist is not.
