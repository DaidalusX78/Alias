"""
Alias — Smart Media Renamer (v1.1.0)
Created by Marc Bailey 2026

Pairs television episodes, multi-episode files, movies, audio tracks, and subtitle files
with intelligent metadata from TMDb, TVMaze, TheAudioDB, and ID3 tags.
"""

from __future__ import annotations

import gc
import json
import os
import queue
import re
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from metadata import (
    CONFIG_PATH,
    TheAudioDBClient,
    TMDbClient,
    TVMazeClient,
    decrypt_secret,
    encrypt_secret,
)
from naming import (
    AUDIO_EXTS,
    SUB_DIR_NAMES,
    VIDEO_EXTS,
    clear_guessit_cache,
    collect_subtitle_files,
    find_changing_digit_ranges,
    is_collision,
    pick_primary_video,
    resolve_audio_name,
    resolve_folder_name,
    resolve_subtitle_name,
    resolve_video_name,
    safe_guessit,
    sanitize_filename,
)
from ui_components import (
    CTkToolTip,
    FolderTreeDropdown,
    RenameConfirmDialog,
    ScanProgressDialog,
)
from winfs import (
    get_detected_drives,
    pick_folder_native,
    restore_network_drive,
    safe_file_or_dir_rename,
)

__version__ = "1.1.0"
__author__ = "Marc Bailey"

PAGE_SIZE = 100

# Application Styling Setup (load persisted theme if available)
_init_appearance = "System"
if CONFIG_PATH.exists():
    try:
        _cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        _init_appearance = _cfg.get("appearance_mode", "System")
    except Exception:
        pass

ctk.set_appearance_mode(_init_appearance)
ctk.set_default_color_theme("blue")


def get_resource_path(relative_path: str) -> Path:
    """Resolve resource path for dev execution and PyInstaller builds."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base_path = Path(meipass)
    else:
        base_path = Path(__file__).resolve().parent
    candidate = base_path / relative_path
    if candidate.exists():
        return candidate
    return Path(sys.executable).resolve().parent / relative_path


class MediaRenamerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"Alias v{__version__} — Smart media renamer | Created by {__author__} 2026")
        self.geometry("1180x760")
        self.minsize(980, 600)

        icon_path = get_resource_path("alias.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        self.selected_folder: Path | None = None
        self.file_items: list[dict] = []
        self.filtered_items: list[dict] = []
        self.current_page: int = 0
        self.sort_mode: str | None = None
        self.last_rename_batch: list[tuple[Path, Path]] = []

        # Metadata Clients
        self.tmdb_client = TMDbClient()
        self.tvmaze_client = TVMazeClient()
        self.audiodb_client = TheAudioDBClient()

        # Scanning and UI State
        self._cancel_scan = False
        self._scan_dialog: ScanProgressDialog | None = None
        self.drive_map: dict[str, str] = {}
        self.folder_tree: FolderTreeDropdown | None = None
        self.msg_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._load_saved_config()

        # Start periodic queue polling for thread-safe UI updates
        self._poll_queue()

        # Asynchronously detect drives so UI never freezes on network timeout
        self._async_refresh_drives()

        # Handle folder argument passed via command line (e.g. Explorer context menu)
        initial_folder = None
        if len(sys.argv) > 1:
            arg_path = Path(sys.argv[1])
            if arg_path.exists():
                initial_folder = arg_path if arg_path.is_dir() else arg_path.parent

        if initial_folder:
            self.set_selected_folder(initial_folder)

    def _poll_queue(self):
        """Thread-safe worker communication pump."""
        try:
            while True:
                msg_type, payload = self.msg_queue.get_nowait()
                if msg_type == "progress":
                    curr, total, name = payload
                    if self._scan_dialog:
                        self._scan_dialog.update_progress(curr, total, name)
                elif msg_type == "scan_finished":
                    self._on_scan_finished(payload)
                elif msg_type == "drives_detected":
                    self._apply_detected_drives(payload)
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    def _async_refresh_drives(self):
        """Run drive detection on a background thread so UI never freezes on disconnected M: or P: drives."""
        def _worker():
            try:
                detected = get_detected_drives()
            except Exception:
                detected = []
            self.msg_queue.put(("drives_detected", detected))

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_detected_drives(self, detected: list[tuple[str, str]]):
        self.drive_map = {label: root for root, label in detected}
        drive_labels = list(self.drive_map.keys()) if self.drive_map else ["No drives found"]
        self.opt_drives.configure(values=drive_labels)
        current_val = self.opt_drives.get()
        if current_val not in drive_labels:
            self.opt_drives.set("Select Drive..." if len(drive_labels) > 1 else drive_labels[0])

    def _load_saved_config(self):
        """Load saved TMDb API key (decrypting with Windows DPAPI) and theme preferences."""
        api_key = os.environ.get("TMDB_API_KEY", "")
        appearance = "System"
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                stored_key = data.get("tmdb_api_key", "")
                if stored_key.startswith("dpapi:"):
                    api_key = decrypt_secret(stored_key)
                elif stored_key:
                    api_key = stored_key
                appearance = data.get("appearance_mode", "System")
            except Exception:
                pass
        if api_key:
            self.entry_api.insert(0, api_key)
            self.tmdb_client = TMDbClient(api_key)
        self.opt_appearance.set(appearance)

    def _save_config(self):
        """Persist TMDb API key (encrypted with Windows DPAPI) and theme preferences."""
        try:
            raw_key = self.entry_api.get().strip()
            encrypted_key = encrypt_secret(raw_key) if raw_key else ""
            cfg = {
                "tmdb_api_key": encrypted_key,
                "appearance_mode": self.opt_appearance.get()
            }
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _on_appearance_changed(self, choice: str):
        ctk.set_appearance_mode(choice)
        self._save_config()

    def _build_ui(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ----------------- Row 0: Configuration / API Key & Theme -----------------
        self.config_frame = ctk.CTkFrame(self, corner_radius=10)
        self.config_frame.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="ew")
        self.config_frame.grid_columnconfigure(1, weight=1)

        lbl_api = ctk.CTkLabel(self.config_frame, text="TMDb API Key:", font=ctk.CTkFont(weight="bold"))
        lbl_api.grid(row=0, column=0, padx=12, pady=10, sticky="w")

        self.entry_api = ctk.CTkEntry(
            self.config_frame,
            placeholder_text="Enter API key for online TV/Movie metadata (optional)...",
            show="*"
        )
        self.entry_api.grid(row=0, column=1, padx=(10, 5), pady=10, sticky="ew")

        self.btn_toggle_key = ctk.CTkButton(
            self.config_frame,
            text="Show",
            width=65,
            fg_color="gray30",
            hover_color="gray40",
            command=self._toggle_api_visibility
        )
        self.btn_toggle_key.grid(row=0, column=2, padx=(5, 10), pady=10)

        # Provider Indicators badge (TVMaze & TheAudioDB ready)
        self.lbl_providers = ctk.CTkLabel(
            self.config_frame,
            text="TVMaze: Active  |  TheAudioDB: Active",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#2EA043", "#3FB950")
        )
        self.lbl_providers.grid(row=0, column=3, padx=(4, 12), pady=10)
        CTkToolTip(self.lbl_providers, "Metadata Providers:\n• TMDb: Active when API key is provided\n• TVMaze: Free public TV metadata (No key required)\n• TheAudioDB: Music metadata & track lookup")

        # Theme Selector (System, Dark, Light)
        lbl_theme = ctk.CTkLabel(self.config_frame, text="Theme:", font=ctk.CTkFont(weight="bold"))
        lbl_theme.grid(row=0, column=4, padx=(8, 4), pady=10)

        self.opt_appearance = ctk.CTkOptionMenu(
            self.config_frame,
            values=["System", "Dark", "Light"],
            command=self._on_appearance_changed,
            width=110
        )
        self.opt_appearance.set("System")
        self.opt_appearance.grid(row=0, column=5, padx=(0, 15), pady=10)
        CTkToolTip(self.opt_appearance, "Theme Mode: Switch between System theme, Dark mode, or Light mode")

        # ----------------- Row 1: Folder Selector & Controls -----------------
        self.top_frame = ctk.CTkFrame(self, corner_radius=10)
        self.top_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        self.top_frame.grid_columnconfigure(0, weight=1)

        # Sub-row 0: Quick drive selector, edit mode, and filters
        self.controls_subframe = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.controls_subframe.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        self.controls_subframe.grid_columnconfigure(5, weight=1)

        self.btn_select = ctk.CTkButton(
            self.controls_subframe,
            text="Browse Folder...",
            width=130,
            font=ctk.CTkFont(weight="bold"),
            command=self.choose_directory
        )
        self.btn_select.grid(row=0, column=0, padx=(2, 8), pady=4)

        lbl_drive = ctk.CTkLabel(self.controls_subframe, text="Quick Drive:", font=ctk.CTkFont(weight="bold"))
        lbl_drive.grid(row=0, column=1, padx=(6, 4), pady=4)

        self.opt_drives = ctk.CTkOptionMenu(
            self.controls_subframe,
            values=["Scanning drives..."],
            command=self._on_quick_drive_selected,
            width=230
        )
        self.opt_drives.set("Scanning drives...")
        self.opt_drives.grid(row=0, column=2, padx=(0, 14), pady=4)

        lbl_mode = ctk.CTkLabel(self.controls_subframe, text="Edit Mode:", font=ctk.CTkFont(weight="bold"))
        lbl_mode.grid(row=0, column=3, padx=(6, 4), pady=4)

        self.opt_mode = ctk.CTkOptionMenu(
            self.controls_subframe,
            values=["Media Only (Auto-sync Subs & Folders)", "Edit All Names Individually"],
            command=self._on_edit_mode_changed,
            width=260
        )
        self.opt_mode.set("Media Only (Auto-sync Subs & Folders)")
        self.opt_mode.grid(row=0, column=4, padx=(0, 12), pady=4)

        self.var_hide_unchanged = ctk.BooleanVar(value=False)
        self.chk_hide_unchanged = ctk.CTkCheckBox(
            self.controls_subframe,
            text="Hide unchanged folders and files",
            variable=self.var_hide_unchanged,
            command=self._on_filter_changed,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.chk_hide_unchanged.grid(row=0, column=5, padx=8, pady=4, sticky="e")

        # Sub-row 1: Direct editable path bar with folder tree dropdown toggle
        self.path_subframe = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.path_subframe.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 8))
        self.path_subframe.grid_columnconfigure(1, weight=1)

        lbl_path_title = ctk.CTkLabel(self.path_subframe, text="Folder Path:", font=ctk.CTkFont(weight="bold"))
        lbl_path_title.grid(row=0, column=0, padx=(2, 8), pady=2)

        self.entry_path = ctk.CTkEntry(
            self.path_subframe,
            placeholder_text="Enter path or click ▼ to browse tree (e.g. M:\\Shared Videos)..."
        )
        self.entry_path.grid(row=0, column=1, padx=(0, 4), pady=2, sticky="ew")
        self.entry_path.bind("<Return>", lambda e: self.load_entered_path())

        self.folder_tree = FolderTreeDropdown(self, self.entry_path, self._on_tree_folder_selected)

        self.btn_tree_toggle = ctk.CTkButton(
            self.path_subframe,
            text="▼",
            width=28,
            fg_color="gray30",
            hover_color="gray40",
            command=self.folder_tree.toggle
        )
        self.btn_tree_toggle.grid(row=0, column=2, padx=(0, 8), pady=2)
        CTkToolTip(self.btn_tree_toggle, "Folder Tree: Click to open/close folder tree browser")

        self.btn_load_path = ctk.CTkButton(
            self.path_subframe,
            text="Scan / Load",
            width=100,
            font=ctk.CTkFont(weight="bold"),
            command=self.load_entered_path
        )
        self.btn_load_path.grid(row=0, column=3, padx=(0, 4), pady=2)

        self.btn_rescan = ctk.CTkButton(
            self.path_subframe,
            text="Rescan",
            width=80,
            state="disabled",
            fg_color="gray30",
            hover_color="gray40",
            command=self.rescan_current_folder
        )
        self.btn_rescan.grid(row=0, column=4, padx=(4, 2), pady=2)

        # ----------------- Row 2: Table -----------------
        self.table_frame = ctk.CTkFrame(self, corner_radius=10)
        self.table_frame.grid(row=2, column=0, padx=20, pady=5, sticky="nsew")
        self.table_frame.grid_rowconfigure(1, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)

        self.header_frame = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        self.header_frame.grid_columnconfigure(0, weight=0, minsize=36)
        self.header_frame.grid_columnconfigure(1, weight=0, minsize=380)
        self.header_frame.grid_columnconfigure(2, weight=0, minsize=110)
        self.header_frame.grid_columnconfigure(3, weight=1)
        self.header_frame.grid_columnconfigure(4, weight=0, minsize=90)

        self.var_select_all = ctk.BooleanVar(value=True)
        self.chk_select_all = ctk.CTkCheckBox(
            self.header_frame,
            text="",
            width=24,
            variable=self.var_select_all,
            command=self._toggle_all_checkboxes
        )
        self.chk_select_all.grid(row=0, column=0, padx=(5, 8), sticky="w")

        self.btn_header_name = ctk.CTkButton(
            self.header_frame,
            text="Current Name ↕",
            height=24,
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=("gray80", "gray25"),
            font=ctk.CTkFont(weight="bold"),
            command=self._toggle_sort_by_name
        )
        self.btn_header_name.grid(row=0, column=1, sticky="w", padx=5)
        CTkToolTip(self.btn_header_name, "Click to sort by Current Name: A-Z, Z-A, or default order")

        self.btn_header_type = ctk.CTkButton(
            self.header_frame,
            text="Type ↕",
            width=95,
            height=24,
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=("gray80", "gray25"),
            font=ctk.CTkFont(weight="bold"),
            command=self._toggle_sort_by_type
        )
        self.btn_header_type.grid(row=0, column=2, sticky="w", padx=5)
        CTkToolTip(self.btn_header_type, "Click to sort by Type: Folders first, Files first, or default order")

        self.lbl_header_proposed = ctk.CTkLabel(
            self.header_frame,
            text="Proposed New Name",
            anchor="w",
            font=ctk.CTkFont(weight="bold")
        )
        self.lbl_header_proposed.grid(row=0, column=3, sticky="w", padx=5)

        self.btn_header_status = ctk.CTkButton(
            self.header_frame,
            text="Status ↕",
            width=80,
            height=24,
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=("gray80", "gray25"),
            font=ctk.CTkFont(weight="bold"),
            command=self._toggle_sort_by_status
        )
        self.btn_header_status.grid(row=0, column=4, sticky="e", padx=(5, 38))
        CTkToolTip(self.btn_header_status, "Click to sort by Status: Pending first, Unchanged first, or default order")

        self.scroll_list = ctk.CTkScrollableFrame(self.table_frame, fg_color="transparent")
        self.scroll_list.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))
        self.scroll_list.grid_columnconfigure(0, weight=0, minsize=36)
        self.scroll_list.grid_columnconfigure(1, weight=0, minsize=380)
        self.scroll_list.grid_columnconfigure(2, weight=0, minsize=110)
        self.scroll_list.grid_columnconfigure(3, weight=1)
        self.scroll_list.grid_columnconfigure(4, weight=0, minsize=90)

        # Pagination bar inside table_frame (row 2)
        self.page_frame = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        self.page_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 6))
        self.page_frame.grid_columnconfigure(1, weight=1)

        self.btn_prev_page = ctk.CTkButton(
            self.page_frame,
            text="◀ Previous Page",
            width=120,
            height=26,
            state="disabled",
            fg_color="gray30",
            hover_color="gray40",
            command=self._prev_page
        )
        self.btn_prev_page.grid(row=0, column=0, padx=4, sticky="w")

        self.lbl_page_info = ctk.CTkLabel(self.page_frame, text="", font=ctk.CTkFont(size=12), text_color="gray")
        self.lbl_page_info.grid(row=0, column=1, padx=10)

        self.btn_next_page = ctk.CTkButton(
            self.page_frame,
            text="Next Page ▶",
            width=120,
            height=26,
            state="disabled",
            fg_color="gray30",
            hover_color="gray40",
            command=self._next_page
        )
        self.btn_next_page.grid(row=0, column=2, padx=4, sticky="e")

        # ----------------- Row 3: Bottom Action Bar -----------------
        self.bottom_frame = ctk.CTkFrame(self, corner_radius=10)
        self.bottom_frame.grid(row=3, column=0, padx=20, pady=(5, 15), sticky="ew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)
        self.bottom_frame.grid_columnconfigure(1, weight=1)

        self.lbl_status = ctk.CTkLabel(self.bottom_frame, text="Idle", anchor="w")
        self.lbl_status.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        self.lbl_credit = ctk.CTkLabel(
            self.bottom_frame,
            text=f"Created by {__author__} 2026 | v{__version__}",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="gray55"
        )
        self.lbl_credit.grid(row=0, column=1, padx=10, pady=10)

        self.btn_undo = ctk.CTkButton(
            self.bottom_frame,
            text="Undo Last Rename",
            fg_color="#6E7681",
            hover_color="#57606A",
            state="disabled",
            command=self.undo_last_rename
        )
        self.btn_undo.grid(row=0, column=2, padx=(10, 5), pady=10, sticky="e")

        self.btn_apply = ctk.CTkButton(
            self.bottom_frame,
            text="Apply Renaming",
            fg_color="#2EA043",
            hover_color="#238636",
            state="disabled",
            font=ctk.CTkFont(weight="bold"),
            command=self.apply_renames
        )
        self.btn_apply.grid(row=0, column=3, padx=(5, 15), pady=10, sticky="e")

    def _toggle_api_visibility(self):
        if self.entry_api.cget("show") == "*":
            self.entry_api.configure(show="")
            self.btn_toggle_key.configure(text="Hide")
        else:
            self.entry_api.configure(show="*")
            self.btn_toggle_key.configure(text="Show")

    def set_selected_folder(self, folder_path: Path):
        self.selected_folder = folder_path
        self.entry_path.delete(0, "end")
        self.entry_path.insert(0, str(folder_path))
        self.rescan_current_folder()

    def load_entered_path(self):
        raw_text = self.entry_path.get().strip().strip('"').strip("'")
        if not raw_text:
            messagebox.showwarning("Path Required", "Please enter or paste a valid folder path.")
            return

        # Attempt to restore offline drive letters if needed
        if len(raw_text) >= 2 and raw_text[1] == ":":
            try:
                import winreg
                letter = raw_text[0].upper()
                net_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Network")
                subkey = winreg.OpenKey(net_key, letter)
                remote_path = winreg.QueryValueEx(subkey, "RemotePath")[0]
                restore_network_drive(letter, remote_path)
            except Exception:
                pass

        candidate = Path(raw_text)
        if not candidate.exists():
            messagebox.showerror(
                "Path Not Found",
                f"Cannot access path:\n{raw_text}\n\nPlease check that the drive or network share is connected and accessible."
            )
            return
        if not candidate.is_dir():
            messagebox.showerror("Not a Directory", f"The specified path is a file, not a directory:\n{raw_text}")
            return

        self._async_refresh_drives()
        self.set_selected_folder(candidate)

    def _on_quick_drive_selected(self, choice: str):
        if choice in self.drive_map:
            root_path = self.drive_map[choice]
            target = Path(root_path)
            if not target.exists():
                m = re.search(r"\[Network:\s*([^\]]+)\]", choice)
                if m and len(root_path) >= 2 and root_path[1] == ":":
                    restore_network_drive(root_path[0].upper(), m.group(1).strip())
            if not target.exists():
                messagebox.showerror(
                    "Drive Inaccessible",
                    f"Could not access {choice}.\n\nPlease ensure the network share or drive is connected."
                )
                return
            self.set_selected_folder(target)

    def choose_directory(self):
        initial = None
        if self.selected_folder and self.selected_folder.exists():
            initial = str(self.selected_folder)

        parent_hwnd = None
        try:
            import ctypes
            raw_id = self.winfo_id()
            parent_hwnd = ctypes.windll.user32.GetAncestor(raw_id, 2)
        except Exception:
            pass

        chosen = pick_folder_native(parent_hwnd=parent_hwnd, title="Select Media Folder", initial_path=initial)
        if chosen == "":
            return  # User cancelled
        if chosen is None:
            chosen = filedialog.askdirectory(parent=self, title="Select Media Folder", initialdir=initial)
            if not chosen:
                return

        self._async_refresh_drives()
        self.set_selected_folder(Path(chosen))

    def _cancel_active_scan(self):
        self._cancel_scan = True

    def rescan_current_folder(self):
        self._async_refresh_drives()
        if not self.selected_folder or not self.selected_folder.exists():
            return

        self._save_config()
        self.tmdb_client = TMDbClient(self.entry_api.get())
        self._cancel_scan = False

        self.lbl_status.configure(text="Scanning folder & querying metadata...")
        self.btn_select.configure(state="disabled")
        self.btn_load_path.configure(state="disabled")
        self.btn_rescan.configure(state="disabled")
        self.btn_apply.configure(state="disabled")

        if self._scan_dialog is not None:
            self._scan_dialog.close_dialog()
        self._scan_dialog = ScanProgressDialog(self, self.selected_folder, self._cancel_active_scan)

        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        clear_guessit_cache()
        resolved_data = []
        try:
            if not self.selected_folder:
                return

            folder = self.selected_folder
            valid_extensions = AUDIO_EXTS | VIDEO_EXTS
            all_media = sorted(
                [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in valid_extensions],
                key=lambda p: str(p).lower()
            )

            total_media = len(all_media)
            processed_media = 0

            by_folder: dict[Path, list[Path]] = {}
            for path in all_media:
                by_folder.setdefault(path.parent, []).append(path)

            for folder_path, media_paths in by_folder.items():
                if self._cancel_scan:
                    break

                video_files_in_folder: list[tuple[Path, str, str]] = []
                audio_files_in_folder: list[tuple[Path, str, str]] = []

                for path in media_paths:
                    if self._cancel_scan:
                        break

                    processed_media += 1
                    if processed_media == 1 or processed_media % 5 == 0 or processed_media == total_media:
                        self.msg_queue.put(("progress", (processed_media, total_media, path.name)))

                    ext = path.suffix.lower()
                    orig_name = path.name

                    try:
                        if ext in AUDIO_EXTS:
                            new_name = resolve_audio_name(path, self.audiodb_client)
                            item_kind = "Audio"
                        else:
                            new_name = resolve_video_name(path, self.tmdb_client, self.tvmaze_client)
                            item_kind = "Video"
                    except Exception:
                        new_name = orig_name
                        item_kind = "Audio" if ext in AUDIO_EXTS else "Video"

                    will_rename = (new_name != orig_name)
                    media_item_id = f"item_{len(resolved_data)}"
                    resolved_data.append({
                        "id": media_item_id,
                        "kind": item_kind,
                        "is_dir": False,
                        "folder_group": folder_path,
                        "path": path,
                        "display_orig": orig_name,
                        "orig_name": orig_name,
                        "new_name": new_name,
                        "will_rename": will_rename,
                        "is_selected": will_rename,
                    })

                    if ext in VIDEO_EXTS:
                        video_files_in_folder.append((path, Path(new_name).stem, media_item_id))
                    else:
                        audio_files_in_folder.append((path, Path(new_name).stem, media_item_id))

                if self._cancel_scan:
                    break

                # Subtitles and folder naming for single-video folder
                if len(video_files_in_folder) == 1:
                    video_path, new_video_stem, v_id = video_files_in_folder[0]
                    old_video_stem = video_path.stem

                    srt_files = collect_subtitle_files(folder_path)
                    dir_counts: dict[Path, int] = {}
                    for srt in srt_files:
                        dir_counts[srt.parent] = dir_counts.get(srt.parent, 0) + 1

                    for srt in srt_files:
                        new_srt_name = resolve_subtitle_name(
                            srt, old_video_stem, new_video_stem, dir_counts[srt.parent]
                        )
                        will_rename_srt = (new_srt_name != srt.name)
                        rel_parent = f"{srt.parent.name}\\" if srt.parent != folder_path else ""
                        resolved_data.append({
                            "id": f"item_{len(resolved_data)}",
                            "kind": "Sub",
                            "is_dir": False,
                            "folder_group": folder_path,
                            "parent_media_id": v_id,
                            "old_video_stem": old_video_stem,
                            "dir_count": dir_counts[srt.parent],
                            "path": srt,
                            "display_orig": f"{rel_parent}{srt.name}",
                            "orig_name": srt.name,
                            "new_name": new_srt_name,
                            "will_rename": will_rename_srt,
                            "is_selected": will_rename_srt,
                        })

                    new_folder_name, collision_skipped = resolve_folder_name(
                        folder_path, video_files_in_folder, self.tmdb_client, self.tvmaze_client
                    )
                    if new_folder_name and folder_path.parent != folder_path:
                        will_rename_dir = (new_folder_name != folder_path.name) and (not collision_skipped)
                        folder_item = {
                            "id": f"item_{len(resolved_data)}",
                            "kind": "Folder",
                            "is_dir": True,
                            "folder_group": folder_path,
                            "parent_media_id": v_id,
                            "is_multi_ep": False,
                            "path": folder_path,
                            "display_orig": folder_path.name,
                            "orig_name": folder_path.name,
                            "new_name": new_folder_name,
                            "will_rename": will_rename_dir,
                            "is_selected": will_rename_dir,
                        }
                        if collision_skipped:
                            folder_item["status_override"] = "Skipped (Season exists)"
                        resolved_data.append(folder_item)

                elif len(video_files_in_folder) > 1:
                    primary_path, primary_new_stem, primary_id = pick_primary_video(video_files_in_folder)

                    srt_files = collect_subtitle_files(folder_path)
                    dir_counts_multi: dict[Path, int] = {}
                    for srt in srt_files:
                        dir_counts_multi[srt.parent] = dir_counts_multi.get(srt.parent, 0) + 1

                    for srt in srt_files:
                        srt_guess = safe_guessit(srt.name)
                        matched_video = None
                        for v_path, v_new_stem, v_id in video_files_in_folder:
                            if srt.stem.lower().startswith(v_path.stem.lower()):
                                matched_video = (v_path, v_new_stem, v_id)
                                break
                            v_guess = safe_guessit(v_path.name)
                            if (
                                "season" in srt_guess and "episode" in srt_guess
                                and srt_guess.get("season") == v_guess.get("season")
                                and srt_guess.get("episode") == v_guess.get("episode")
                            ):
                                matched_video = (v_path, v_new_stem, v_id)
                                break

                        if not matched_video:
                            matched_video = (primary_path, primary_new_stem, primary_id)

                        v_path, v_new_stem, v_id = matched_video
                        new_srt_name = resolve_subtitle_name(
                            srt, v_path.stem, v_new_stem, dir_counts_multi[srt.parent]
                        )
                        will_rename_srt = (new_srt_name != srt.name)
                        rel_parent = f"{srt.parent.name}\\" if srt.parent != folder_path else ""
                        resolved_data.append({
                            "id": f"item_{len(resolved_data)}",
                            "kind": "Sub",
                            "is_dir": False,
                            "folder_group": folder_path,
                            "parent_media_id": v_id,
                            "old_video_stem": v_path.stem,
                            "dir_count": dir_counts_multi[srt.parent],
                            "path": srt,
                            "display_orig": f"{rel_parent}{srt.name}",
                            "orig_name": srt.name,
                            "new_name": new_srt_name,
                            "will_rename": will_rename_srt,
                            "is_selected": will_rename_srt,
                        })

                    new_folder_name, collision_skipped = resolve_folder_name(
                        folder_path, video_files_in_folder, self.tmdb_client, self.tvmaze_client
                    )
                    if new_folder_name and folder_path.parent != folder_path:
                        will_rename_dir = (new_folder_name != folder_path.name) and (not collision_skipped)
                        folder_item = {
                            "id": f"item_{len(resolved_data)}",
                            "kind": "Folder",
                            "is_dir": True,
                            "folder_group": folder_path,
                            "parent_media_id": primary_id,
                            "is_multi_ep": True,
                            "path": folder_path,
                            "display_orig": folder_path.name,
                            "orig_name": folder_path.name,
                            "new_name": new_folder_name,
                            "will_rename": will_rename_dir,
                            "is_selected": will_rename_dir,
                        }
                        if collision_skipped:
                            folder_item["status_override"] = "Skipped (Season exists)"
                        resolved_data.append(folder_item)
        finally:
            gc.collect()
            self.msg_queue.put(("scan_finished", resolved_data))

    def _on_scan_finished(self, resolved_data: list[dict]):
        if self._scan_dialog is not None:
            self._scan_dialog.close_dialog()
            self._scan_dialog = None

        self.file_items = resolved_data
        self.current_page = 0
        self.var_select_all.set(True)
        self._apply_filter_and_render()

    def _on_edit_mode_changed(self, _choice):
        if self.file_items:
            self._render_current_page()

    def _on_filter_changed(self):
        self.current_page = 0
        self._apply_filter_and_render()

    def _on_tree_folder_selected(self, folder_str: str):
        self.entry_path.delete(0, "end")
        self.entry_path.insert(0, folder_str)
        self.load_entered_path()

    def _toggle_sort_by_name(self):
        CTkToolTip.hide_all()
        if self.sort_mode == "name_asc":
            self.sort_mode = "name_desc"
        elif self.sort_mode == "name_desc":
            self.sort_mode = None
        else:
            self.sort_mode = "name_asc"
        self._update_sort_button_labels()
        self.current_page = 0
        self._apply_filter_and_render()

    def _toggle_sort_by_type(self):
        CTkToolTip.hide_all()
        if self.sort_mode == "type_folders":
            self.sort_mode = "type_files"
        elif self.sort_mode == "type_files":
            self.sort_mode = None
        else:
            self.sort_mode = "type_folders"
        self._update_sort_button_labels()
        self.current_page = 0
        self._apply_filter_and_render()

    def _toggle_sort_by_status(self):
        CTkToolTip.hide_all()
        if self.sort_mode == "status_pending":
            self.sort_mode = "status_unchanged"
        elif self.sort_mode == "status_unchanged":
            self.sort_mode = None
        else:
            self.sort_mode = "status_pending"
        self._update_sort_button_labels()
        self.current_page = 0
        self._apply_filter_and_render()

    def _update_sort_button_labels(self):
        if self.sort_mode == "name_asc":
            self.btn_header_name.configure(text="Current Name (A-Z ▲)")
        elif self.sort_mode == "name_desc":
            self.btn_header_name.configure(text="Current Name (Z-A ▼)")
        else:
            self.btn_header_name.configure(text="Current Name ↕")

        if self.sort_mode == "type_folders":
            self.btn_header_type.configure(text="Type (Folders ▲)")
        elif self.sort_mode == "type_files":
            self.btn_header_type.configure(text="Type (Files ▼)")
        else:
            self.btn_header_type.configure(text="Type ↕")

        if self.sort_mode == "status_pending":
            self.btn_header_status.configure(text="Status (Pending ▲)")
        elif self.sort_mode == "status_unchanged":
            self.btn_header_status.configure(text="Status (Unchanged ▼)")
        else:
            self.btn_header_status.configure(text="Status ↕")

    def _apply_filter_and_render(self):
        if not self.file_items:
            self.filtered_items = []
            self._render_current_page()
            return

        if self.var_hide_unchanged.get():
            items = [item for item in self.file_items if item["will_rename"]]
        else:
            items = list(self.file_items)

        if self.sort_mode == "name_asc":
            items.sort(key=lambda x: str(x.get("orig_name", "")).lower())
        elif self.sort_mode == "name_desc":
            items.sort(key=lambda x: str(x.get("orig_name", "")).lower(), reverse=True)
        elif self.sort_mode == "type_folders":
            order_map = {"Folder": 0, "Video": 1, "Audio": 2, "Sub": 3}
            items.sort(key=lambda x: (order_map.get(x["kind"], 9), str(x["path"]).lower()))
        elif self.sort_mode == "type_files":
            order_map = {"Video": 0, "Audio": 1, "Sub": 2, "Folder": 3}
            items.sort(key=lambda x: (order_map.get(x["kind"], 9), str(x["path"]).lower()))
        elif self.sort_mode == "status_pending":
            items.sort(key=lambda x: (
                0 if (x["will_rename"] and x["is_selected"]) else (1 if x["will_rename"] else 2),
                str(x.get("orig_name", "")).lower()
            ))
        elif self.sort_mode == "status_unchanged":
            items.sort(key=lambda x: (
                2 if (x["will_rename"] and x["is_selected"]) else (1 if x["will_rename"] else 0),
                str(x.get("orig_name", "")).lower()
            ))

        self.filtered_items = items
        total_pages = max(1, (len(self.filtered_items) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)

        self._render_current_page()

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render_current_page()

    def _next_page(self):
        total_pages = max(1, (len(self.filtered_items) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._render_current_page()

    def _render_current_page(self):
        for widget in self.scroll_list.winfo_children():
            widget.destroy()

        for item in self.file_items:
            item.pop("chk", None)
            item.pop("selected_var", None)
            item.pop("entry_new", None)
            item.pop("label_new", None)
            item.pop("status_label", None)
            item.pop("diff_badge", None)

        self.btn_select.configure(state="normal")
        self.btn_load_path.configure(state="normal")
        self.btn_rescan.configure(state="normal" if self.selected_folder else "disabled")

        if not self.file_items:
            self.lbl_status.configure(text="No supported media files found.")
            self.lbl_page_info.configure(text="")
            self.btn_prev_page.configure(state="disabled")
            self.btn_next_page.configure(state="disabled")
            self.btn_apply.configure(state="disabled")
            return

        is_media_only = (self.opt_mode.get() == "Media Only (Auto-sync Subs & Folders)")
        if is_media_only:
            self.lbl_header_proposed.configure(text="Proposed New Name (Edit Media / Auto-syncs Subs & Folders)")
        else:
            self.lbl_header_proposed.configure(text="Proposed New Name (Click any row to edit)")

        if not self.filtered_items:
            ctk.CTkLabel(
                self.scroll_list,
                text="All folders and files in this library are already properly named! (Untick 'Hide unchanged folders and files' to view all items).",
                text_color="gray",
                font=ctk.CTkFont(size=13)
            ).grid(row=0, column=1, columnspan=4, padx=15, pady=30)
            self.lbl_page_info.configure(text="0 items need renaming")
            self.btn_prev_page.configure(state="disabled")
            self.btn_next_page.configure(state="disabled")
            self._update_selection_status()
            return

        total_filtered = len(self.filtered_items)
        total_pages = max(1, (total_filtered + PAGE_SIZE - 1) // PAGE_SIZE)
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, total_filtered)
        page_slice = self.filtered_items[start_idx:end_idx]

        self.lbl_page_info.configure(
            text=f"Page {self.current_page + 1} of {total_pages}  (Showing {start_idx + 1}–{end_idx} of {total_filtered} visible items)"
        )
        self.btn_prev_page.configure(state="normal" if self.current_page > 0 else "disabled")
        self.btn_next_page.configure(state="normal" if self.current_page < total_pages - 1 else "disabled")

        for idx, item in enumerate(page_slice):
            var_chk = ctk.BooleanVar(value=item["is_selected"])
            item["selected_var"] = var_chk

            def make_chk_handler(itm, v=var_chk):
                def _on_chk():
                    itm["is_selected"] = v.get()
                    self._update_selection_status()
                return _on_chk

            chk = ctk.CTkCheckBox(
                self.scroll_list,
                text="",
                width=24,
                variable=var_chk,
                state="normal" if item["will_rename"] else "disabled",
                command=make_chk_handler(item)
            )
            chk.grid(row=idx, column=0, padx=(5, 8), pady=4, sticky="w")
            item["chk"] = chk

            lbl_orig = ctk.CTkLabel(
                self.scroll_list,
                text=item["display_orig"],
                anchor="w",
                wraplength=360,
                justify="left"
            )
            lbl_orig.grid(row=idx, column=1, padx=5, pady=4, sticky="w")

            # Column 2: Type badge (Folder, Video, Audio, Sub)
            badge_is_folder = (item["kind"] == "Folder")
            badge_fg = ("#1f6aa5", "#144870") if badge_is_folder else ("gray80", "gray25")
            badge_text_color = "white" if badge_is_folder else ("gray10", "gray90")
            lbl_type = ctk.CTkLabel(
                self.scroll_list,
                text=item["kind"],
                width=65,
                height=22,
                corner_radius=6,
                fg_color=badge_fg,
                text_color=badge_text_color,
                font=ctk.CTkFont(size=11, weight="bold")
            )
            lbl_type.grid(row=idx, column=2, padx=5, pady=4, sticky="w")

            # Column 3: Proposed name & Changing Digit Highlighting
            rel_prefix = ""
            if item["kind"] == "Sub" and item["path"].parent.name.lower() in SUB_DIR_NAMES:
                rel_prefix = f"{item['path'].parent.name}\\"

            entry_frame = ctk.CTkFrame(self.scroll_list, fg_color="transparent")
            entry_frame.grid(row=idx, column=3, padx=5, pady=3, sticky="ew")

            can_edit = (not is_media_only) or (item["kind"] in ("Audio", "Video"))
            digit_ranges = find_changing_digit_ranges(item["orig_name"], item["new_name"]) if item["will_rename"] else []

            if can_edit:
                entry_frame.grid_columnconfigure(1 if rel_prefix else 0, weight=1)
                col_idx = 0
                if rel_prefix:
                    lbl_pre = ctk.CTkLabel(entry_frame, text=rel_prefix, text_color="gray", font=ctk.CTkFont(size=12))
                    lbl_pre.grid(row=0, column=0, padx=(0, 2), sticky="w")
                    col_idx = 1

                entry_new = ctk.CTkEntry(
                    entry_frame,
                    height=28,
                    font=ctk.CTkFont(size=12),
                    text_color="#58A6FF" if item["will_rename"] else ("gray10", "gray90")
                )
                entry_new.insert(0, item["new_name"])
                entry_new.grid(row=0, column=col_idx, sticky="ew")
                item["entry_new"] = entry_new

                def make_handler(itm):
                    return lambda event: self._on_item_name_edited(itm)

                entry_new.bind("<KeyRelease>", make_handler(item))
                entry_new.bind("<FocusOut>", make_handler(item))

                # Contrasting pill highlighting changing digits next to the entry
                if digit_ranges:
                    changed_tokens = [item["new_name"][s:e] for s, e in digit_ranges]
                    diff_text = f"Δ {', '.join(changed_tokens)}"
                    badge = ctk.CTkLabel(
                        entry_frame,
                        text=diff_text,
                        font=ctk.CTkFont(size=11, weight="bold"),
                        text_color="#FFA500",
                        fg_color=("#FFE0B2", "#4D2C00"),
                        corner_radius=4,
                        padx=6,
                        pady=1
                    )
                    badge.grid(row=0, column=col_idx + 1, padx=(6, 2), sticky="e")
                    CTkToolTip(badge, f"Changing digits from original: {', '.join(changed_tokens)}")
                    item["diff_badge"] = badge
            else:
                # Segmented display highlighting changing digits in contrasting vivid orange
                seg_box = ctk.CTkFrame(entry_frame, fg_color="transparent")
                seg_box.pack(side="left", fill="x")

                if rel_prefix:
                    ctk.CTkLabel(seg_box, text=rel_prefix, text_color="gray", font=ctk.CTkFont(size=12)).pack(side="left")

                full_text = item["new_name"]
                if digit_ranges and item["will_rename"]:
                    last_idx = 0
                    for start, end in digit_ranges:
                        if start > last_idx:
                            ctk.CTkLabel(
                                seg_box,
                                text=full_text[last_idx:start],
                                text_color="#58A6FF",
                                font=ctk.CTkFont(size=12)
                            ).pack(side="left")
                        ctk.CTkLabel(
                            seg_box,
                            text=full_text[start:end],
                            text_color="#FFA500",
                            fg_color=("#FFE0B2", "#4D2C00"),
                            corner_radius=3,
                            font=ctk.CTkFont(size=12, weight="bold")
                        ).pack(side="left")
                        last_idx = end
                    if last_idx < len(full_text):
                        ctk.CTkLabel(
                            seg_box,
                            text=full_text[last_idx:],
                            text_color="#58A6FF",
                            font=ctk.CTkFont(size=12)
                        ).pack(side="left")
                else:
                    ctk.CTkLabel(
                        seg_box,
                        text=full_text,
                        text_color="#58A6FF" if item["will_rename"] else "gray",
                        font=ctk.CTkFont(size=12)
                    ).pack(side="left")

                lbl_sync = ctk.CTkLabel(
                    seg_box,
                    text="  (auto-synced)",
                    font=ctk.CTkFont(size=11, slant="italic"),
                    text_color="gray55"
                )
                lbl_sync.pack(side="left")
                item["label_new"] = seg_box

            # Column 4: Status
            if item.get("status_override"):
                status_text = item["status_override"]
                status_color = "#E5A00D"
            elif item["will_rename"] and item["is_selected"]:
                status_text = "Pending"
                status_color = "#D29922"
            elif item["will_rename"]:
                status_text = "Skipped"
                status_color = "gray"
            else:
                status_text = "Unchanged"
                status_color = "gray"

            lbl_tag = ctk.CTkLabel(
                self.scroll_list,
                text=status_text,
                text_color=status_color,
                font=ctk.CTkFont(size=12, weight="bold")
            )
            lbl_tag.grid(row=idx, column=4, padx=(5, 15), pady=4, sticky="e")
            item["status_label"] = lbl_tag

        self._update_selection_status()

    def _on_item_name_edited(self, item):
        if "entry_new" not in item:
            return

        edited_val = item["entry_new"].get().strip()
        item["new_name"] = edited_val
        is_changed = bool(edited_val) and (edited_val != item["orig_name"])
        item["will_rename"] = is_changed
        item["is_selected"] = is_changed

        if "chk" in item:
            item["chk"].configure(state="normal" if is_changed else "disabled")
        if item.get("selected_var"):
            item["selected_var"].set(is_changed)

        item["entry_new"].configure(text_color="#58A6FF" if is_changed else ("gray10", "gray90"))

        # Update diff badge
        digit_ranges = find_changing_digit_ranges(item["orig_name"], edited_val) if is_changed else []
        if item.get("diff_badge"):
            if digit_ranges:
                tokens = [edited_val[s:e] for s, e in digit_ranges]
                item["diff_badge"].configure(text=f"Δ {', '.join(tokens)}")
            else:
                item["diff_badge"].destroy()
                item.pop("diff_badge", None)

        # In Auto-sync mode, cascade changes from video/audio to subtitles and folders
        if self.opt_mode.get() == "Media Only (Auto-sync Subs & Folders)" and item["kind"] in ("Audio", "Video"):
            new_media_stem = Path(edited_val).stem if edited_val else item["path"].stem

            for dep in self.file_items:
                if dep.get("parent_media_id") == item.get("id"):
                    if dep["kind"] == "Sub":
                        dep_new_name = resolve_subtitle_name(
                            dep["path"], dep.get("old_video_stem", ""), new_media_stem, dep.get("dir_count", 1)
                        )
                    elif dep["kind"] == "Folder":
                        if dep.get("is_multi_ep"):
                            continue
                        dep_new_name = sanitize_filename(new_media_stem)
                    else:
                        continue

                    dep["new_name"] = dep_new_name
                    dep_changed = (dep_new_name != dep["orig_name"])
                    dep["will_rename"] = dep_changed
                    dep["is_selected"] = dep_changed

                    if "entry_new" in dep:
                        dep["entry_new"].delete(0, "end")
                        dep["entry_new"].insert(0, dep_new_name)
                        dep["entry_new"].configure(text_color="#58A6FF" if dep_changed else ("gray10", "gray90"))
                    if "chk" in dep:
                        dep["chk"].configure(state="normal" if dep_changed else "disabled")
                    if dep.get("selected_var"):
                        dep["selected_var"].set(dep_changed)

        self._update_selection_status()

    def _toggle_all_checkboxes(self):
        target_state = self.var_select_all.get()
        for item in self.file_items:
            if item["will_rename"]:
                item["is_selected"] = target_state
                if "selected_var" in item and item["selected_var"] is not None:
                    item["selected_var"].set(target_state)
        self._update_selection_status()

    def _update_selection_status(self):
        total_found = len(self.file_items)
        selected_count = 0

        for item in self.file_items:
            if item.get("status_override"):
                if "status_label" in item:
                    item["status_label"].configure(text=item["status_override"], text_color="#E5A00D")
                continue

            if not item["will_rename"]:
                if "status_label" in item:
                    item["status_label"].configure(text="Unchanged", text_color="gray")
                continue

            if item["is_selected"]:
                selected_count += 1
                if "status_label" in item:
                    item["status_label"].configure(text="Pending", text_color="#D29922")
            else:
                if "status_label" in item:
                    item["status_label"].configure(text="Skipped", text_color="gray")

        mode_desc = "TMDb + TVMaze" if self.tmdb_client.is_configured() else "TVMaze (Free) mode"
        self.lbl_status.configure(
            text=f"[{mode_desc}] {total_found} total item(s) scanned ({len(self.filtered_items)} shown). {selected_count} selected for rename."
        )
        self.btn_apply.configure(state="normal" if selected_count > 0 else "disabled")

    def apply_renames(self):
        """Show confirmation dialog with breakdown before executing rename batch."""
        for item in self.file_items:
            if "entry_new" in item:
                val = item["entry_new"].get().strip()
                if val:
                    item["new_name"] = val

        selected_items = [
            item for item in self.file_items
            if item["will_rename"] and item["is_selected"]
        ]
        if not selected_items:
            return

        breakdown = {"Folder": 0, "Video": 0, "Audio": 0, "Sub": 0}
        for itm in selected_items:
            kind = itm.get("kind", "File")
            breakdown[kind] = breakdown.get(kind, 0) + 1

        RenameConfirmDialog(self, breakdown, len(selected_items), on_confirm=self._execute_apply_renames)

    def _execute_apply_renames(self):
        renamed_count = 0
        current_batch = []
        error_details = []

        selected_items = [
            item for item in self.file_items
            if item["will_rename"] and item["is_selected"]
        ]

        dir_renames = sorted(
            [item for item in selected_items if item.get("is_dir", False)],
            key=lambda x: len(x["path"].parts),
            reverse=True
        )
        file_renames = [item for item in selected_items if not item.get("is_dir", False)]
        deferred_dirs = []

        for item in dir_renames:
            src = item["path"]
            sanitized_new = sanitize_filename(item["new_name"]) if item["new_name"] else item["orig_name"]
            base_dest = src.parent / sanitized_new
            dest = base_dest

            counter = 1
            while is_collision(dest, src):
                dest = src.parent / f"{base_dest.name}_{counter}"
                counter += 1

            is_selected_root = bool(
                self.selected_folder and str(src.resolve()).lower() == str(self.selected_folder.resolve()).lower()
            )

            try:
                safe_file_or_dir_rename(src, dest, max_retries=4)
                current_batch.append((dest, src, True))
                renamed_count += 1

                if is_selected_root:
                    self.selected_folder = dest
                    self.entry_path.delete(0, "end")
                    self.entry_path.insert(0, str(self.selected_folder))

                for child_item in file_renames + dir_renames:
                    c_path = child_item["path"]
                    if c_path != src and c_path.is_relative_to(src):
                        child_item["path"] = dest / c_path.relative_to(src)
            except Exception:
                deferred_dirs.append(item)

        for item in file_renames:
            src = item["path"]
            sanitized_new = sanitize_filename(item["new_name"]) if item["new_name"] else item["orig_name"]
            base_dest = src.parent / sanitized_new
            dest = base_dest

            counter = 1
            while is_collision(dest, src):
                dest = src.parent / f"{base_dest.stem}_{counter}{base_dest.suffix}"
                counter += 1

            try:
                safe_file_or_dir_rename(src, dest)
                current_batch.append((dest, src, False))
                renamed_count += 1
            except Exception as err:
                error_details.append(f"{src.name}: {err}")

        for item in deferred_dirs:
            src = item["path"]
            sanitized_new = sanitize_filename(item["new_name"]) if item["new_name"] else item["orig_name"]
            base_dest = src.parent / sanitized_new
            dest = base_dest

            counter = 1
            while is_collision(dest, src):
                dest = src.parent / f"{base_dest.name}_{counter}"
                counter += 1

            is_selected_root = bool(
                self.selected_folder and str(src.resolve()).lower() == str(self.selected_folder.resolve()).lower()
            )

            try:
                safe_file_or_dir_rename(src, dest, max_retries=8)
                current_batch.append((dest, src, True))
                renamed_count += 1

                if is_selected_root:
                    self.selected_folder = dest
                    self.entry_path.delete(0, "end")
                    self.entry_path.insert(0, str(self.selected_folder))
            except Exception as err:
                error_details.append(f"[Folder] {src.name}: {err}")

        if current_batch:
            self.last_rename_batch = [(d, s) for d, s, _ in current_batch]
            self.btn_undo.configure(state="normal")

            renamed_lookup = {src: dest for dest, src, _ in current_batch}
            for itm in self.file_items:
                old_p = itm["path"]
                if old_p in renamed_lookup:
                    new_p = renamed_lookup[old_p]
                    itm["path"] = new_p
                    itm["orig_name"] = new_p.name
                    itm["new_name"] = new_p.name
                    itm["will_rename"] = False
                    itm["is_selected"] = False
                    if itm["kind"] == "Sub":
                        rel = f"{new_p.parent.name}\\" if new_p.parent != itm.get("folder_group") else ""
                        itm["display_orig"] = f"{rel}{new_p.name}"
                    else:
                        itm["display_orig"] = new_p.name

                fg = itm.get("folder_group")
                if fg and fg in renamed_lookup:
                    itm["folder_group"] = renamed_lookup[fg]

            self._apply_filter_and_render()
            self._update_selection_status()

        if error_details:
            msg = f"Renamed {renamed_count} item(s).\n\nThe following error(s) occurred:\n• " + "\n• ".join(error_details[:5])
            if len(error_details) > 5:
                msg += f"\n...and {len(error_details) - 5} more."
            messagebox.showwarning("Renaming Result", msg)
        else:
            messagebox.showinfo(
                "Renaming Complete",
                f"Successfully renamed {renamed_count} item(s)."
            )

    def undo_last_rename(self):
        if not self.last_rename_batch:
            return

        restored_count = 0
        error_details = []

        remaining = list(reversed(self.last_rename_batch))
        for i, (current_path, original_path) in enumerate(remaining):
            try:
                if current_path.exists():
                    is_selected_root = bool(
                        self.selected_folder and str(current_path.resolve()).lower() == str(self.selected_folder.resolve()).lower()
                    )
                    safe_file_or_dir_rename(current_path, original_path)
                    restored_count += 1
                    if is_selected_root:
                        self.selected_folder = original_path
                        self.entry_path.delete(0, "end")
                        self.entry_path.insert(0, str(self.selected_folder))

                    if original_path.is_dir():
                        for j in range(i + 1, len(remaining)):
                            c_p, o_p = remaining[j]
                            if c_p.is_relative_to(current_path):
                                new_c_p = original_path / c_p.relative_to(current_path)
                            else:
                                new_c_p = c_p
                            if o_p.is_relative_to(current_path):
                                new_o_p = original_path / o_p.relative_to(current_path)
                            else:
                                new_o_p = o_p
                            remaining[j] = (new_c_p, new_o_p)
            except Exception as err:
                error_details.append(f"{current_path.name}: {err}")

        if restored_count > 0:
            restored_lookup = {curr: orig for curr, orig in self.last_rename_batch if not curr.exists() and orig.exists()}
            for itm in self.file_items:
                p = itm["path"]
                if p in restored_lookup:
                    orig_p = restored_lookup[p]
                    itm["path"] = orig_p
                    itm["orig_name"] = orig_p.name
                    changed = (itm["new_name"] != orig_p.name)
                    itm["will_rename"] = changed
                    itm["is_selected"] = changed
                    if itm["kind"] == "Sub":
                        rel = f"{orig_p.parent.name}\\" if orig_p.parent != itm.get("folder_group") else ""
                        itm["display_orig"] = f"{rel}{orig_p.name}"
                    else:
                        itm["display_orig"] = orig_p.name

                fg = itm.get("folder_group")
                if fg and fg in restored_lookup:
                    itm["folder_group"] = restored_lookup[fg]

            self._apply_filter_and_render()
            self._update_selection_status()

        self.last_rename_batch = []
        self.btn_undo.configure(state="disabled")

        if error_details:
            msg = f"Restored {restored_count} item(s).\n\nThe following error(s) occurred during undo:\n• " + "\n• ".join(error_details[:5])
            messagebox.showwarning("Undo Result", msg)
        else:
            messagebox.showinfo(
                "Undo Complete",
                f"Restored {restored_count} item(s) to their original names."
            )


if __name__ == "__main__":
    app = MediaRenamerApp()
    app.mainloop()
