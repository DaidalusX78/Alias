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
