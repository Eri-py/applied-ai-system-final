"""Scoring and ranking logic for VibeFinder 1.0, the music recommender simulation.

The module has two layers over the same maths:

- a functional layer (``load_songs`` / ``score_song`` / ``recommend_songs``) that works
  on plain dictionaries, which is what ``src/main.py`` drives, and
- an object layer (``Song`` / ``UserProfile`` / ``Recommender``) that wraps the same
  functions, which is what ``tests/test_recommender.py`` drives.
"""

import csv
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Catalog location, resolved from this file so the CLI works from any directory.
DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "songs.csv"

# Columns that must be read as numbers rather than strings.
FLOAT_COLUMNS = ("energy", "valence", "danceability", "acousticness")
INT_COLUMNS = ("id", "tempo_bpm", "popularity", "release_decade", "duration_sec")


@dataclass
class Song:
    """Represents a song and its attributes."""

    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float
    popularity: int = 50
    release_decade: int = 2020
    mood_tags: List[str] = field(default_factory=list)
    language: str = "english"
    duration_sec: int = 210


@dataclass
class UserProfile:
    """Represents a user's taste preferences."""

    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool
    target_tempo: Optional[int] = None
    favorite_tags: List[str] = field(default_factory=list)
    favorite_decade: Optional[int] = None
    favorite_language: Optional[str] = None
    target_duration: Optional[int] = None
    mode: str = "balanced"


@dataclass(frozen=True)
class ScoringMode:
    """One named set of weights — the 'strategy' a user picks to rank the catalog."""

    name: str
    description: str
    genre: float = 2.0
    partial_genre: float = 1.0
    mood: float = 1.0
    tag: float = 0.4
    max_tag: float = 1.2
    energy: float = 1.5
    energy_tolerance: float = 0.5
    acoustic: float = 0.8
    tempo: float = 1.0
    tempo_tolerance: float = 40.0
    decade: float = 0.5
    language: float = 0.6
    duration: float = 0.5
    duration_tolerance: float = 120.0
    novelty: float = 0.0
    popularity: float = 0.0


# The "Algorithm Recipe" registry. `balanced` is the recipe described in the README;
# the others re-weight the same terms so main.py can switch strategies at runtime.
SCORING_MODES: Dict[str, ScoringMode] = {
    "balanced": ScoringMode(
        name="balanced",
        description="Genre leads, mood and energy follow. The default recipe.",
    ),
    "genre_first": ScoringMode(
        name="genre_first",
        description="Stay inside the user's genre almost no matter what.",
        genre=3.5,
        partial_genre=1.75,
        mood=0.5,
        tag=0.2,
        max_tag=0.6,
        energy=0.75,
    ),
    "mood_first": ScoringMode(
        name="mood_first",
        description="Match the feeling first and let the genre fall where it may.",
        genre=0.75,
        partial_genre=0.4,
        mood=2.5,
        tag=0.6,
        max_tag=1.8,
        energy=1.0,
    ),
    "energy_focused": ScoringMode(
        name="energy_focused",
        description="Hit the right intensity; genre and mood are tie-breakers.",
        genre=0.5,
        partial_genre=0.25,
        mood=0.5,
        tag=0.2,
        max_tag=0.6,
        energy=3.0,
        energy_tolerance=0.35,
        tempo=1.5,
    ),
    "discovery": ScoringMode(
        name="discovery",
        description="Balanced, but pays a bonus for songs the crowd has not found yet.",
        genre=1.0,
        partial_genre=0.5,
        mood=1.0,
        energy=1.5,
        novelty=1.5,
    ),
}

# Penalties applied while building the final list, to stop one artist or genre sweeping
# the top k. See `recommend_songs(..., diversify=True)`.
ARTIST_PENALTY = 1.5
GENRE_PENALTY = 0.75


def _closeness(value: float, target: float, tolerance: float) -> float:
    """Returns 1.0 for an exact match, falling linearly to 0.0 once the gap hits tolerance."""
    gap = abs(float(value) - float(target))
    return max(0.0, 1.0 - gap / tolerance)


def _split_tags(raw) -> List[str]:
    """Turns a 'nostalgic;sleepy' style field (or an existing list) into a clean list."""
    if isinstance(raw, list):
        return [str(tag).strip().lower() for tag in raw if str(tag).strip()]
    return [tag.strip().lower() for tag in str(raw or "").split(";") if tag.strip()]


def get_mode(mode) -> ScoringMode:
    """Looks up a scoring mode by name, accepting a ScoringMode object unchanged."""
    if isinstance(mode, ScoringMode):
        return mode
    return SCORING_MODES[str(mode or "balanced").lower()]


def load_songs(csv_path=DEFAULT_CSV_PATH) -> List[Dict]:
    """Reads the catalog CSV into a list of dicts with numeric fields already converted."""
    songs: List[Dict] = []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            song = dict(row)
            for column in FLOAT_COLUMNS:
                if column in song:
                    song[column] = float(song[column])
            for column in INT_COLUMNS:
                if column in song:
                    song[column] = int(song[column])
            song["mood_tags"] = _split_tags(song.get("mood_tags"))
            songs.append(song)
    return songs


def score_song(user_prefs: Dict, song: Dict, mode=None) -> Tuple[float, List[str]]:
    """Scores one song against one taste profile and returns (score, reasons)."""
    weights = get_mode(mode if mode is not None else user_prefs.get("mode"))
    score = 0.0
    reasons: List[str] = []

    def award(points: float, reason: str) -> None:
        nonlocal score
        if round(points, 2) != 0:
            score += points
            reasons.append(f"{reason} ({points:+.2f})")

    # --- Genre: exact match is worth the most, a shared word ("indie pop" vs "pop")
    # still counts for half, because the starter catalog mixes broad and narrow labels.
    wanted_genre = str(user_prefs.get("genre", "")).strip().lower()
    song_genre = str(song.get("genre", "")).strip().lower()
    if wanted_genre and song_genre:
        if wanted_genre == song_genre:
            award(weights.genre, f"genre match: {song_genre}")
        elif set(wanted_genre.split()) & set(song_genre.split()):
            award(weights.partial_genre, f"related genre: {song_genre} ~ {wanted_genre}")

    # --- Mood: one flat point for the headline mood, plus smaller points per shared
    # descriptive tag so two "chill" songs can still be told apart.
    wanted_mood = str(user_prefs.get("mood", "")).strip().lower()
    song_mood = str(song.get("mood", "")).strip().lower()
    if wanted_mood and wanted_mood == song_mood:
        award(weights.mood, f"mood match: {song_mood}")

    shared_tags = sorted(set(_split_tags(user_prefs.get("mood_tags"))) & set(_split_tags(song.get("mood_tags"))))
    if shared_tags:
        award(min(weights.tag * len(shared_tags), weights.max_tag), f"shared vibe: {', '.join(shared_tags)}")

    # --- Energy: a distance score, not a "higher is better" score. A user who wants
    # 0.4 should be rewarded for a 0.42 song and not for a 0.98 one.
    if user_prefs.get("energy") is not None and song.get("energy") is not None:
        fit = _closeness(song["energy"], user_prefs["energy"], weights.energy_tolerance)
        award(weights.energy * fit, f"energy {song['energy']:.2f} vs target {float(user_prefs['energy']):.2f}")

    # --- Tempo: same distance idea, measured in BPM, only when the user asked for one.
    if user_prefs.get("tempo_bpm") is not None and song.get("tempo_bpm") is not None:
        fit = _closeness(song["tempo_bpm"], user_prefs["tempo_bpm"], weights.tempo_tolerance)
        award(weights.tempo * fit, f"tempo {int(song['tempo_bpm'])} vs target {int(user_prefs['tempo_bpm'])} bpm")

    # --- Acousticness: a yes/no preference turned into a sliding scale.
    if user_prefs.get("likes_acoustic") is not None and song.get("acousticness") is not None:
        wants_acoustic = bool(user_prefs["likes_acoustic"])
        fit = song["acousticness"] if wants_acoustic else 1.0 - song["acousticness"]
        label = "acoustic" if wants_acoustic else "produced"
        award(weights.acoustic * fit, f"{label} texture ({song['acousticness']:.2f} acousticness)")

    # --- Decade and popularity: the optional extras from the stretch dataset.
    if user_prefs.get("decade") is not None and song.get("release_decade") is not None:
        if int(user_prefs["decade"]) == int(song["release_decade"]):
            award(weights.decade, f"from the {int(song['release_decade'])}s")

    # --- Language and length: two more optional preferences, only scored when the user
    # names one. "instrumental" is treated as its own language, not as a wildcard.
    if user_prefs.get("language") and song.get("language"):
        wanted_language = str(user_prefs["language"]).strip().lower()
        if wanted_language == str(song["language"]).strip().lower():
            label = "no vocals" if wanted_language == "instrumental" else f"sung in {wanted_language}"
            award(weights.language, label)

    if user_prefs.get("duration_sec") is not None and song.get("duration_sec") is not None:
        fit = _closeness(song["duration_sec"], user_prefs["duration_sec"], weights.duration_tolerance)
        award(weights.duration * fit, f"length {int(song['duration_sec'])}s vs target {int(user_prefs['duration_sec'])}s")

    if weights.novelty and song.get("popularity") is not None:
        award(weights.novelty * (1.0 - song["popularity"] / 100.0), f"under the radar (popularity {int(song['popularity'])})")
    elif weights.popularity and song.get("popularity") is not None:
        award(weights.popularity * (song["popularity"] / 100.0), f"crowd favourite (popularity {int(song['popularity'])})")

    if not reasons:
        reasons.append("nothing in this song matches the profile")

    return round(score, 2), reasons


def recommend_songs(
    user_prefs: Dict,
    songs: List[Dict],
    k: int = 5,
    mode=None,
    diversify: bool = True,
) -> List[Tuple[Dict, float, str]]:
    """Scores every song, then returns the top k as (song, score, explanation) tuples."""
    weights = get_mode(mode if mode is not None else user_prefs.get("mode"))
    scored = [(song, *score_song(user_prefs, song, weights)) for song in songs]

    # `sorted` returns a new list and leaves the caller's catalog order untouched,
    # which `.sort()` would not. Ties break on title so runs are reproducible.
    ranked = sorted(scored, key=lambda row: (-row[1], row[0]["title"]))

    if not diversify:
        return [(song, score, "; ".join(reasons)) for song, score, reasons in ranked[:k]]

    # Greedy re-ranking: each time an artist or genre is picked, later songs from that
    # artist or genre are discounted, so the top k cannot be one artist five times.
    picked: List[Tuple[Dict, float, str]] = []
    artists_used: Dict[str, int] = {}
    genres_used: Dict[str, int] = {}
    remaining = list(ranked)

    while remaining and len(picked) < k:
        best_index, best_adjusted, best_note = 0, None, ""
        for index, (song, score, _) in enumerate(remaining):
            artist_hits = artists_used.get(song["artist"].lower(), 0)
            genre_hits = genres_used.get(song["genre"].lower(), 0)
            penalty = ARTIST_PENALTY * artist_hits + GENRE_PENALTY * genre_hits
            adjusted = score - penalty
            if best_adjusted is None or adjusted > best_adjusted:
                best_index, best_adjusted = index, adjusted
                best_note = f"diversity penalty ({-penalty:.2f})" if penalty else ""

        song, score, reasons = remaining.pop(best_index)
        explanation = "; ".join(reasons + ([best_note] if best_note else []))
        picked.append((song, round(best_adjusted, 2), explanation))
        artists_used[song["artist"].lower()] = artists_used.get(song["artist"].lower(), 0) + 1
        genres_used[song["genre"].lower()] = genres_used.get(song["genre"].lower(), 0) + 1

    return picked


def profile_to_prefs(user: "UserProfile") -> Dict:
    """Converts a UserProfile object into the preference dict the scoring layer expects."""
    return {
        "genre": user.favorite_genre,
        "mood": user.favorite_mood,
        "energy": user.target_energy,
        "likes_acoustic": user.likes_acoustic,
        "tempo_bpm": user.target_tempo,
        "mood_tags": user.favorite_tags,
        "decade": user.favorite_decade,
        "language": user.favorite_language,
        "duration_sec": user.target_duration,
        "mode": user.mode,
    }


class Recommender:
    """Object wrapper around the scoring functions, holding one catalog of Songs."""

    def __init__(self, songs: List[Song]):
        self.songs = songs

    def recommend(self, user: UserProfile, k: int = 5, diversify: bool = False) -> List[Song]:
        """Returns the k best Song objects for this user, highest score first."""
        ranked = recommend_songs(
            profile_to_prefs(user),
            [asdict(song) for song in self.songs],
            k=k,
            diversify=diversify,
        )
        by_id = {song.id: song for song in self.songs}
        return [by_id[row[0]["id"]] for row in ranked]

    def score(self, user: UserProfile, song: Song) -> float:
        """Returns the numeric score this user's profile gives one song."""
        return score_song(profile_to_prefs(user), asdict(song))[0]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Returns a plain-language sentence listing why this song scored what it did."""
        score, reasons = score_song(profile_to_prefs(user), asdict(song))
        return f"'{song.title}' by {song.artist} scored {score:.2f} — " + "; ".join(reasons)
