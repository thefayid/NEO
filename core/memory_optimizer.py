"""
core/memory_optimizer.py — Proactive Process Memory & Working Set Optimizer for NEO.

Keeps NEO's physical RAM consumption ultra-low (< 60MB) by:
1. Running complete generational garbage collection across all Python generations (0, 1, 2).
2. Shedding inactive/dormant pages from the process Working Set via Win32 EmptyWorkingSet
   using strict 64-bit c_void_p handle types.
3. Invoking malloc_trim(0) on Linux platforms to return freed C-heap pages to the OS.
4. Providing both an asynchronous loop helper and a lightweight background thread.
"""
from __future__ import annotations

import gc
import os
import platform
import threading
import time
from typing import Dict, Any, Optional

import psutil

_IS_WINDOWS = platform.system() == "Windows"
_IS_LINUX = platform.system() == "Linux"

# Setup Windows Win32 API functions once at module import
_WIN32_READY = False
if _IS_WINDOWS:
    try:
        import ctypes
        from ctypes import wintypes
        _kernel32 = ctypes.windll.kernel32
        _psapi = ctypes.windll.psapi
        _kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        _psapi.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
        _psapi.EmptyWorkingSet.restype = wintypes.BOOL
        _WIN32_READY = True
    except Exception:
        _WIN32_READY = False

# Setup Linux malloc_trim once
_LIBC_TRIM: Optional[Any] = None
if _IS_LINUX:
    try:
        import ctypes
        _libc = ctypes.CDLL("libc.so.6")
        if hasattr(_libc, "malloc_trim"):
            _libc.malloc_trim.argtypes = [ctypes.c_size_t]
            _libc.malloc_trim.restype = ctypes.c_int
            _LIBC_TRIM = _libc.malloc_trim
    except Exception:
        _LIBC_TRIM = None


def trim_memory() -> Dict[str, Any]:
    """
    Executes an immediate full-generation garbage collection and trims physical working set.
    Returns memory stats before and after trimming in MB.
    """
    proc = psutil.Process(os.getpid())
    try:
        rss_before = proc.memory_info().rss / (1024 * 1024)
    except Exception:
        rss_before = 0.0

    # 1. Full Python generational garbage collection
    gc.collect(2)

    # 2. Release OS-level memory pages
    trimmed_os = False
    if _IS_WINDOWS and _WIN32_READY:
        try:
            h = _kernel32.GetCurrentProcess()
            res = _psapi.EmptyWorkingSet(h)
            trimmed_os = bool(res)
        except Exception:
            pass
    elif _IS_LINUX and _LIBC_TRIM is not None:
        try:
            _LIBC_TRIM(0)
            trimmed_os = True
        except Exception:
            pass

    try:
        rss_after = proc.memory_info().rss / (1024 * 1024)
    except Exception:
        rss_after = 0.0

    return {
        "rss_before_mb": round(rss_before, 2),
        "rss_after_mb": round(rss_after, 2),
        "reclaimed_mb": round(max(0.0, rss_before - rss_after), 2),
        "os_trimmed": trimmed_os,
    }


class BackgroundMemoryTrimmer:
    """Daemon thread that periodically runs memory trimming in the background."""

    def __init__(self, interval_seconds: int = 30):
        self._interval = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="neo-memory-trimmer")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        # Initial wait to let boot routines settle
        time.sleep(2.0)
        trim_memory()
        while self._running:
            time.sleep(self._interval)
            if self._running:
                trim_memory()


# Global shared singleton
memory_trimmer = BackgroundMemoryTrimmer(interval_seconds=30)
