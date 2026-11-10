"""
Unit tests for Alias naming and resolution logic.
Covers tag extraction, subtitle resolution, folder naming, and digit diffing.
"""

from pathlib import Path

from naming import (
    extract_special_tags,
    find_changing_digit_ranges,
    resolve_folder_name,
    resolve_subtitle_name,
    resolve_video_name,
    sanitize_filename,
)


def test_sanitize_filename():
    assert sanitize_filename('Show: The "Best" Movie? *Special*') == "Show - The Best Movie Special"
    assert sanitize_filename("Folder: Part 1/2") == "Folder - Part 12"


def test_extract_special_tags_editions():
    assert "Extended Cut" in extract_special_tags("The Martian Extended Cut 4K (2015)")
    assert "Directors Cut" in extract_special_tags("Blade Runner Directors Cut")
    assert "Final Cut" in extract_special_tags("Apocalypse Now Final Cut")
    assert "Theatrical Cut" in extract_special_tags("Avatar Theatrical Cut")
    assert "Unrated" in extract_special_tags("Movie Title Unrated Edition")


def test_extract_special_tags_3d_and_resolutions():
    tags = extract_special_tags("Avatar (2009) 3D H-SBS 2160p")
    assert "3D H-SBS" in tags
    assert "4K" in tags

    tags_ou = extract_special_tags("Gravity.2013.3D.Half-OU.1080p")
    assert "3D H-OU" in tags_ou

    tags_2k = extract_special_tags("Avengers 2K")
    assert "2K" in tags_2k


def test_find_changing_digit_ranges():
    orig = "Humans - S01E01"
    new = "Humans - S01 - E01-E08"
    ranges = find_changing_digit_ranges(orig, new)
    assert len(ranges) == 1
    start, end = ranges[0]
    assert new[start:end] == "08"

    # Same digits in both strings -> no change
    assert find_changing_digit_ranges("Movie (2015)", "Movie (2015)") == []


def test_resolve_subtitle_name_single():
    srt = Path("C:/Media/Subs/Movie.srt")
    new_name = resolve_subtitle_name(srt, "Movie", "Movie (2024)", total_srts_in_dir=1)
    assert new_name == "Movie (2024).srt"


def test_resolve_subtitle_name_multi_preserves_language():
    srt_eng = Path("C:/Media/Subs/Movie.en.srt")
    new_name = resolve_subtitle_name(srt_eng, "Movie", "Movie (2024)", total_srts_in_dir=2)
    assert new_name == "Movie (2024).en.srt"

    srt_numbered = Path("C:/Media/Subs/2_English.srt")
    new_name2 = resolve_subtitle_name(srt_numbered, "Movie", "Movie (2024)", total_srts_in_dir=2)
    assert new_name2 == "Movie (2024).2_English.srt"


def test_resolve_folder_name_season_folder_preserved():
    # If folder is already "Season 1", it must NOT be renamed to episode names!
    folder = Path("C:/Media/TV/Humans/Season 1")
    videos = [(folder / "Humans - S01E01.mkv", "Humans - S01E01 - Episode 1", "id1")]
    proposed, skipped = resolve_folder_name(folder, videos)
    assert proposed == "Season 1"
    assert skipped is False


def test_resolve_folder_name_movie_matches_video_stem():
    folder = Path("C:/Media/Movies/The Martian Extended Cut 4K (2015)")
    videos = [(
        folder / "The Martian Extended Cut 4K (2015).mkv",
        "The Martian (2015) [Extended Cut 4K]",
        "id1"
    )]
    proposed, skipped = resolve_folder_name(folder, videos)
    assert proposed == "The Martian (2015) [Extended Cut 4K]"
    assert skipped is False


def test_resolve_video_name_franchise_sequels():
    cases = [
        ("John Wick - Chapter 2 (2017).mp4", "John Wick - Chapter 2 (2017).mp4"),
        ("Kingsman - The Golden Circle (2017).mp4", "Kingsman - The Golden Circle (2017).mp4"),
        ("Mission - Impossible II (2000).mp4", "Mission - Impossible II (2000).mp4"),
        ("Pirates of the Caribbean - At World's End (2007).avi", "Pirates of the Caribbean - At World's End (2007).avi"),
        ("Ice Age - A Mammoth Christmas (2011).avi", "Ice Age - A Mammoth Christmas (2011).avi"),
    ]
    for orig, expected in cases:
        result = resolve_video_name(Path(orig), tmdb_client=None)
        assert result == expected


def test_tmdb_client_pick_best_match():
    from metadata import TMDbClient

    results = [
        {"title": "The Curse of the Black Pearl", "release_date": "2003-07-09"},
        {"title": "At World's End", "release_date": "2007-05-19"},
        {"title": "Dead Man's Chest", "release_date": "2006-06-20"},
    ]
    # When requesting 2007, must pick At World's End (2007) not the first item
    best = TMDbClient._pick_best_movie_match(results, "2007")
    assert best["title"] == "At World's End"

    # When requesting 2006, must pick Dead Man's Chest (2006)
    best_2006 = TMDbClient._pick_best_movie_match(results, "2006")
    assert best_2006["title"] == "Dead Man's Chest"


def test_extract_special_tags_spanish():
    assert "Extended Cut" in extract_special_tags("El Senor de los Anillos Version Extendida (2001)")
    assert "Directors Cut" in extract_special_tags("Blade Runner Montaje del Director (1982)")
    assert "Final Cut" in extract_special_tags("Apocalypse Now Montaje Final")
    assert "Special Edition" in extract_special_tags("Star Wars Edicion Especial (1977)")
    assert "Unrated" in extract_special_tags("Pelicula Sin Censura (2005)")
    assert "Remastered" in extract_special_tags("Clasico Remasterizada (1960)")


def test_resolve_folder_name_spanish_season():
    folder = Path("C:/Media/TV/La casa de papel (2017)/Temporada 1")
    videos = [(folder / "La casa de papel - S01E01.mkv", "La casa de papel - S01E01", "id1")]
    proposed, skipped = resolve_folder_name(folder, videos)
    assert proposed == "Temporada 1"
    assert skipped is False


def test_resolve_video_name_preserves_spanish_original():
    class DummyTMDb:
        def __init__(self, language="en-US"):
            self.language = language

        def is_configured(self):
            return True

        def search_movie(self, title, year=None):
            if "laberinto" in title.lower():
                return {
                    "title": "Pan's Labyrinth",
                    "original_title": "El laberinto del fauno",
                    "original_language": "es",
                    "release_date": "2006-10-11",
                }
            return None

    # In English mode, a film whose original language is Spanish preserves its Spanish title
    client_en = DummyTMDb(language="en-US")
    res_en = resolve_video_name(Path("El laberinto del fauno (2006).mkv"), tmdb_client=client_en)
    assert "El Laberinto del Fauno" in res_en

    # In Spanish mode, it returns the Spanish title
    client_es = DummyTMDb(language="es-ES")
    res_es = resolve_video_name(Path("El laberinto del fauno (2006).mkv"), tmdb_client=client_es)
    assert "El Laberinto del Fauno" in res_es


def test_capitalize_title_spanish_and_english():
    from naming import capitalize_title

    assert capitalize_title("el rey león") == "El Rey León"
    assert capitalize_title("el libro de la vida") == "El Libro de la Vida"
    assert capitalize_title("los boxtrolls") == "Los Boxtrolls"
    assert capitalize_title("mission - impossible ii") == "Mission - Impossible II"
    assert capitalize_title("the lord of the rings") == "The Lord of the Rings"


def test_tmdb_strict_year_cutoff():
    from metadata import TMDbClient

    results = [
        {"title": "Ice Age: Dawn of the Dinosaurs", "release_date": "2009-06-26"},
    ]
    # File is dated 2014, movie in result is 2009 (5 years apart) -> must NOT pick it!
    match = TMDbClient._pick_best_movie_match(results, "2014")
    assert match is None

    # Within 2 years (e.g. 2010 vs 2009) is accepted for release date variations
    match_close = TMDbClient._pick_best_movie_match(results, "2010")
    assert match_close is not None


def test_loose_file_folder_resolution():
    loose_video = Path("M:/Shared Videos/Gladiator.2000.1080p.mp4")
    resolved_video = resolve_video_name(loose_video, tmdb_client=None)
    assert resolved_video == "Gladiator (2000).mp4"

    # Corresponding folder stem
    target_folder_name = Path(resolved_video).stem
    assert target_folder_name == "Gladiator (2000)"

    # Subtitle for loose video
    loose_srt = Path("M:/Shared Videos/Gladiator.2000.srt")
    resolved_sub = resolve_subtitle_name(loose_srt, loose_video.stem, target_folder_name, 1)
    assert resolved_sub == "Gladiator (2000).srt"


def test_normalize_duplicate_key():
    from naming import normalize_duplicate_key

    # Folders with collision suffix _1
    assert normalize_duplicate_key("Guardians of the Galaxy (2014)_1") == "guardians of the galaxy (2014)"
    assert normalize_duplicate_key("Guardians of the Galaxy (2014)") == "guardians of the galaxy (2014)"
    assert normalize_duplicate_key("Guardians of the Galaxy (2014) (auto-synced)") == "guardians of the galaxy (2014)"

    # Files with tags and collision suffixes
    assert normalize_duplicate_key("Hercules (1997)_1") == normalize_duplicate_key("Hercules (1997)")
    assert normalize_duplicate_key("Logan (2017)_1") == normalize_duplicate_key("Logan (2017)")
    assert normalize_duplicate_key("Gladiator (2000) (1).mp4") == normalize_duplicate_key("Gladiator (2000).mp4")
    assert normalize_duplicate_key("Avatar (2009) [3D H-SBS].mkv") == normalize_duplicate_key("Avatar (2009) [1080p].mp4")
    assert normalize_duplicate_key("Avatar (2009) - Copy.mkv") == normalize_duplicate_key("Avatar (2009).mkv")

    # Sequel number without year or collision is preserved
    assert normalize_duplicate_key("Iron Man 3 (2013)") == "iron man 3 (2013)"
    assert normalize_duplicate_key("Iron Man 3 (2013)_1") == "iron man 3 (2013)"


def test_resolve_audio_name_conventions(monkeypatch):
    import naming

    class DummyAudio(dict):
        pass

    def dummy_mutagen(path, easy=True):
        d = DummyAudio()
        d["title"] = ["Bohemian Rhapsody"]
        d["artist"] = ["Queen"]
        d["tracknumber"] = ["1/12"]
        return d

    monkeypatch.setattr(naming, "MutagenFile", dummy_mutagen)

    # 1. Inside an artist / album folder structure -> 01 - Bohemian Rhapsody.mp3 (no redundant artist)
    path_in_album = Path("C:/Music/Queen/A Night at the Opera/track1.mp3")
    res1 = naming.resolve_audio_name(path_in_album)
    assert res1 == "01 - Bohemian Rhapsody.mp3"

    # 2. Inside a combined artist - album folder -> 01 - Bohemian Rhapsody.mp3
    path_in_artist_folder = Path("C:/Music/Queen - Greatest Hits/track1.mp3")
    res2 = naming.resolve_audio_name(path_in_artist_folder)
    assert res2 == "01 - Bohemian Rhapsody.mp3"

    # 3. Inside a loose folder -> Queen - 01 - Bohemian Rhapsody.mp3
    path_loose = Path("C:/Music/Downloads/track1.mp3")
    res3 = naming.resolve_audio_name(path_loose)
    assert res3 == "Queen - 01 - Bohemian Rhapsody.mp3"






