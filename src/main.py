"""Command line runner for VibeFinder 1.0.

Run it with:  python -m src.main
Optional flags:
    --mode balanced|genre_first|mood_first|energy_focused|discovery
    --no-diversity    turn the artist/genre diversity penalty off
    --profile NAME    run a single profile instead of all of them
"""

import argparse
import sys
import textwrap

from src.recommender import (
    SCORING_MODES,
    load_songs,
    recommend_songs,
)

# The taste profiles used for the Phase 4 stress test. The last two are the
# adversarial ones: deliberately self-contradictory, to see what the maths does.
PROFILES = {
    "happy_pop": {
        "label": "High-Energy Pop — the starter profile",
        "genre": "pop",
        "mood": "happy",
        "energy": 0.8,
        "likes_acoustic": False,
        "mood_tags": ["sunny", "uplifting"],
    },
    "chill_lofi": {
        "label": "Chill Lofi — studying at 1am",
        "genre": "lofi",
        "mood": "chill",
        "energy": 0.38,
        "likes_acoustic": True,
        "mood_tags": ["sleepy", "nostalgic"],
    },
    "intense_rock": {
        "label": "Deep Intense Rock — gym and traffic",
        "genre": "rock",
        "mood": "intense",
        "energy": 0.92,
        "likes_acoustic": False,
        "tempo_bpm": 155,
        "mood_tags": ["aggressive", "driving"],
    },
    "sad_banger": {
        "label": "Adversarial — wants to cry at 180 bpm (sad mood, 0.9 energy)",
        "genre": "pop",
        "mood": "melancholy",
        "energy": 0.9,
        "likes_acoustic": True,
        "tempo_bpm": 170,
        "mood_tags": ["melancholy", "hype"],
    },
    "empty": {
        "label": "Adversarial — a brand new user who has told us nothing",
        "genre": "",
        "mood": "",
        "energy": None,
        "likes_acoustic": None,
    },
    "unknown_genre": {
        "label": "Adversarial — loves a genre the catalog does not have (polka)",
        "genre": "polka",
        "mood": "happy",
        "energy": 0.5,
        "likes_acoustic": False,
    },
}

COLUMNS = ("#", "Title", "Artist", "Genre", "Mood", "Energy", "Score", "Why")


def describe(profile: dict) -> str:
    """Builds the one-line 'genre=pop, mood=happy, ...' summary printed above a table."""
    parts = []
    for key in ("genre", "mood", "energy", "tempo_bpm", "likes_acoustic", "mood_tags", "decade"):
        value = profile.get(key)
        if value in (None, "", []):
            continue
        parts.append(f"{key}={value}")
    return ", ".join(parts) or "no preferences given"


def render_table(rows: list) -> str:
    """Formats the ranked recommendations as an ASCII table, reasons included."""
    try:
        from tabulate import tabulate
    except ImportError:  # tabulate is a nicety, not a dependency of the logic
        lines = []
        for row in rows:
            lines.append(f"{row[0]}. {row[1]} — {row[2]} | score {row[6]}")
            lines.append(f"   Because: {row[7]}")
        return "\n".join(lines)

    wrapped = [list(row[:-1]) + ["\n".join(textwrap.wrap(row[-1], 46))] for row in rows]
    return tabulate(wrapped, headers=COLUMNS, tablefmt="rounded_grid", floatfmt=".2f")


def run_profile(name: str, profile: dict, songs: list, mode: str, diversify: bool, k: int = 5) -> None:
    """Scores the catalog for one profile and prints the top k as a table."""
    recommendations = recommend_songs(profile, songs, k=k, mode=mode, diversify=diversify)

    print(f"\n=== {profile.get('label', name)} ===")
    print(f"Profile: {describe(profile)}")
    print(f"Mode: {mode} | diversity penalty: {'on' if diversify else 'off'}\n")

    rows = [
        (
            rank,
            song["title"],
            song["artist"],
            song["genre"],
            song["mood"],
            song["energy"],
            score,
            explanation,
        )
        for rank, (song, score, explanation) in enumerate(recommendations, start=1)
    ]
    print(render_table(rows))


def main() -> None:
    # Windows terminals default to cp1252, which cannot print the table borders.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="VibeFinder 1.0 — music recommender simulation")
    parser.add_argument("--mode", default="balanced", choices=sorted(SCORING_MODES), help="scoring strategy")
    parser.add_argument("--profile", default=None, choices=sorted(PROFILES), help="run one profile only")
    parser.add_argument("--no-diversity", action="store_true", help="disable the artist/genre penalty")
    parser.add_argument("-k", type=int, default=5, help="how many songs to recommend")
    args = parser.parse_args()

    songs = load_songs()
    print(f"Loaded songs: {len(songs)}")
    print(f"Scoring mode '{args.mode}': {SCORING_MODES[args.mode].description}")

    chosen = {args.profile: PROFILES[args.profile]} if args.profile else PROFILES
    for name, profile in chosen.items():
        run_profile(name, profile, songs, args.mode, not args.no_diversity, k=args.k)


if __name__ == "__main__":
    main()
