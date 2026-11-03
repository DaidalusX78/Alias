"""
Reusable UI Components and Dialogs for Alias CustomTkinter interface.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from typing import Any

import customtkinter as ctk

from winfs import get_detected_drives


class CTkToolTip:
    """
    Singleton-backed tooltip system.
    Reuses a single persistent Toplevel window to eliminate window creation leaks and stuck tooltips.
    """
    _window: ctk.CTkToplevel | None = None
    _label: ctk.CTkLabel | None = None
    _timer_id: str | None = None
    _current_widget: Any = None

    @classmethod
    def hide_all(cls) -> None:
        if cls._timer_id and cls._current_widget:
            try:
                cls._current_widget.after_cancel(cls._timer_id)
            except Exception:
                pass
            cls._timer_id = None
        if cls._window and cls._window.winfo_exists():
            try:
                cls._window.withdraw()
            except Exception:
                pass
        cls._current_widget = None

    def __init__(self, widget: Any, text: str):
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)
        self.widget.bind("<ButtonPress>", self.hide_tip)
        self.widget.bind("<FocusOut>", self.hide_tip)
        self.widget.bind("<Destroy>", self.hide_tip)

    def show_tip(self, event=None) -> None:
        CTkToolTip.hide_all()
        if not self.text:
            return
        try:
            root = self.widget.winfo_toplevel()
            if CTkToolTip._window is None or not CTkToolTip._window.winfo_exists():
                CTkToolTip._window = tw = ctk.CTkToplevel(root)
                tw.wm_overrideredirect(True)
                tw.attributes("-topmost", True)
                tw.withdraw()
                CTkToolTip._label = lbl = ctk.CTkLabel(
                    tw,
                    text="",
                    font=ctk.CTkFont(size=11),
                    fg_color=("gray85", "gray20"),
                    text_color=("gray10", "gray90"),
                    corner_radius=6,
                    padx=8,
                    pady=4
                )
                lbl.pack()
                tw.bind("<ButtonPress>", lambda e: CTkToolTip.hide_all())
                lbl.bind("<ButtonPress>", lambda e: CTkToolTip.hide_all())

            CTkToolTip._label.configure(text=self.text)
            self.widget.update_idletasks()
            x = self.widget.winfo_rootx() + 15
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            CTkToolTip._window.wm_geometry(f"+{x}+{y}")
            CTkToolTip._window.deiconify()
            CTkToolTip._current_widget = self.widget

            # Auto-dismiss after 3.5 seconds
            CTkToolTip._timer_id = self.widget.after(3500, CTkToolTip.hide_all)
        except Exception:
            CTkToolTip.hide_all()

    def hide_tip(self, event=None) -> None:
        CTkToolTip.hide_all()


class FolderTreeDropdown:
    """
    Interactive dropdown directory tree anchored to the Folder Path bar.
    Opens exclusively via the dropdown toggle button (allowing full text selection/pasting in path bar).
    Binds outside click detection only while open to prevent handler accumulation.
    """
    def __init__(self, parent: ctk.CTk, entry_widget: ctk.CTkEntry, on_select_callback: Callable[[str], None]):
        self.parent = parent
        self.entry_widget = entry_widget
        self.on_select_callback = on_select_callback
        self.popup: ctk.CTkToplevel | None = None
        self.tree: ttk.Treeview | None = None
        self._click_binding_id: str | None = None

    def is_open(self) -> bool:
        return self.popup is not None and self.popup.winfo_exists()

    def close(self) -> None:
        if self._click_binding_id:
            try:
                self.parent.unbind("<Button-1>", self._click_binding_id)
            except Exception:
                pass
            self._click_binding_id = None

        if self.popup and self.popup.winfo_exists():
            try:
                self.popup.destroy()
            except Exception:
                pass
        self.popup = None
        self.tree = None

    def toggle(self, event=None) -> None:
        if self.is_open():
            self.close()
        else:
            self.open()

    def open(self) -> None:
        self.close()
        try:
            self.parent.update_idletasks()
            x = self.entry_widget.winfo_rootx()
            y = self.entry_widget.winfo_rooty() + self.entry_widget.winfo_height() + 4
            w = max(self.entry_widget.winfo_width(), 460)
            h = 320

            self.popup = tw = ctk.CTkToplevel(self.parent)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"{w}x{h}+{x}+{y}")
            tw.attributes("-topmost", True)

            border_frame = ctk.CTkFrame(tw, corner_radius=8, border_width=2, border_color=("gray60", "gray40"))
            border_frame.pack(fill="both", expand=True)

            hdr = ctk.CTkFrame(border_frame, fg_color="transparent")
            hdr.pack(fill="x", padx=10, pady=(6, 2))
            ctk.CTkLabel(hdr, text="Browse Folder Tree:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
            btn_close = ctk.CTkButton(
                hdr, text="✕", width=24, height=20, fg_color="transparent",
                hover_color=("gray80", "gray30"), command=self.close
            )
            btn_close.pack(side="right")

            tree_container = ctk.CTkFrame(border_frame, fg_color="transparent")
            tree_container.pack(fill="both", expand=True, padx=8, pady=(0, 6))

            is_dark = (ctk.get_appearance_mode().lower() == "dark")
            bg_color = "#242424" if is_dark else "#F5F5F5"
            fg_color = "#FFFFFF" if is_dark else "#1A1A1A"
            select_bg = "#1F6AA5"

            style = ttk.Style(tw)
            style.theme_use("clam")
            style.configure(
                "FolderTree.Treeview",
                background=bg_color,
                foreground=fg_color,
                fieldbackground=bg_color,
                rowheight=24,
                font=("Segoe UI", 10),
                borderwidth=0
            )
            style.map("FolderTree.Treeview", background=[("selected", select_bg)], foreground=[("selected", "#FFFFFF")])

            self.tree = tree = ttk.Treeview(tree_container, style="FolderTree.Treeview", selectmode="browse", show="tree")
            vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")

            # Populate detected drives
            drives = get_detected_drives()
            for root_path, label in drives:
                node = tree.insert("", "end", text=f"🖴  {label}", values=[str(root_path)], open=False)
                tree.insert(node, "end", text="...")

            def on_tree_open(evt):
                cur_node = tree.focus()
                if not cur_node:
                    return
                children = tree.get_children(cur_node)
                if len(children) == 1 and tree.item(children[0], "text") == "...":
                    tree.delete(children[0])
                    dir_path = tree.item(cur_node, "values")[0]
                    try:
                        with os.scandir(dir_path) as it:
                            entries = sorted(
                                [e for e in it if e.is_dir() and not e.name.startswith(("$", "."))],
                                key=lambda e: e.name.lower()
                            )
                            for sub in entries:
                                sub_node = tree.insert(cur_node, "end", text=f"📁  {sub.name}", values=[sub.path], open=False)
                                tree.insert(sub_node, "end", text="...")
                    except Exception:
                        pass

            tree.bind("<<TreeviewOpen>>", on_tree_open)

            def do_choose(evt=None):
                cur_node = tree.focus()
                if cur_node:
                    vals = tree.item(cur_node, "values")
                    if vals and len(vals) > 0:
                        chosen = vals[0]
                        self.close()
                        if self.on_select_callback:
                            self.on_select_callback(chosen)

            tree.bind("<Double-1>", do_choose)
            tree.bind("<Return>", do_choose)

            action_bar = ctk.CTkFrame(border_frame, fg_color="transparent")
            action_bar.pack(fill="x", padx=10, pady=(0, 6))

            btn_ok = ctk.CTkButton(action_bar, text="Select Folder", height=24, width=110, font=ctk.CTkFont(size=11, weight="bold"), command=do_choose)
            btn_ok.pack(side="right", padx=2)

            tw.bind("<Escape>", lambda e: self.close())
            # Track outside clicks cleanly
            self._click_binding_id = self.parent.bind("<Button-1>", self._check_click_outside, add="+")
        except Exception:
            self.close()

    def _check_click_outside(self, event):
        if not self.is_open():
            return
        try:
            x, y = event.x_root, event.y_root
            px = self.popup.winfo_rootx()
            py = self.popup.winfo_rooty()
            pw = self.popup.winfo_width()
            ph = self.popup.winfo_height()

            # Ignore clicks inside popup
            if px <= x <= px + pw and py <= y <= py + ph:
                return
            self.close()
        except Exception:
            self.close()


class ScanProgressDialog(ctk.CTkToplevel):
    """Modal progress pop-up shown during media directory scanning."""
    def __init__(self, parent: ctk.CTk, folder_path: Path, on_cancel: Callable[[], None]):
        super().__init__(parent)
        self.title("Scanning Media Folder...")
        self.geometry("480x195")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - 480) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - 195) // 2
        self.geometry(f"+{max(px, 50)}+{max(py, 50)}")

        self._on_cancel = on_cancel
        self.protocol("WM_DELETE_WINDOW", self._handle_cancel)

        self.grid_columnconfigure(0, weight=1)

        self.lbl_title = ctk.CTkLabel(
            self,
            text="Scanning folder, please wait...",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        self.lbl_title.grid(row=0, column=0, padx=20, pady=(18, 4), sticky="w")

        self.lbl_folder = ctk.CTkLabel(
            self,
            text=str(folder_path),
            font=ctk.CTkFont(size=12),
            text_color="gray",
            anchor="w"
        )
        self.lbl_folder.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.progress = ctk.CTkProgressBar(self, mode="indeterminate")
        self.progress.grid(row=2, column=0, padx=20, pady=6, sticky="ew")
        self.progress.start()
        self._is_indeterminate = True

        self.lbl_detail = ctk.CTkLabel(
            self,
            text="Discovering media files on disk...",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.lbl_detail.grid(row=3, column=0, padx=20, pady=(4, 10), sticky="ew")

        self.btn_cancel = ctk.CTkButton(
            self,
            text="Cancel Scan",
            width=110,
            fg_color="#D9534F",
            hover_color="#C9302C",
            command=self._handle_cancel
        )
        self.btn_cancel.grid(row=4, column=0, padx=20, pady=(0, 14), sticky="e")

    def update_progress(self, current: int, total: int, current_name: str) -> None:
        if not self.winfo_exists():
            return
        if total > 0:
            if self._is_indeterminate:
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self._is_indeterminate = False
            self.progress.set(min(max(current / total, 0.0), 1.0))
        short_name = (current_name[:48] + "...") if len(current_name) > 51 else current_name
        self.lbl_detail.configure(text=f"Processed {current} of {total} media files — {short_name}")

    def _handle_cancel(self) -> None:
        self.btn_cancel.configure(state="disabled", text="Cancelling...")
        if self._on_cancel:
            self._on_cancel()

    def close_dialog(self) -> None:
        try:
            self.progress.stop()
        except Exception:
            pass
        try:
            self.grab_release()
            self.destroy()
        except Exception:
            pass


class RenameConfirmDialog(ctk.CTkToplevel):
    """Modal confirmation dialog showing breakdown by type before executing rename batch."""
    def __init__(self, parent: ctk.CTk, breakdown: dict[str, int], total_count: int, on_confirm: Callable[[], None]):
        super().__init__(parent)
        self.title("Confirm Batch Renaming")
        self.geometry("460x230")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - 460) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - 230) // 2
        self.geometry(f"+{max(px, 50)}+{max(py, 50)}")

        self.on_confirm = on_confirm

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=f"Apply Renaming to {total_count} item(s)?",
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        # Breakdown summary
        parts: list[str] = []
        if breakdown.get("Folder", 0):
            parts.append(f"• {breakdown['Folder']} Folder(s)")
        if breakdown.get("Video", 0):
            parts.append(f"• {breakdown['Video']} Video file(s)")
        if breakdown.get("Audio", 0):
            parts.append(f"• {breakdown['Audio']} Audio track(s)")
        if breakdown.get("Sub", 0):
            parts.append(f"• {breakdown['Sub']} Subtitle (.srt) file(s)")

        summary_text = "\n".join(parts) if parts else "No items selected."
        ctk.CTkLabel(
            self,
            text=summary_text,
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="w"
        ).grid(row=1, column=0, padx=25, pady=6, sticky="w")

        ctk.CTkLabel(
            self,
            text="You can undo this operation after applying if needed.",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color="gray"
        ).grid(row=2, column=0, padx=20, pady=(4, 14), sticky="w")

        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.grid(row=3, column=0, padx=20, pady=(0, 15), sticky="e")

        ctk.CTkButton(
            btn_box,
            text="Cancel",
            width=90,
            fg_color="gray30",
            hover_color="gray40",
            command=self._cancel
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_box,
            text="Apply Renames",
            width=130,
            font=ctk.CTkFont(weight="bold"),
            fg_color="#2EA043",
            hover_color="#238636",
            command=self._proceed
        ).pack(side="left")

    def _cancel(self):
        self.grab_release()
        self.destroy()

    def _proceed(self):
        self.grab_release()
        self.destroy()
        if self.on_confirm:
            self.on_confirm()
