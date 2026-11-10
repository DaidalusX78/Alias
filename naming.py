"""
Pure naming, metadata parsing, and tag extraction functions for Alias.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from guessit import guessit
from mutagen import File as MutagenFile

INVALID_WIN_CHARS = r'[<>:"/\\|?*]'
AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv"}
SUB_EXTS = {".srt"}
SUB_DIR_NAMES = {"subs", "sub", "subtitles", "subtitle"}
PROMO_KEYWORDS = {"sample", "rarbg", "etrg", "trailer", "featurette", "extras"}

# Scan-level guessit memoization cache to prevent redundant re-parsing
_GUESSIT_CACHE: dict[str, dict[str, Any]] = {}


def clear_guessit_cache() -> None:
    _GUESSIT_CACHE.clear()


def safe_guessit(name: str) -> dict[str, Any]:
    """Cached wrapper around guessit. Runs once per unique filename string."""
    if name not in _GUESSIT_CACHE:
        try:
            _GUESSIT_CACHE[name] = dict(guessit(name))
        except Exception:
            _GUESSIT_CACHE[name] = {}
    return _GUESSIT_CACHE[name]


def sanitize_filename(name: str) -> str:
    """Strips characters illegal under Windows NTFS/FAT32, turning colons into dashes."""
    cleaned = re.sub(r"\s*:\s*", " - ", name)
    sanitized = re.sub(INVALID_WIN_CHARS, "", cleaned)
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.strip(" .")


def is_collision(candidate: Path, original: Path) -> bool:
    """Check if candidate path exists and is truly a different file/directory."""
    if not candidate.exists():
        return False
    try:
        return not candidate.samefile(original)
    except Exception:
        return str(candidate.resolve()).lower() != str(original.resolve()).lower()


def safe_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except Exception:
        return 0


def collect_subtitle_files(video_dir: Path) -> list[Path]:
    """Find .srt files directly in video_dir or inside any Subs/Subtitles subfolder."""
    srt_files: list[Path] = []
    try:
        srt_files = [p for p in video_dir.iterdir() if p.is_file() and p.suffix.lower() in SUB_EXTS]
        for child in video_dir.iterdir():
            if child.is_dir() and child.name.lower() in SUB_DIR_NAMES:
                for sub_file in child.rglob("*"):
                    if sub_file.is_file() and sub_file.suffix.lower() in SUB_EXTS:
                        srt_files.append(sub_file)
    except Exception:
        pass
    return sorted(srt_files, key=lambda p: str(p).lower())


def pick_primary_video(video_tuples: list[tuple[Path, str, str]]) -> tuple[Path, str, str]:
    """Pick primary video from a list of (video_path, new_stem, id), filtering promo clips."""
    non_promo = [
        item for item in video_tuples
        if not any(kw in item[0].stem.lower() for kw in PROMO_KEYWORDS)
    ]
    candidates = non_promo if non_promo else video_tuples
    return max(candidates, key=lambda item: safe_size(item[0]))


def extract_special_tags(*sources: str) -> list[str]:
    """
    Extracts edition cuts, 3D formats, and resolution tags from filenames or folder names.
    Supports: Extended Cut, Directors Cut, Final Cut, Theatrical Cut, Unrated, Special Edition,
    3D H-SBS, 3D SBS, 3D H-OU, 3D OU, 3D MVC, 3D, 4K, 2K.
    """
    text = " ".join(sources)
    tags: list[str] = []

    # 1. Edition / Cut (tight boundaries so bare 'extended' doesn't match ordinary titles)
    if re.search(r"\b(extended[\s._-]director\'?s?[\s._-]cut)\b", text, re.IGNORECASE):
        tags.append("Extended Directors Cut")
    elif re.search(
        r"\b(director\'?s?[\s._-]cut|montaje[\s._-]del[\s._-]director|versi[oó]n[\s._-]del[\s._-]director)\b",
        text,
        re.IGNORECASE,
    ):
        tags.append("Directors Cut")
    elif re.search(r"\b(final[\s._-]cut|montaje[\s._-]final)\b", text, re.IGNORECASE):
        tags.append("Final Cut")
    elif re.search(
        r"\b(extended[\s._-]cut|extended[\s._-]edition|versi[oó]n[\s._-]extendida|edici[oó]n[\s._-]extendida)\b",
        text,
        re.IGNORECASE,
    ):
        tags.append("Extended Cut")
    elif re.search(r"\b(theatrical[\s._-]cut|versi[oó]n[\s._-]de[\s._-]cine)\b", text, re.IGNORECASE):
        tags.append("Theatrical Cut")
    elif re.search(r"\b(unrated|sin[\s._-]censura)\b", text, re.IGNORECASE):
        tags.append("Unrated")
    elif re.search(r"\b(special[\s._-]edition|edici[oó]n[\s._-]especial)\b", text, re.IGNORECASE):
        tags.append("Special Edition")
    elif re.search(r"\b(remastered|remasterizada?)\b", text, re.IGNORECASE):
        tags.append("Remastered")

    # 2. 3D & 3D Formats
    if re.search(r"\b(h[\s._-]?sbs|half[\s._-]?sbs)\b", text, re.IGNORECASE):
        tags.append("3D H-SBS")
    elif re.search(r"\b(h[\s._-]?ou|half[\s._-]?ou|h[\s._-]?tab|half[\s._-]?tab)\b", text, re.IGNORECASE):
        tags.append("3D H-OU")
    elif re.search(r"\b(sbs)\b", text, re.IGNORECASE) and re.search(r"\b(3d)\b", text, re.IGNORECASE):
        tags.append("3D SBS")
    elif re.search(r"\b(ou|tab)\b", text, re.IGNORECASE) and re.search(r"\b(3d)\b", text, re.IGNORECASE):
        tags.append("3D OU")
    elif re.search(r"\b(3d[\s._-]?mvc|mvc)\b", text, re.IGNORECASE) and re.search(r"\b(3d)\b", text, re.IGNORECASE):
        tags.append("3D MVC")
    elif re.search(r"\b3d\b", text, re.IGNORECASE):
        tags.append("3D")

    # 3. Resolution (4K, 2K)
    if re.search(r"\b(4k|2160p|uhd)\b", text, re.IGNORECASE):
        tags.append("4K")
    elif re.search(r"\b(2k|1440p)\b", text, re.IGNORECASE):
        tags.append("2K")

    return tags


def find_changing_digit_ranges(orig: str, new: str) -> list[tuple[int, int]]:
    """
    Identifies ranges (start, end) of digits in `new` that are new or changed from `orig`.
    Used to highlight changing digits in the UI with a contrasting color.
    """
    new_numbers = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\d+", new)]
    orig_numbers = set(re.findall(r"\d+", orig))

    ranges: list[tuple[int, int]] = []
    for start, end, val in new_numbers:
        if val not in orig_numbers or orig.count(val) != new.count(val):
            ranges.append((start, end))
    return ranges


def resolve_audio_name(filepath: Path, audiodb_client: Any = None) -> str:
    """Extract ID3/Vorbis tags: [Artist - ]Track - Title.ext, enriched with TheAudioDB if available."""
    try:
        audio = MutagenFile(filepath, easy=True)
        if audio and "title" in audio:
            title = audio["title"][0]
            artist = audio["artist"][0] if "artist" in audio else ""
            track_list = audio.get("tracknumber", [""])
            track = track_list[0].split("/")[0].zfill(2) if track_list[0] else ""

            if audiodb_client and artist:
                db_track = audiodb_client.search_track(artist, title)
                if db_track:
                    artist = db_track.get("strArtist", artist)
                    title = db_track.get("strTrack", title)
                    if not track and db_track.get("intTrackNumber"):
                        track = str(db_track["intTrackNumber"]).zfill(2)

            title = capitalize_title(title)
            if artist:
                artist = capitalize_title(artist)

            # Check if artist is already part of the parent folder structure (e.g. Music/Queen/Album or Queen - Album)
            parent_name = filepath.parent.name.lower()
            grandparent_name = filepath.parent.parent.name.lower() if filepath.parent.parent != filepath.parent else ""
            artist_in_path = bool(artist and (artist.lower() in parent_name or artist.lower() in grandparent_name))

            if artist and not artist_in_path:
                if track:
                    new_str = f"{artist} - {track} - {title}{filepath.suffix}"
                else:
                    new_str = f"{artist} - {title}{filepath.suffix}"
            else:
                # Standard album folder format (Plex/Kodi/iTunes recommendation: 01 - Title.ext)
                if track:
                    new_str = f"{track} - {title}{filepath.suffix}"
                else:
                    new_str = f"{title}{filepath.suffix}"
            return sanitize_filename(new_str)
    except Exception:
        pass
    return filepath.name


LOWERCASE_WORDS = {
    # English
    "a", "an", "the", "and", "but", "or", "for", "nor", "on", "at", "to",
    "from", "by", "with", "in", "of",
    # Spanish
    "de", "del", "la", "las", "los", "el", "al", "y", "e", "o", "u",
    "en", "por", "para", "con", "sin", "un", "una", "unos", "unas", "que",
}

ROMAN_NUMERALS = {"ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"}


def capitalize_word(w: str) -> str:
    if not w:
        return ""
    if "-" in w and not w.startswith("-"):
        return "-".join(capitalize_word(part) for part in w.split("-"))
    if w.lower() in ROMAN_NUMERALS:
        return w.upper()
    if any(c.isdigit() for c in w):
        return w
    return w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper()


def capitalize_title(title: str) -> str:
    """
    Applies consistent title casing across English and Spanish titles.
    Preserves lowercase articles/prepositions unless at segment boundary or start.
    Preserves uppercase Roman numerals (e.g. II, III, IV).
    """
    if not title:
        return ""
    segments = re.split(r"(\s*[-:]\s*)", title)
    result_segments = []
    for seg in segments:
        if re.match(r"^\s*[-:]\s*$", seg):
            result_segments.append(seg)
            continue
        words = seg.split(" ")
        capped = []
        for i, w in enumerate(words):
            if not w:
                capped.append(w)
                continue
            w_lower = w.lower()
            if i == 0:
                capped.append(capitalize_word(w))
            elif w_lower in LOWERCASE_WORDS:
                capped.append(w_lower)
            else:
                capped.append(capitalize_word(w))
        result_segments.append(" ".join(capped))
    return "".join(result_segments)


def extract_full_title(guess: dict[str, Any], fallback_stem: str) -> str:
    """Extracts the base title and any franchise subtitles / chapters from guessit dict."""
    raw_title = guess.get("title", fallback_stem)
    title = raw_title[0] if isinstance(raw_title, list) else str(raw_title)

    # Clean web/pirate release prefixes (e.g. 'Ver Madagascar' -> 'Madagascar')
    title = re.sub(r"^(?:ver|pel[ií]cula|descargar)\s+[-_.]?\s*", "", title, flags=re.IGNORECASE).strip()

    raw_alt = guess.get("alternative_title")
    alt_parts: list[str] = []
    if raw_alt:
        if isinstance(raw_alt, list):
            alt_parts = [str(a).strip() for a in raw_alt if str(a).strip()]
        elif str(raw_alt).strip():
            alt_parts = [str(raw_alt).strip()]

    # Filter out edition cuts that should be formatted as bracketed tags instead of part of title
    valid_alt_parts = [p for p in alt_parts if not extract_special_tags(p)]
    if valid_alt_parts:
        title = f"{title} - {' - '.join(valid_alt_parts)}"

    return title


def resolve_video_name(filepath: Path, tmdb_client: Any = None, tvmaze_client: Any = None) -> str:
    """Extract metadata using guessit, enriched via TVMaze (free) or TMDb when configured."""
    guess = safe_guessit(filepath.name)
    title = extract_full_title(guess, filepath.stem)

    # TV Episode handling
    if "season" in guess and "episode" in guess:
        raw_season = guess["season"]
        season = int(raw_season[0] if isinstance(raw_season, list) else raw_season)
        s_pad = str(season).zfill(2)

        raw_episode = guess["episode"]
        if isinstance(raw_episode, list):
            episodes = [int(ep) for ep in raw_episode]
            first_ep = episodes[0]
            e_pad = "-E".join(str(ep).zfill(2) for ep in episodes)
        else:
            first_ep = int(raw_episode)
            e_pad = str(first_ep).zfill(2)

        ep_title = guess.get("episode_title", "")
        if isinstance(ep_title, list):
            ep_title = " / ".join(str(t) for t in ep_title)

        # 1. Try TMDb if configured
        if tmdb_client and tmdb_client.is_configured():
            show_data = tmdb_client.search_tv_show(title)
            if show_data:
                orig_name = show_data.get("original_name", "")
                orig_lang = show_data.get("original_language", "")

                if orig_lang == "es" and orig_name:
                    title = orig_name
                else:
                    title = show_data.get("name", title)

                ep_data = tmdb_client.get_episode_details(show_data["id"], season, first_ep)
                if ep_data and ep_data.get("name"):
                    ep_title = ep_data["name"]

        # 2. Free TVMaze fallback if ep_title is still missing
        if not ep_title and tvmaze_client:
            tvm_show = tvmaze_client.search_show(title)
            if tvm_show:
                title = tvm_show.get("name", title)
                tvm_title = tvmaze_client.get_episode_title(tvm_show.get("id", 0), season, first_ep)
                if tvm_title:
                    ep_title = tvm_title

        title = capitalize_title(title)
        if ep_title:
            ep_title = capitalize_title(ep_title)
        sub_part = f" - {ep_title}" if ep_title else ""
        return sanitize_filename(f"{title} - S{s_pad}E{e_pad}{sub_part}{filepath.suffix}")

    # Movie handling
    raw_year = guess.get("year", "")
    year = str(raw_year[0] if isinstance(raw_year, list) else raw_year) if raw_year else ""
    if tmdb_client and tmdb_client.is_configured():
        movie_data = tmdb_client.search_movie(title, year if year else None)
        if movie_data:
            rel_date = movie_data.get("release_date", "")
            match_year = rel_date[:4] if (rel_date and len(rel_date) >= 4) else ""
            # Only adopt TMDb metadata if the years are compatible (within 2 years) or if no original year was known
            year_compatible = True
            if year and match_year:
                try:
                    if abs(int(year) - int(match_year)) > 2:
                        year_compatible = False
                except ValueError:
                    pass

            if year_compatible:
                orig_title = movie_data.get("original_title", "")
                orig_lang = movie_data.get("original_language", "")

                if orig_lang == "es" and orig_title:
                    title = orig_title
                else:
                    title = movie_data.get("title", title)

                if match_year:
                    year = match_year

    title = capitalize_title(title)

    # Check tags on both file and immediate parent folder (if single movie folder)
    tags = extract_special_tags(filepath.stem, filepath.parent.name)
    tag_str = f" [{' '.join(tags)}]" if tags else ""
    if year:
        return sanitize_filename(f"{title} ({year}){tag_str}{filepath.suffix}")
    return sanitize_filename(f"{title}{tag_str}{filepath.suffix}")


def resolve_subtitle_name(srt_path: Path, old_video_stem: str, new_video_stem: str, total_srts_in_dir: int) -> str:
    """Build proposed .srt filename based on the associated video's new stem."""
    srt_stem = srt_path.stem

    if total_srts_in_dir == 1:
        return sanitize_filename(f"{new_video_stem}{srt_path.suffix}")

    # Retain subtitle identifier (e.g. English, 2_English, en)
    if old_video_stem and srt_stem.lower().startswith(old_video_stem.lower()):
        remainder = srt_stem[len(old_video_stem):].strip(" ._-")
    elif new_video_stem and srt_stem.lower().startswith(new_video_stem.lower()):
        remainder = srt_stem[len(new_video_stem):].strip(" ._-")
    else:
        remainder = srt_stem.strip(" ._-")

    if remainder:
        return sanitize_filename(f"{new_video_stem}.{remainder}{srt_path.suffix}")
    return sanitize_filename(f"{new_video_stem}{srt_path.suffix}")


def resolve_folder_name(
    folder_path: Path,
    video_tuples: list[tuple[Path, str, str]],
    tmdb_client: Any = None,
    tvmaze_client: Any = None
) -> tuple[str, bool]:
    """
    Computes proposed folder name for folder_path containing video_tuples.
    Returns tuple of (proposed_folder_name, collision_skipped_flag).

    Key behaviors:
    1. If folder is ALREADY a Season folder ('Season 1', 'Season 01', 'Specials'), preserve it.
    2. If folder has an episode tag (e.g. 'Humans - S01E01') and parent already has 'Season 1',
       SKIP the rename and flag it (avoids creating Season 1_1).
    3. For movie folders, match primary video stem 100%.
    """
    if not video_tuples:
        return folder_path.name, False

    # 1. Already a Season folder -> preserve
    m_season = re.match(r"^(Season|Series|Specials)[\s._-]*(\d*)$", folder_path.name, re.IGNORECASE)
    if m_season:
        return folder_path.name, False

    non_promo = [
        item for item in video_tuples
        if not any(kw in item[0].stem.lower() for kw in PROMO_KEYWORDS)
    ]
    candidates = non_promo if non_promo else video_tuples

    # Check if files in this folder are TV episodes
    tv_info: list[tuple[str, int | None, str]] = []
    for v_path, _, _ in candidates:
        guess = safe_guessit(v_path.name)
        if "season" in guess or "episode" in guess:
            title = extract_full_title(guess, v_path.stem)

            s_val = guess.get("season")
            season = None
            if s_val is not None:
                try:
                    season = int(s_val[0] if isinstance(s_val, list) else s_val)
                except Exception:
                    pass

            raw_y = guess.get("year")
            y_str = str(raw_y[0] if isinstance(raw_y, list) else raw_y) if raw_y else ""
            tv_info.append((title, season, y_str))

    # If at least half of the videos have TV episode metadata
    if tv_info and len(tv_info) >= len(candidates) / 2:
        titles = [t for t, _, _ in tv_info if t]
        show_title = titles[0] if titles else ""
        if tmdb_client and tmdb_client.is_configured() and show_title:
            show_data = tmdb_client.search_tv_show(show_title)
            if show_data and show_data.get("name"):
                show_title = show_data["name"]
        elif tvmaze_client and show_title:
            tvm_show = tvmaze_client.search_show(show_title)
            if tvm_show and tvm_show.get("name"):
                show_title = tvm_show["name"]

        seasons = sorted({s for _, s, _ in tv_info if s is not None})
        years = [y for _, _, y in tv_info if y]
        year = years[0] if years else ""
        if not year:
            m_year = re.search(r"\((\d{4})\)", folder_path.name)
            if m_year:
                year = m_year.group(1)

        has_ep_tag = bool(re.search(r"[-_\s]S\d+E\d+", folder_path.name, re.IGNORECASE))
        parent_name = folder_path.parent.name
        is_subfolder_of_show = (
            bool(re.search(r"\(\d{4}\)", parent_name))
            or (show_title and show_title.lower() in parent_name.lower())
            or (show_title and parent_name.lower() in show_title.lower())
        )

        # Season folder naming (supports Spanish 'Temporada' and English 'Season')
        is_spanish_named = bool(re.match(r"^temporada\s+\d+", folder_path.name, re.IGNORECASE))
        is_spanish_pref = getattr(tmdb_client, "language", "en-US").startswith("es") if tmdb_client else False

        # Single season subfolder
        if len(seasons) == 1 and (has_ep_tag or is_subfolder_of_show):
            season_word = "Temporada" if (is_spanish_named or is_spanish_pref) else "Season"
            target_season_name = f"{season_word} {seasons[0]}"
            target_path = folder_path.parent / target_season_name
            # If target Season N already exists on disk and is a DIFFERENT folder, skip to avoid Season N_1!
            if is_collision(target_path, folder_path):
                return folder_path.name, True  # collision skipped
            return target_season_name, False

        # Multiple seasons
        if len(seasons) > 1 and (has_ep_tag or is_subfolder_of_show):
            seasons_word = "Temporadas" if (is_spanish_named or is_spanish_pref) else "Seasons"
            return f"{seasons_word} {min(seasons)}-{max(seasons)}", False

        # TV Show root folder itself
        show_title = capitalize_title(show_title)
        tags = extract_special_tags(folder_path.name)
        tag_str = f" [{' '.join(tags)}]" if tags else ""
        if year:
            return sanitize_filename(f"{show_title} ({year}){tag_str}"), False
        return sanitize_filename(f"{show_title}{tag_str}") if show_title else folder_path.name, False

    # Movie folder: directly match primary video stem (100% agreement guaranteed)
    _, primary_new_stem, _ = pick_primary_video(candidates)
    if primary_new_stem:
        return sanitize_filename(primary_new_stem), False

    tags = extract_special_tags(folder_path.name)
    tag_str = f" [{' '.join(tags)}]" if tags else ""
    return sanitize_filename(f"{folder_path.name}{tag_str}"), False


def normalize_duplicate_key(name: str) -> str:
    """
    Normalizes a folder or media file name into a canonical grouping key to detect duplicates.
    Removes file extensions, tags in brackets like [3D H-SBS] or [1080p],
    annotations like (auto-synced), and collision suffixes like _1, _2, (1), - Copy.
    Preserves 4-digit release years like (2014) and movie sequel numbers like 'Iron Man 3'.
    """
    stem = Path(name).stem if ("." in name and not name.startswith(".")) else name

    # Remove UI annotations
    stem = re.sub(r"\s*\((auto-synced|create & move into)\)", "", stem, flags=re.IGNORECASE)

    # Remove tags in square brackets e.g. [3D H-SBS], [1080p], [Extended Cut]
    stem = re.sub(r"\s*\[[^\]]*\]", "", stem)

    # Remove collision suffixes: _1, _2, (1), (2), - Copy, Copy (2), etc.
    # Note: \d{1,2} ensures 4-digit years like (2014) are NOT stripped!
    stem = re.sub(
        r"(_\d+|\s*\(\d{1,2}\)|\s*-\s*copy(\s*\d+)?|\s*copy\s*\d*)$",
        "",
        stem,
        flags=re.IGNORECASE
    )

    # Normalize internal punctuation and whitespace for robust comparison
    stem = re.sub(r"[-_.:]", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip().lower()
    return stem

