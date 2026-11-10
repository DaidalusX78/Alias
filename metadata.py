"""
Metadata integration module for Alias: TMDb, TVMaze, and TheAudioDB.
Provides cached, circuit-breaker protected API calls and Windows DPAPI credential security.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Any

import requests

CONFIG_PATH = Path.home() / ".alias_renamer_config.json"


# ---------------- Windows DPAPI Secure Storage ----------------

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def encrypt_secret(secret_text: str) -> str:
    """Encrypt a secret string using Windows DPAPI (current user scope)."""
    if not secret_text or not hasattr(ctypes, "windll"):
        return secret_text
    try:
        raw_bytes = secret_text.encode("utf-8")
        in_blob = _DATA_BLOB(len(raw_bytes), ctypes.cast(raw_bytes, ctypes.POINTER(ctypes.c_char)))
        out_blob = _DATA_BLOB()
        if ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob), "AliasKey", None, None, None, 0, ctypes.byref(out_blob)
        ):
            encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
            return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    except Exception:
        pass
    return secret_text


def decrypt_secret(stored_text: str) -> str:
    """Decrypt a secret string encrypted with Windows DPAPI."""
    if not stored_text or not stored_text.startswith("dpapi:") or not hasattr(ctypes, "windll"):
        return stored_text
    try:
        raw_b64 = stored_text[len("dpapi:"):]
        encrypted_bytes = base64.b64decode(raw_b64)
        in_blob = _DATA_BLOB(len(encrypted_bytes), ctypes.cast(encrypted_bytes, ctypes.POINTER(ctypes.c_char)))
        out_blob = _DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            decrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
            return decrypted.decode("utf-8")
    except Exception:
        pass
    return ""


# ---------------- TMDb Client with Circuit Breaker ----------------

class TMDbClient:
    """TMDb API client with persistent HTTP session, negative caching, and failure circuit breaker."""
    BASE_URL = "https://api.themoviedb.org/3"
    MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self, api_key: str = "", language: str = "en-US"):
        self.api_key = api_key.strip()
        self.language = language or "en-US"
        self._cache: dict[str, Any] = {}
        self._session = requests.Session()
        self.consecutive_failures = 0
        self.circuit_open = False

    def is_configured(self) -> bool:
        return bool(self.api_key) and not self.circuit_open

    def reset_circuit(self) -> None:
        self.consecutive_failures = 0
        self.circuit_open = False

    def _record_success(self) -> None:
        self.consecutive_failures = 0

    def _record_failure(self, status_code: int | None = None) -> None:
        if status_code in (401, 403):
            # Invalid API key - trip immediately
            self.circuit_open = True
            return
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self.circuit_open = True

    def search_tv_show(self, title: str, language: str | None = None) -> dict[str, Any] | None:
        if not self.is_configured() or not title:
            return None
        lang = language or self.language or "en-US"
        cache_key = f"tv_{title.strip().lower()}_{lang}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.BASE_URL}/search/tv"
        params = {"api_key": self.api_key, "query": title, "language": lang}
        try:
            resp = self._session.get(url, params=params, timeout=4)
            if resp.status_code == 200:
                self._record_success()
                results = resp.json().get("results", [])
                res = results[0] if results else None
                self._cache[cache_key] = res
                return res
            self._record_failure(resp.status_code)
        except Exception:
            self._record_failure()

        self._cache[cache_key] = None
        return None

    def get_episode_details(
        self, show_id: int, season: int, episode: int, language: str | None = None
    ) -> dict[str, Any] | None:
        if not self.is_configured() or not show_id:
            return None
        lang = language or self.language or "en-US"
        cache_key = f"ep_{show_id}_{season}_{episode}_{lang}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.BASE_URL}/tv/{show_id}/season/{season}/episode/{episode}"
        params = {"api_key": self.api_key, "language": lang}
        try:
            resp = self._session.get(url, params=params, timeout=4)
            if resp.status_code == 200:
                self._record_success()
                data = resp.json()
                self._cache[cache_key] = data
                return data
            self._record_failure(resp.status_code)
        except Exception:
            self._record_failure()

        self._cache[cache_key] = None
        return None

    @staticmethod
    def _pick_best_movie_match(results: list[dict[str, Any]], target_year: str | None) -> dict[str, Any] | None:
        if not results:
            return None
        if not target_year:
            return results[0]

        target_year = str(target_year).strip()
        # 1. Exact primary release year match
        for m in results:
            rd = m.get("release_date", "")
            if rd and len(rd) >= 4 and rd[:4] == target_year:
                return m

        # 2. Tolerant ±1 year match (handles festival vs theatrical or regional releases)
        try:
            y_int = int(target_year)
            for m in results:
                rd = m.get("release_date", "")
                if rd and len(rd) >= 4:
                    try:
                        m_year = int(rd[:4])
                        if abs(m_year - y_int) <= 1:
                            return m
                    except ValueError:
                        pass

            # 3. Tolerant ±2 years match
            for m in results:
                rd = m.get("release_date", "")
                if rd and len(rd) >= 4:
                    try:
                        m_year = int(rd[:4])
                        if abs(m_year - y_int) <= 2:
                            return m
                    except ValueError:
                        pass
        except ValueError:
            pass

        # If target year was explicitly specified and no result is within 2 years,
        # do NOT pick an unrelated movie/sequel dated 5+ years away!
        return None

    def search_movie(
        self, title: str, year: str | None = None, language: str | None = None
    ) -> dict[str, Any] | None:
        if not self.is_configured() or not title:
            return None
        lang = language or self.language or "en-US"
        cache_key = f"movie_{title.strip().lower()}_{year}_{lang}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.BASE_URL}/search/movie"
        params: dict[str, Any] = {"api_key": self.api_key, "query": title, "language": lang}
        if year:
            params["primary_release_year"] = year

        try:
            resp = self._session.get(url, params=params, timeout=4)
            if resp.status_code == 200:
                self._record_success()
                results = resp.json().get("results", [])

                # If primary_release_year was too strict or returned no hits, fallback
                if not results and year:
                    fb_resp = self._session.get(
                        url, params={"api_key": self.api_key, "query": title, "year": year, "language": lang}, timeout=4
                    )
                    if fb_resp.status_code == 200:
                        results = fb_resp.json().get("results", [])

                if not results and year:
                    fb_resp = self._session.get(
                        url, params={"api_key": self.api_key, "query": title, "language": lang}, timeout=4
                    )
                    if fb_resp.status_code == 200:
                        results = fb_resp.json().get("results", [])

                res = self._pick_best_movie_match(results, year)
                self._cache[cache_key] = res
                return res
            self._record_failure(resp.status_code)
        except Exception:
            self._record_failure()

        self._cache[cache_key] = None
        return None


# ---------------- TVMaze Free Client (No API Key Required) ----------------

class TVMazeClient:
    """Free TV metadata lookup via TVMaze REST API (no key needed)."""
    BASE_URL = "https://api.tvmaze.com"

    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._session = requests.Session()
        self.circuit_open = False
        self.consecutive_failures = 0

    def search_show(self, title: str) -> dict[str, Any] | None:
        if self.circuit_open or not title:
            return None
        cache_key = f"tvm_show_{title.strip().lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.BASE_URL}/singlesearch/shows"
        params = {"q": title}
        try:
            resp = self._session.get(url, params=params, timeout=4)
            if resp.status_code == 200:
                self.consecutive_failures = 0
                data = resp.json()
                self._cache[cache_key] = data
                return data
            elif resp.status_code == 404:
                self._cache[cache_key] = None
                return None
        except Exception:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 4:
                self.circuit_open = True

        self._cache[cache_key] = None
        return None

    def get_episode_title(self, show_id: int, season: int, episode: int) -> str:
        if self.circuit_open or not show_id:
            return ""
        cache_key = f"tvm_ep_{show_id}_{season}_{episode}"
        if cache_key in self._cache:
            return self._cache[cache_key] or ""

        url = f"{self.BASE_URL}/shows/{show_id}/episodebynumber"
        params = {"season": season, "number": episode}
        try:
            resp = self._session.get(url, params=params, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                ep_name = data.get("name", "")
                self._cache[cache_key] = ep_name
                return ep_name
        except Exception:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 4:
                self.circuit_open = True

        self._cache[cache_key] = None
        return ""


# ---------------- TheAudioDB Client (Audio Enrichment) ----------------

class TheAudioDBClient:
    """TheAudioDB client for looking up music track titles and metadata."""
    BASE_URL = "https://www.theaudiodb.com/api/v1/json"

    def __init__(self, api_key: str = "2"):
        # Key '2' is the public test key provided by TheAudioDB
        self.api_key = api_key.strip() or "2"
        self._cache: dict[str, Any] = {}
        self._session = requests.Session()
        self.circuit_open = False

    def search_track(self, artist: str, track_title: str) -> dict[str, Any] | None:
        if self.circuit_open or not artist or not track_title:
            return None
        cache_key = f"adb_{artist.strip().lower()}_{track_title.strip().lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.BASE_URL}/{self.api_key}/searchtrack.php"
        params = {"s": artist, "t": track_title}
        try:
            resp = self._session.get(url, params=params, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                tracks = data.get("track") if data else None
                res = tracks[0] if tracks else None
                self._cache[cache_key] = res
                return res
        except Exception:
            pass

        self._cache[cache_key] = None
        return None
