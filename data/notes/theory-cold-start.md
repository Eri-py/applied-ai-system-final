---
id: theory-cold-start
title: Vague requests, cold starts and asking for less
kind: theory
keywords: vague, unclear, anything, something, whatever, surprise me, dont know, do not know, not sure, random, cold start, no preference, just music, good music
hints:
  mode: balanced
---
A request like "play me something good" carries almost no information, and the failure mode
is to pretend otherwise. A content-based system with no user history has nothing to fall back
on: there is no behaviour to collaborate with and no stated preference to match, so every
song is equally defensible, which means the ranking is being decided by whatever default
sits in the weights.

The honest response is to make the defaults visible and the confidence low. A system that
returns five songs with a confident explanation for a request that specified nothing is
reporting precision it does not have, and that is the most damaging kind of error because it
is invisible to the user - the list looks exactly like a good list.

Two practical rules follow. First, let the confidence score fall when the request is thin,
and say so in the output rather than only logging it. Second, prefer coverage over
commitment: when nothing is specified, a list that spans several genres and energy levels
is more useful than five songs from one corner, because it gives the listener something to
react to. The next request is then informative, and the cold start is over.
