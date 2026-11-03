"""
Windows File System and Shell Integration for Alias.
Handles mapped network drive discovery and restoration (M:, P:), modern folder picker,
and Shell API (SHFileOperationW) safe rename fallbacks for Explorer lock avoidance.
"""

from __future__ import annotations

import ctypes
import gc
import os
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def _win32_shell_rename(src: Path, dest: Path) -> bool:
    """Uses Windows Shell API (SHFileOperationW) to rename a folder or file safely."""
    if not hasattr(ctypes, "windll"):
        return False
    try:
        FO_RENAME = 0x0004
        FOF_SILENT = 0x0004
        FOF_NOCONFIRMATION = 0x0010
        FOF_NOCONFIRMMKDIR = 0x0200
        FOF_NOERRORUI = 0x0400

        op = _SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_RENAME
        op.pFrom = str(src.resolve()) + "\0\0"
        op.pTo = str(dest.resolve()) + "\0\0"
        op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_NOCONFIRMMKDIR | FOF_NOERRORUI

        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return res == 0 and not op.fAnyOperationsAborted and dest.exists()
    except Exception:
        return False


def safe_file_or_dir_rename(src: Path, dest: Path, max_retries: int = 8) -> None:
    """
    Renames a file or directory safely on Windows:
    1. Releases Python working directory lock.
    2. Retries with backoff.
    3. Falls back to Windows Shell SHFileOperationW to release Explorer thumbnail handles.
    """
    try:
        os.chdir(tempfile.gettempdir())
    except Exception:
        pass
    gc.collect()

    last_err = None
    for attempt in range(max_retries):
        try:
            src.rename(dest)
            return
        except (PermissionError, OSError) as err:
            last_err = err
            if _win32_shell_rename(src, dest):
                return
            time.sleep(0.15 * (attempt + 1))

    if last_err:
        raise last_err


class NETRESOURCEW(ctypes.Structure):
    _fields_ = [
        ("dwScope", wintypes.DWORD),
        ("dwType", wintypes.DWORD),
        ("dwDisplayType", wintypes.DWORD),
        ("dwUsage", wintypes.DWORD),
        ("lpLocalName", wintypes.LPWSTR),
        ("lpRemoteName", wintypes.LPWSTR),
        ("lpComment", wintypes.LPWSTR),
        ("lpProvider", wintypes.LPWSTR),
    ]


def restore_network_drive(letter: str, remote_path: str) -> None:
    """Attempts to reconnect a disconnected mapped network drive via Windows MPR."""
    if not hasattr(ctypes, "windll"):
        return
    try:
        nr = NETRESOURCEW()
        nr.dwType = 1  # RESOURCETYPE_DISK
        nr.lpLocalName = f"{letter}:"
        nr.lpRemoteName = remote_path
        ctypes.windll.mpr.WNetAddConnection2W(ctypes.byref(nr), None, None, 1)
    except Exception:
        pass


def get_detected_drives() -> list[tuple[str, str]]:
    """
    Enumerates all logical drives and HKCU\\Network persistent drives (e.g. M:, P:).
    Designed to be run in a background thread so UI never freezes.
    """
    drives: list[tuple[str, str]] = []
    seen_roots: set[str] = set()

    # 1. Query HKCU\Network for persistent mapped network drives
    if winreg is not None:
        try:
            net_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Network")
            for i in range(winreg.QueryInfoKey(net_key)[0]):
                try:
                    letter = winreg.EnumKey(net_key, i).upper()
                    subkey = winreg.OpenKey(net_key, letter)
                    remote_path = winreg.QueryValueEx(subkey, "RemotePath")[0]
                    root_path = f"{letter}:\\"

                    if not Path(root_path).exists():
                        restore_network_drive(letter, remote_path)

                    label = f"{letter}: [Network: {remote_path}]"
                    drives.append((root_path, label))
                    seen_roots.add(root_path.lower())

                    if remote_path:
                        try:
                            if Path(remote_path).exists():
                                unc_root = remote_path.rstrip("\\") + "\\"
                                if unc_root.lower() not in seen_roots:
                                    drives.append((unc_root, f"Share: {remote_path}"))
                                    seen_roots.add(unc_root.lower())
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    # 2. Query GetLogicalDrives
    if hasattr(ctypes, "windll"):
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                if bitmask & 1:
                    root_path = f"{letter}:\\"
                    if root_path.lower() not in seen_roots:
                        dtype = ctypes.windll.kernel32.GetDriveTypeW(root_path)
                        remote_buf = ctypes.create_unicode_buffer(512)
                        remote_len = ctypes.c_ulong(512)
                        res = ctypes.windll.mpr.WNetGetConnectionW(f"{letter}:", remote_buf, ctypes.byref(remote_len))
                        remote_name = remote_buf.value if res == 0 else ""

                        label = f"{letter}:"
                        if remote_name:
                            label += f" [Network: {remote_name}]"
                        elif dtype == 2:
                            label += " [Removable]"
                        elif dtype == 3:
                            label += " [Local Disk]"
                        elif dtype == 4:
                            label += " [Network Drive]"
                        elif dtype == 5:
                            label += " [CD/DVD]"
                        drives.append((root_path, label))
                        seen_roots.add(root_path.lower())
                bitmask >>= 1
        except Exception:
            pass

    return drives if drives else [("C:\\", "C: [Local Disk]")]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


CLSID_FileOpenDialog = GUID(
    0xDC1C5A9C, 0xE88A, 0x4DDE, (wintypes.BYTE * 8)(0xA5, 0xA1, 0x60, 0xF8, 0x2A, 0x20, 0xAE, 0xF7)
)
IID_IFileOpenDialog = GUID(
    0xD57C7288, 0xD4AD, 0x4768, (wintypes.BYTE * 8)(0xBE, 0x02, 0x9D, 0x96, 0x95, 0x32, 0xD9, 0x60)
)
IID_IShellItem = GUID(
    0x43826D1E, 0xE718, 0x42EE, (wintypes.BYTE * 8)(0xBC, 0x55, 0xA1, 0xE2, 0x61, 0xC3, 0x7B, 0xFE)
)


def pick_folder_native(
    parent_hwnd: int | None = None,
    title: str = "Select Media Folder",
    initial_path: str | None = None
) -> str | None:
    """Modern Windows Explorer IFileOpenDialog with FOS_PICKFOLDERS."""
    if not hasattr(ctypes, "windll"):
        return None
    try:
        ole32 = ctypes.oledll.ole32
        shell32 = ctypes.windll.shell32
        ole32.CoInitialize(None)

        dialog = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_FileOpenDialog), None, 1, ctypes.byref(IID_IFileOpenDialog), ctypes.byref(dialog)
        )
        if hr != 0 or not dialog.value:
            ole32.CoUninitialize()
            return None

        vtable = ctypes.cast(
            ctypes.cast(dialog.value, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p),
        )
        Release_Dialog = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vtable[2])
        Show = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.HWND)(vtable[3])
        SetOptions = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.DWORD)(vtable[9])
        GetOptions = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))(vtable[10])
        SetFolder = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p)(vtable[12])
        SetTitle = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.LPCWSTR)(vtable[17])
        GetResult = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable[20])

        try:
            options = wintypes.DWORD()
            GetOptions(dialog, ctypes.byref(options))
            FOS_PICKFOLDERS = 0x00000020
            FOS_FORCEFILESYSTEM = 0x00000040
            FOS_PATHMUSTEXIST = 0x00000800
            SetOptions(dialog, options.value | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST)

            if title:
                SetTitle(dialog, title)

            if initial_path and Path(initial_path).exists():
                init_item = ctypes.c_void_p()
                hr_item = shell32.SHCreateItemFromParsingName(
                    str(initial_path), None, ctypes.byref(IID_IShellItem), ctypes.byref(init_item)
                )
                if hr_item == 0 and init_item.value:
                    SetFolder(dialog, init_item)
                    item_vtable = ctypes.cast(
                        ctypes.cast(init_item.value, ctypes.POINTER(ctypes.c_void_p))[0],
                        ctypes.POINTER(ctypes.c_void_p),
                    )
                    ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(item_vtable[2])(init_item)

            ret = Show(dialog, parent_hwnd or 0)
            if ret == 0:
                result_item = ctypes.c_void_p()
                if GetResult(dialog, ctypes.byref(result_item)) == 0 and result_item.value:
                    try:
                        res_vtable = ctypes.cast(
                            ctypes.cast(result_item.value, ctypes.POINTER(ctypes.c_void_p))[0],
                            ctypes.POINTER(ctypes.c_void_p),
                        )
                        GetDisplayName = ctypes.WINFUNCTYPE(
                            ctypes.HRESULT, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR)
                        )(res_vtable[5])
                        psz_path = wintypes.LPWSTR()
                        SIGDN_FILESYSPATH = 0x80058000
                        if GetDisplayName(result_item, SIGDN_FILESYSPATH, ctypes.byref(psz_path)) == 0 and psz_path.value:
                            chosen_path = psz_path.value
                            ole32.CoTaskMemFree(psz_path)
                            return chosen_path
                    finally:
                        res_vtable = ctypes.cast(
                            ctypes.cast(result_item.value, ctypes.POINTER(ctypes.c_void_p))[0],
                            ctypes.POINTER(ctypes.c_void_p),
                        )
                        ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(res_vtable[2])(result_item)
            return ""
        finally:
            Release_Dialog(dialog)
            ole32.CoUninitialize()
    except Exception:
        return None
