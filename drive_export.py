"""Non-blocking, local-first Google Drive uploads for PiCap Movie Studio.

The parent's rclone Google Drive remote is named 'picapdrive'. Tokens and
Google credentials are managed by rclone, never written by PiCap.
"""
import json
import shutil
from collections import deque
from pathlib import Path

from PyQt5.QtCore import QObject, QProcess, pyqtSignal


BASE_DIR = Path.home() / "PiCapMovies"
SETTINGS_FILE = BASE_DIR / "drive-export.json"
REMOTE = "picapdrive"
DEFAULT_FOLDER = "PiCap Movies"


def drive_folder():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        folder = data.get("folder", "")
        if isinstance(folder, str) and is_valid_folder(folder):
            return folder.strip()
    except (OSError, ValueError, TypeError):
        pass
    return DEFAULT_FOLDER


def is_valid_folder(folder):
    return (
        isinstance(folder, str)
        and 1 <= len(folder.strip()) <= 100
        and folder.strip() not in (".", "..")
        and not any(ch in folder for ch in ("/", "\\", ":", "\n", "\r"))
        and not folder.startswith(".")
    )


def save_drive_folder(folder):
    if not is_valid_folder(folder):
        raise ValueError("Use a folder name of 1-100 characters, without /, \\, or :.")
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps({"folder": folder.strip()}, indent=2), encoding="utf-8"
    )


def video_for_project(project_dir):
    project_dir = Path(project_dir)
    # Prefer the most recently completed render. An old MP4 may coexist with a
    # newer AVI (or vice versa) after scenes are added to an existing project.
    candidates = []
    for name in ("movie.mp4", "movie.avi"):
        video = project_dir / name
        try:
            stat = video.stat()
        except OSError:
            continue
        if video.is_file() and stat.st_size > 0:
            candidates.append((stat.st_mtime_ns, video))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


class DriveExporter(QObject):
    """Queue Drive transfers without blocking touchscreen or camera activity."""

    status_changed = pyqtSignal(str)
    upload_complete = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.waiting = deque()
        self.current = None
        self.process = None
        self.last_output = ""

    def queue_project(self, project_dir):
        project_dir = Path(project_dir)
        video = video_for_project(project_dir)
        if video is None:
            self.status_changed.emit("Drive: Make this movie before uploading it.")
            return False
        if project_dir == self.current or project_dir in self.waiting:
            self.status_changed.emit("Drive: This movie is already queued for upload.")
            return True
        self.waiting.append(project_dir)
        self.status_changed.emit("Drive: Movie queued for upload.")
        self._start_next()
        return True

    def _start_next(self):
        if self.process is not None or not self.waiting:
            return
        if not shutil.which("rclone"):
            self.waiting.clear()
            self.status_changed.emit(
                "Drive: Install rclone and connect the picapdrive remote first."
            )
            return

        self.current = self.waiting.popleft()
        video = video_for_project(self.current)
        if video is None:
            self.status_changed.emit("Drive: Movie file missing. Make the movie again.")
            self.current = None
            self._start_next()
            return

        folder = drive_folder()
        destination = f"{REMOTE}:{folder}/{self.current.name}{video.suffix}"
        self.last_output = ""
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.status_changed.emit(f"Drive: Uploading {self.current.name}...")
        # No shell is involved: spaces in the destination folder are safe.
        # copyto never deletes local files or any other Drive files.
        self.process.start(
            "rclone",
            [
                "copyto", str(video), destination,
                "--retries", "2", "--low-level-retries", "2",
            ],
        )

    def _read_output(self):
        if self.process is None:
            return
        chunk = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        self.last_output = (self.last_output + chunk)[-1200:]

    def _error(self, _error):
        if self.process is None:
            return
        # FailedToStart may not emit finished. Other failures normally do.
        if self.process.error() == QProcess.FailedToStart:
            self._finish(False)

    def _finished(self, code, status):
        self._read_output()
        self._finish(code == 0 and status == QProcess.NormalExit)

    def _finish(self, success):
        if self.process is None:
            return
        old_process = self.process
        old_project = self.current
        self.process = None
        self.current = None
        old_process.deleteLater()
        if success:
            self.status_changed.emit(
                f"Drive: Uploaded {old_project.name} to {drive_folder()}."
            )
            self.upload_complete.emit(str(old_project))
        else:
            lines = self.last_output.strip().splitlines()
            detail = lines[-1].strip() if lines else "Connection or authorization failed."
            self.status_changed.emit(
                f"Drive: Upload failed for {old_project.name}: {detail[:110]}"
            )
        self._start_next()
