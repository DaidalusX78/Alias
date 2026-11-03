# Alias v1.1.0 — Smart Media Renamer
**Created by Marc Bailey 2026**

Alias is a desktop media library renamer designed for Windows 10 and 11. It automates media renaming using intelligent parsing (guessit, mutagen) and online metadata enrichment (TMDb, TVMaze, and TheAudioDB) while synchronizing subtitles and folder hierarchies.

---

## What's New in v1.1.0

- **Multi-Source Metadata Enrichment:**
  - **TMDb (The Movie Database):** Full movie and TV show lookup with persistent session, negative caching, and automatic circuit breaker.
  - **TVMaze Integration:** Free, public TV metadata lookup out-of-the-box (no API key required).
  - **TheAudioDB Integration:** Audio track enrichment and metadata identification.
- **Batch Confirmation Dialog:**
  - Modal breakdown dialog before renaming items (e.g. *Rename 425 items: 3 folders, 210 videos, 212 subs*).
- **Digit Diff Highlighting:**
  - Contrasting orange (`#FFA500` / `#FFB74D`) highlighting for changing numbers so filename differences stand out at a glance.
- **Season Folder Collision Protection:**
  - If a single-episode subfolder has an episode tag (e.g. `Humans - S01E01`) and `Season 1` already exists in that show directory, Alias skips the rename and flags it as `Skipped (Season exists)` to prevent unwanted `Season 1_1` duplicates.
- **Background Drive Detection & Thread-Safe UI:**
  - Drive polling runs asynchronously in a worker thread so UI never freezes on disconnected or slow network drives (`M:`, `P:`).
  - UI communications routed through a thread-safe message queue.
- **Credential Security (Windows DPAPI):**
  - TMDb API keys are encrypted at rest using Windows DPAPI (`CryptProtectData`), eliminating plain-text secrets in configuration files.
- **Modular Architecture & Test Suite:**
  - Modularized into `naming.py`, `winfs.py`, `metadata.py`, and `ui_components.py`.
  - Comprehensive unit test suite run with `pytest`.
- **Reusable Singleton Tooltips & Clean Dropdown:**
  - Singleton tooltip engine prevents memory leaks and stuck tooltips.
  - Folder tree dropdown toggles exclusively via the `▼` button and cleanly unbinds click handlers on dismissal.

---

## Key Features

- **Automated Metadata & Edition Tag Parsing:**
  - Extracts ID3 and Vorbis tags for audio files (`Artist - Track - Title.ext`).
  - Resolves TV show names, season/episode numbers (`S01E02`), episode titles, and movie release years using `guessit`, `TMDb`, and `TVMaze`.
  - Supports resolution tags (`4K`, `2K`), 3D formats (`3D H-SBS`, `3D SBS`, `3D H-OU`, `3D OU`, `3D MVC`, `3D`), and edition cuts (`Extended Cut`, `Directors Cut`, `Final Cut`, `Theatrical Cut`, `Unrated`, `Special Edition`, `Remastered`).
  - Handles single- and multi-episode files (e.g. `S01E01-E02`).
- **Interactive Directory Tree Dropdown:**
  - Click the `▼` button on the Folder Path bar to open an interactive directory tree browser.
  - Browse mapped network drives (`M:`, `P:`), local drives, and folders with lazy-loading child expansion.
- **Table Navigation & Multi-Column Sorting:**
  - Clear 4-column layout: **Current Name**, **Type (File/Folder)**, **Proposed New Name**, and **Status**.
  - One-click sorting across columns:
    - **Current Name:** Sort A-Z (▲) or Z-A (▼).
    - **Type:** Sort Folders first (▲) or Files first (▼).
    - **Status:** Sort Pending renames first (▲) or Unchanged/Skipped first (▼).
- **Theme & Appearance Customization:**
  - Clean theme selector: switch between **System**, **Dark**, and **Light** modes with persistent config.
- **Folder & Subtitle Synchronization:**
  - Automatically identifies `.srt` subtitle files in the video folder or inside `Subs` / `Subtitles` subfolders.
  - Automatically renames the parent movie/show folder to match the new media title while preserving existing season folders (`Season 1`, `Season 01`).
- **Dual Edit Modes:**
  - **`Media Only (Auto-sync Subs & Folders)` (Default):** Edit only the audio or video filename. All corresponding `.srt` files and the parent folder cascade and auto-update their proposed names live.
  - **`Edit All Names Individually`:** Direct text editing across every individual file, subtitle, and folder row.
- **Safety First:**
  - **Confirmation Dialog:** Shows an exact item breakdown before any rename executes.
  - **Non-destructive Undo:** Revert the most recent batch of renames with one click.
  - **Collision Prevention:** Protects against overwriting existing files with numbered collision suffixes (`_1`, `_2`).
  - **Character Sanitization:** Automatically cleans Windows-disallowed NTFS/FAT32 characters (`:`, `*`, `?`, etc.) and formats titles neatly.

---

## Quick Start (Development)

1. **Activate the virtual environment:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
2. **Run Alias:**
   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```
3. **Run Unit Tests:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/
   ```

---

## Building from Source

To build the standalone Windows executable and setup installer:

```powershell
.\build.ps1
```

*Prerequisites: Python 3.10+, PyInstaller 6+, and Inno Setup 6 (for `.exe` setup installer generation).*

---

## License & Attribution

Created by **Marc Bailey** 2026.
GitHub: [https://github.com/DaidalusX78/Alias](https://github.com/DaidalusX78/Alias)
