"""Small cross-process file locks for local single-machine coordination."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import BinaryIO


class LockTimeoutError(TimeoutError):
    """Raised when a local coordination lock cannot be acquired in time."""


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


class CrossProcessFileLock:
    """Serialize one critical section across threads and local processes.

    The operating system releases the byte-range lock when the process exits,
    so a crashed worker cannot leave a permanent lock behind.
    """

    def __init__(
        self,
        path: os.PathLike[str] | str,
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.1,
    ):
        self.path = Path(path)
        self.timeout = max(0.0, timeout)
        self.poll_interval = max(0.01, poll_interval)
        self._thread_lock = _thread_lock(self.path)
        self._handle: BinaryIO | None = None
        self._thread_acquired = False

    def acquire(self) -> None:
        deadline = time.monotonic() + self.timeout
        if not self._thread_lock.acquire(timeout=self.timeout):
            raise LockTimeoutError(f"timed out waiting for lock: {self.path}")
        self._thread_acquired = True

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a+b")
            self._ensure_lock_byte()
            while True:
                try:
                    self._lock_file()
                    return
                except (BlockingIOError, OSError):
                    if time.monotonic() >= deadline:
                        raise LockTimeoutError(
                            f"timed out waiting for lock: {self.path}"
                        )
                    time.sleep(self.poll_interval)
        except Exception:
            self._close_handle()
            self._release_thread_lock()
            raise

    def release(self) -> None:
        try:
            if self._handle is not None:
                self._unlock_file()
        finally:
            self._close_handle()
            self._release_thread_lock()

    def _ensure_lock_byte(self) -> None:
        assert self._handle is not None
        self._handle.seek(0, os.SEEK_END)
        if self._handle.tell() == 0:
            self._handle.write(b"\0")
            self._handle.flush()
        self._handle.seek(0)

    def _lock_file(self) -> None:
        assert self._handle is not None
        if os.name == "nt":
            import msvcrt

            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(self) -> None:
        assert self._handle is not None
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass

    def _close_handle(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def _release_thread_lock(self) -> None:
        if self._thread_acquired:
            self._thread_lock.release()
            self._thread_acquired = False

    def __enter__(self) -> "CrossProcessFileLock":
        self.acquire()
        return self

    def __exit__(self, *_args) -> None:
        self.release()
