# Alias — Smart Media Renamer

[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue.svg)](https://microsoft.com/windows)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![UI: CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-orange.svg)](https://github.com/TomSchimansky/CustomTkinter)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version: 1.1.05](https://img.shields.io/badge/Version-1.1.05-papaya.svg)](installer.iss)

**Alias** is a desktop media library organizer and batch renamer designed for Windows 10 and 11. It combines local heuristics (`guessit`, ID3 tag parsing) with online metadata providers (**The Movie Database (TMDb)**, **TVMaze**, and **TheAudioDB**) to cleanly standardize movies, television series, multi-episode files, music albums, and accompanying subtitle files.

---

## Key Features

- **Multi-Source Intelligent Metadata Matching:**
  - **Movies:** Automatically queries TMDb with release-year tolerance checks ($\pm 2$ years) to prevent mismatched sequels, reboots, or remakes.
  - **TV Shows:** Matches episodes with TVMaze (free, no key required) and TMDb, supporting standard `S01E01` notation, multi-episode files (`S01E01-E03`), and season-folder structures.
  - **Music & Audio Tracks:** Extracts ID3 and Vorbis tags via `mutagen`, enriched with TheAudioDB. Follows Plex/Kodi/iTunes standard track numbering (`01 - Title.ext` inside album folders, or `Artist - 01 - Title.ext` in flat folders).
  - **Subtitles (`.srt`):** Automatically discovers and syncs subtitle files (including `Subs/` subdirectories), renaming them in tandem with the primary video while preserving language descriptors (e.g. `.en.srt`, `.es.srt`).

- **Duplicate Detection & Management:**
  - Detects duplicate files, multiple formats, and collision copies (e.g. `Movie (2014)` and `Movie (2014)_1`, or 1080p and 3D versions).
  - Highlights duplicates with distinct warning badges (`⚠️ Duplicate (N)`).
  - **Status (Duplicates ▲):** One-click grouping brings duplicate items side-by-side to the top of the table.
  - **Deselect Duplicates (Keep 1st):** Instant batch action unchecks secondary copies across the entire library to prevent renaming collisions.
  - **Filter by Duplicates:** Quickly isolate and review only conflicting items with the *Duplicates only* toggle.

- **Multilingual Support (English & Spanish):**
  - Full title-casing and metadata localization for Spanish (`es-ES`, `es-MX`) and English (`en-US`).
  - Preserves legitimate original foreign titles, accurately capitalizes lowercase prepositions/articles, and recognizes localized directory terms (e.g., `Temporada 1` vs `Season 1`).
  - Automatically filters pirate prefixes (e.g., *Ver*, *Descargar*, *Pelicula*).

- **Special Edition & Format Tag Preservation:**
  - Preserves resolution and edition tags: `[Extended Cut]`, `[Directors Cut]`, `[Theatrical Cut]`, `[Final Cut]`, `[Unrated]`, `[Remastered]`, `[4K]`, `[3D H-SBS]`, `[3D H-OU]`.
  - Contrasting visual pill badges highlight changing numeric values (e.g., year or episode corrections) directly in the table.

- **Put Loose Files into Folders:**
  - Automatically identifies media dumped into root or unsorted directories and moves each file (and its subtitles) into a newly created, standardized movie folder.
  - Fully integrated with the preview table, confirmation dialog, and one-click Undo.

- **Secure & Robust Architecture:**
  - **Windows DPAPI Encryption:** Stores TMDb API keys safely encrypted under user-specific Windows credentials—never in plain text.
  - **Asynchronous Drive Discovery:** Probes physical, mapped, and offline network drives in background threads to eliminate UI freezing.
  - **Non-Destructive Simulation:** Preview proposed names in real time, review a categorical breakdown dialog, and rollback changes using the **Undo Last Rename** history stack.

---

## Installation & Setup

### Option 1: Standalone Windows Installer (Recommended)
Compile the Inno Setup script to create a standalone installer:
```powershell
iscc.exe installer.iss
```
The generated installer (`installer_output/Alias_Setup_v1.1.05.exe`) packages `Alias.exe`, necessary dependencies, desktop shortcuts, and Windows uninstallation hooks.

### Option 2: Run from Source

#### Prerequisites
- **Python 3.10+** (64-bit recommended)
- **Windows 10 / 11**

#### Quickstart
1. Clone the repository:
   ```powershell
   git clone https://github.com/DaidalusX78/Alias.git
   cd Alias
   ```

2. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:
   ```powershell
   pip install -r requirements-dev.txt
   ```

4. Launch the application:
   ```powershell
   python app.py
   ```

---

## Configuration

1. **TMDb API Key (Optional but recommended):**
   - Obtain a free API key at [themoviedb.org](https://www.themoviedb.org/).
   - Enter your API Key in the top toolbar and click **Save Key**. The key is encrypted locally using the Windows Data Protection API (DPAPI).
   - If no key is entered, Alias operates in free mode using TVMaze and local `guessit` parsing.
2. **Metadata Language:**
   - Choose your preferred language from the dropdown menu (e.g. *English (en-US)* or *Español (es-ES)*).
3. **Appearance Mode:**
   - Select *Dark*, *Light*, or *System* theme. Settings persist across application launches.

---

## Development & Testing

### Running Tests
Unit tests cover title sanitization, tag extraction, franchise sequel parsing, duplicate normalization, and audio track resolution:
```powershell
.\.venv\Scripts\pytest.exe
```

### Code Formatting & Linting
Run Ruff linter:
```powershell
.\.venv\Scripts\ruff.exe check .
```

---

## Technology Stack

| Layer | Technologies |
|---|---|
| **GUI Framework** | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), Tkinter, Win32 DWM |
| **Parsing & Media** | [guessit](https://github.com/guessit-io/guessit), [mutagen](https://github.com/quodlibet/mutagen) |
| **Online APIs** | [The Movie Database (TMDb)](https://www.themoviedb.org/), [TVMaze](https://www.tvmaze.com/), [TheAudioDB](https://www.theaudiodb.com/) |
| **Security & Win32** | Windows Data Protection API (DPAPI / `CryptProtectData`), Win32 Shell API |
| **Packaging** | [PyInstaller](https://pyinstaller.org/), [Inno Setup 6](https://jrsoftware.org/isinfo.php) |

---

## License

Distributed under the MIT License. See `LICENSE` for more information.

**Author:** Marc Bailey (2026)  
**Repository:** [https://github.com/DaidalusX78/Alias](https://github.com/DaidalusX78/Alias)

