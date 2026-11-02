from src.recommender import (
    Recommender,
    Song,
    UserProfile,
    load_songs,
    recommend_songs,
    score_song,
)

POP_PREFS = {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}


def make_small_recommender() -> Recommender:
    songs = [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]
    return Recommender(songs)


def make_song(**overrides) -> dict:
    song = {
        "id": 99,
        "title": "Fixture",
        "artist": "Fixture Band",
        "genre": "pop",
        "mood": "happy",
        "energy": 0.8,
        "tempo_bpm": 120,
        "valence": 0.8,
        "danceability": 0.8,
        "acousticness": 0.2,
        "popularity": 50,
        "release_decade": 2020,
        "mood_tags": [],
        "language": "english",
        "duration_sec": 210,
    }
    song.update(overrides)
    return song


def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    results = rec.recommend(user, k=2)

    assert len(results) == 2
    # Starter expectation: the pop, happy, high energy song should score higher
    assert results[0].genre == "pop"
    assert results[0].mood == "happy"


def test_explain_recommendation_returns_non_empty_string():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    song = rec.songs[0]

    explanation = rec.explain_recommendation(user, song)
    assert isinstance(explanation, str)
    assert explanation.strip() != ""


def test_load_songs_converts_numbers_and_tags():
    songs = load_songs()
    assert len(songs) == 22
    first = songs[0]
    assert isinstance(first["energy"], float)
    assert isinstance(first["tempo_bpm"], int)
    assert isinstance(first["id"], int)
    assert first["mood_tags"] == ["euphoric", "sunny", "uplifting"]


def test_genre_match_beats_related_genre():
    exact, _ = score_song(POP_PREFS, make_song(genre="pop"))
    related, _ = score_song(POP_PREFS, make_song(genre="indie pop"))
    unrelated, _ = score_song(POP_PREFS, make_song(genre="metal"))
    assert exact > related > unrelated


def test_energy_rewards_closeness_not_loudness():
    prefs = {"genre": "", "mood": "", "energy": 0.4}
    close, _ = score_song(prefs, make_song(energy=0.42))
    far, _ = score_song(prefs, make_song(energy=0.95))
    assert close > far
    # A gap of 0.5 or more earns nothing, rather than going negative.
    assert score_song(prefs, make_song(energy=1.0))[0] == 0.0


def test_reasons_are_returned_with_every_score():
    score, reasons = score_song(POP_PREFS, make_song())
    assert score > 0
    assert any("genre match" in reason for reason in reasons)
    assert all(reason.endswith(")") for reason in reasons)


def test_profile_with_no_preferences_scores_zero_and_says_so():
    score, reasons = score_song({}, make_song())
    assert score == 0.0
    assert reasons == ["nothing in this song matches the profile"]


def test_recommend_songs_respects_k_and_sorts_descending():
    songs = load_songs()
    results = recommend_songs(POP_PREFS, songs, k=5, diversify=False)
    scores = [score for _, score, _ in results]
    assert len(results) == 5
    assert scores == sorted(scores, reverse=True)


def test_recommend_songs_does_not_mutate_the_catalog():
    songs = load_songs()
    before = [song["title"] for song in songs]
    recommend_songs(POP_PREFS, songs, k=5)
    assert [song["title"] for song in songs] == before


def test_diversity_penalty_breaks_up_repeated_artists():
    catalog = [
        make_song(id=1, title="A1", artist="Solo Act", genre="pop", energy=0.80),
        make_song(id=2, title="A2", artist="Solo Act", genre="pop", energy=0.79),
        make_song(id=3, title="A3", artist="Solo Act", genre="pop", energy=0.78),
        make_song(id=4, title="B1", artist="Other Band", genre="rock", mood="intense", energy=0.80),
    ]
    greedy = [song["artist"] for song, _, _ in recommend_songs(POP_PREFS, catalog, k=3, diversify=False)]
    diverse = [song["artist"] for song, _, _ in recommend_songs(POP_PREFS, catalog, k=3, diversify=True)]
    assert greedy == ["Solo Act", "Solo Act", "Solo Act"]
    assert "Other Band" in diverse


def test_scoring_modes_change_the_winner():
    catalog = [
        make_song(id=1, title="On Genre", genre="pop", mood="moody", energy=0.2),
        make_song(id=2, title="On Energy", genre="metal", mood="moody", energy=0.8),
    ]
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8}
    genre_first = recommend_songs(prefs, catalog, k=1, mode="genre_first", diversify=False)
    energy_first = recommend_songs(prefs, catalog, k=1, mode="energy_focused", diversify=False)
    assert genre_first[0][0]["title"] == "On Genre"
    assert energy_first[0][0]["title"] == "On Energy"


def test_discovery_mode_rewards_unknown_songs():
    catalog = [
        make_song(id=1, title="Famous", popularity=95),
        make_song(id=2, title="Obscure", popularity=10),
    ]
    results = recommend_songs(POP_PREFS, catalog, k=2, mode="discovery", diversify=False)
    assert results[0][0]["title"] == "Obscure"


def test_language_scores_only_on_an_exact_match():
    catalog = [
        make_song(id=1, title="In English", language="english"),
        make_song(id=2, title="In Yoruba", language="yoruba"),
        make_song(id=3, title="No Vocals", language="instrumental"),
    ]
    winner = recommend_songs({**POP_PREFS, "language": "yoruba"}, catalog, k=1, diversify=False)
    assert winner[0][0]["title"] == "In Yoruba"
    # "instrumental" is a language of its own, not a wildcard that matches everyone.
    score, reasons = score_song({"language": "english"}, make_song(language="instrumental"))
    assert score == 0.0


def test_duration_term_dies_off_outside_the_tolerance():
    prefs = {"duration_sec": 150}
    assert score_song(prefs, make_song(duration_sec=150))[0] == 0.5
    assert score_song(prefs, make_song(duration_sec=210))[0] == 0.25
    assert score_song(prefs, make_song(duration_sec=400))[0] == 0.0


def test_new_features_are_ignored_when_the_user_omits_them():
    # Adding language/duration must not change the score of a profile that names neither.
    quiet = dict(POP_PREFS)
    assert score_song(quiet, make_song(language="yoruba", duration_sec=400))[0] == score_song(
        quiet, make_song(language="english", duration_sec=150)
    )[0]


def test_acoustic_preference_flips_the_ranking():
    catalog = [
        make_song(id=1, title="Unplugged", acousticness=0.95),
        make_song(id=2, title="Plugged In", acousticness=0.05),
    ]
    likes = recommend_songs({**POP_PREFS, "likes_acoustic": True}, catalog, k=2, diversify=False)
    dislikes = recommend_songs({**POP_PREFS, "likes_acoustic": False}, catalog, k=2, diversify=False)
    assert likes[0][0]["title"] == "Unplugged"
    assert dislikes[0][0]["title"] == "Plugged In"
