"""Retrieval layer: a BM25 index over the written music-knowledge notes in `data/notes/`.

This is the "R" in the system's RAG. It exists because the natural-language half of the
problem ("something for a rainy sunday morning") cannot be answered from the song catalog
alone -- the catalog knows a song's tempo, but nothing in it says which tempo a rainy Sunday
wants. The notes carry that knowledge in two forms at once:

- prose, which is handed to the language model as grounding context, and
- a `hints:` block of structured defaults, which seeds the taste profile directly.

The second form is what makes retrieval load-bearing rather than decorative: with the notes
switched off (`--no-retrieval`), the planner has no numeric targets to start from and the
measured quality of the playlists drops. See `evaluation/run_eval.py` for that ablation.

No third-party dependency: BM25 is about thirty lines, and dependency-free beats clever here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_NOTES_DIR = Path(__file__).resolve().parent.parent / "data" / "notes"

# BM25 constants. k1 controls how fast term-frequency saturates (a 10th mention of a word
# adds far less than the 2nd); b controls how hard long documents are penalised.
BM25_K1 = 1.5
BM25_B = 0.75

# The `keywords:` line is the hand-written "this note is about these words" field, so a hit
# there is worth more than a hit in the body prose.
KEYWORD_FIELD_BOOST = 3.0
TITLE_FIELD_BOOST = 2.0

# Words too common in this corpus to carry signal. Deliberately short -- BM25's IDF term
# already discounts common words; this only removes the ones that would otherwise match
# every note and flatten the ranking.
STOPWORDS = frozenset(
    """
    a an and are as at be been but by can do does for from has have how i in is it its
    me my of on or so that the their them then there they this to was what when which
    who will with you your want wants need needs give some something please while just
    """.split()
)

# A retrieved note only contributes structured hints if it scored at least this fraction of
# the top hit's score. Without the floor, a request that matches one note strongly and
# another faintly inherits the faint note's specific numbers -- "play me something good"
# picked up the focus note's 0.40 energy and instrumental-only filter purely because the
# word "good" appears in it once. That is the false-precision failure `theory-cold-start`
# warns about, produced by the retriever itself.
HINT_FLOOR_RATIO = 0.35

# Which hint keys are numeric, so "0.9" becomes a float rather than the string "0.9".
_FLOAT_HINTS = ("energy",)
_INT_HINTS = ("tempo_bpm", "decade", "duration_sec", "k")
_BOOL_HINTS = ("likes_acoustic",)
_LIST_HINTS = ("mood_tags",)


@dataclass
class Note:
    """One retrievable passage: the prose plus the structured hints in its frontmatter."""

    id: str
    title: str
    kind: str
    keywords: List[str]
    hints: Dict[str, object]
    body: str
    path: Optional[Path] = None

    @property
    def text(self) -> str:
        """The prose, used as grounding context in a prompt."""
        return self.body.strip()


@dataclass
class Hit:
    """A retrieved note plus the score that retrieved it."""

    note: Note
    score: float
    matched_terms: List[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.note.id

    @property
    def title(self) -> str:
        return self.note.title

    @property
    def hints(self) -> Dict[str, object]:
        return self.note.hints

    @property
    def keyword_hit(self) -> bool:
        """True if the query matched a word the note's author listed in `keywords:`.

        A much stronger signal than the score alone that this note is genuinely about the
        query, rather than sharing an incidental word with its prose. "crying" is a keyword of
        the heartbreak note; "list" merely appears in the body of the energy-arc note.
        """
        keyword_terms = set(tokenize(" ".join(self.note.keywords)))
        return bool(keyword_terms & set(self.matched_terms))


def tokenize(text: str) -> List[str]:
    """Lowercases, splits on non-letters, drops stopwords and single characters.

    `r&b` is folded to `rnb` first because it is a genre name in the catalog and would
    otherwise split into `r` and `b` and be discarded as too short.
    """
    lowered = str(text or "").lower().replace("r&b", "rnb")
    raw = re.findall(r"[a-z0-9]+", lowered)
    return [word for word in raw if len(word) > 1 and word not in STOPWORDS]


def _coerce_hint(key: str, raw: str) -> object:
    """Turns a frontmatter hint string into the type the scoring layer expects."""
    value = raw.strip()
    if key in _LIST_HINTS:
        return [part.strip() for part in value.split(",") if part.strip()]
    if key in _BOOL_HINTS:
        return value.lower() in ("true", "yes", "1")
    if key in _FLOAT_HINTS:
        try:
            return float(value)
        except ValueError:
            return None
    if key in _INT_HINTS:
        try:
            return int(float(value))
        except ValueError:
            return None
    return value


def parse_note(text: str, path: Optional[Path] = None) -> Note:
    """Parses one note file: `---` frontmatter, then prose.

    The frontmatter is a deliberately tiny subset of YAML (flat `key: value` pairs plus one
    indented `hints:` block) so the project needs no YAML dependency. A malformed or missing
    frontmatter block is not fatal -- the note still retrieves on its body text, it just
    contributes no hints.
    """
    front: Dict[str, str] = {}
    hints: Dict[str, object] = {}
    body = text

    match = re.match(r"\s*---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if match:
        block, body = match.group(1), match.group(2)
        in_hints = False
        for line in block.splitlines():
            if not line.strip():
                continue
            indented = line[:1].isspace()
            if line.strip() == "hints:":
                in_hints = True
                continue
            if ":" not in line:
                continue
            key, _, raw = line.strip().partition(":")
            key = key.strip()
            if in_hints and indented:
                coerced = _coerce_hint(key, raw)
                if coerced not in (None, "", []):
                    hints[key] = coerced
            else:
                in_hints = False
                front[key] = raw.strip()

    note_id = front.get("id") or (path.stem if path else "untitled")
    return Note(
        id=note_id,
        title=front.get("title", note_id),
        kind=front.get("kind", "note"),
        keywords=[k.strip().lower() for k in front.get("keywords", "").split(",") if k.strip()],
        hints=hints,
        body=body,
        path=path,
    )


def load_notes(notes_dir=DEFAULT_NOTES_DIR) -> List[Note]:
    """Reads every `.md` note in a directory, sorted by filename so runs are reproducible."""
    directory = Path(notes_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"notes directory not found: {directory}")
    notes = [parse_note(p.read_text(encoding="utf-8"), p) for p in sorted(directory.glob("*.md"))]
    if not notes:
        raise ValueError(f"no notes found in {directory}")
    return notes


class NoteRetriever:
    """BM25 retriever over the note corpus.

    Each note is indexed as one bag of words built from its keywords (boosted), title
    (boosted) and body, so a query word the author listed as a keyword outranks the same
    word appearing once in prose.
    """

    def __init__(self, notes: List[Note]):
        self.notes = list(notes)
        self._doc_terms: List[Dict[str, float]] = []
        self._doc_len: List[float] = []
        self._df: Dict[str, int] = {}

        for note in self.notes:
            counts: Dict[str, float] = {}
            for term in tokenize(" ".join(note.keywords)):
                counts[term] = counts.get(term, 0.0) + KEYWORD_FIELD_BOOST
            for term in tokenize(note.title):
                counts[term] = counts.get(term, 0.0) + TITLE_FIELD_BOOST
            for term in tokenize(note.body):
                counts[term] = counts.get(term, 0.0) + 1.0
            self._doc_terms.append(counts)
            self._doc_len.append(sum(counts.values()))
            for term in counts:
                self._df[term] = self._df.get(term, 0) + 1

        self._n = len(self.notes)
        self._avg_len = (sum(self._doc_len) / self._n) if self._n else 0.0

    def _idf(self, term: str) -> float:
        """Standard BM25 inverse document frequency, floored at 0 for ubiquitous terms."""
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        return max(0.0, math.log((self._n - df + 0.5) / (df + 0.5) + 1.0))

    def search(self, query: str, k: int = 3) -> List[Hit]:
        """Returns the k best-matching notes, highest score first.

        Ties break on note id so the same query always produces the same ordering, which the
        reproducibility tests depend on.
        """
        terms = tokenize(query)
        if not terms:
            return []

        scored: List[Hit] = []
        for index, note in enumerate(self.notes):
            counts = self._doc_terms[index]
            length = self._doc_len[index] or 1.0
            total = 0.0
            matched: List[str] = []
            for term in set(terms):
                tf = counts.get(term, 0.0)
                if tf <= 0:
                    continue
                idf = self._idf(term)
                denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * length / (self._avg_len or 1.0))
                total += idf * (tf * (BM25_K1 + 1)) / denominator
                matched.append(term)
            if total > 0:
                scored.append(Hit(note=note, score=round(total, 4), matched_terms=sorted(matched)))

        scored.sort(key=lambda hit: (-hit.score, hit.note.id))
        return scored[:k]

    def strength(self, hits: List[Hit]) -> float:
        """Normalises the top hit's score into a 0-1 "did retrieval actually find anything".

        Feeds the confidence score. The divisor is empirical: a clearly on-topic request
        ("gym playlist") scores around 6-9 against this corpus, so 8.0 maps a strong match to
        roughly 1.0 and a single weak word to near 0.
        """
        if not hits:
            return 0.0
        return round(min(1.0, hits[0].score / 8.0), 3)


def merge_hints(hits: List[Hit]) -> Dict[str, object]:
    """Collapses the hints of several retrieved notes into one set of profile defaults.

    The top hit wins any key it defines: a specific listening-context note ("workout") should
    not have its energy target averaged away by a general genre note that happened to also
    retrieve. Lower-ranked notes only fill in keys nobody above them set, and numeric keys
    are left as the leader's value rather than blended, because the mean of "sleep at 0.22"
    and "party at 0.86" is a profile that serves neither.

    Notes scoring below `HINT_FLOOR_RATIO` of the top hit are read for grounding prose but
    contribute no hints, so a faint keyword collision cannot smuggle in a target the user
    never implied.
    """
    merged: Dict[str, object] = {}
    provenance: Dict[str, str] = {}
    if not hits:
        return merged

    floor = hits[0].score * HINT_FLOOR_RATIO
    for hit in hits:
        if hit.score < floor:
            continue
        for key, value in hit.hints.items():
            if key not in merged:
                merged[key] = value
                provenance[key] = hit.id
    if merged:
        merged["_provenance"] = provenance
    return merged
