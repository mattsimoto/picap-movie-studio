#!/usr/bin/env python3
from pathlib import Path
import sys

from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import QApplication

from app import PiCapStageFour, FPS_OPTIONS

PROJECT_DIR = Path.home() / "PiCapMovies" / "stage2-test"
MOVIE_PATH = PROJECT_DIR / "movie.avi"
RENDERER = Path(__file__).with_name("mjpeg_avi_test.py")


class PiCapStageFourMJPEG(PiCapStageFour):
    """Stage 4 UI using the proven pure-Python MJPEG AVI renderer."""

    def render_movie(self):
        if self.frame_count <= 0 or self.rendering or self.playing or self.shutting_down:
            return

        if not RENDERER.exists():
            self.status.setText("Renderer missing")
            return

        self.rendering = True
        self.onion_overlay.hide()
        self.render_button.setText("MAKING MOVIE...")
        self.status.setText("Making movie...")
        self.refresh_buttons()

        fps = FPS_OPTIONS[self.fps_index]
        self.render_process = QProcess(self)
        self.render_process.setProcessChannelMode(QProcess.MergedChannels)
        self.render_process.finished.connect(self.render_finished)
        self.render_process.errorOccurred.connect(self.render_error)
        self.render_process.start(sys.executable, [str(RENDERER), str(fps)])

    def render_finished(self, exit_code, _exit_status):
        success = exit_code == 0 and MOVIE_PATH.exists() and MOVIE_PATH.stat().st_size > 0
        details = ""
        if self.render_process is not None:
            try:
                details = bytes(self.render_process.readAllStandardOutput()).decode("utf-8", errors="replace")
            except Exception:
                details = ""

        self.rendering = False
        self.render_process = None
        self.render_button.setText("MAKE MOVIE")

        if success:
            size_mb = MOVIE_PATH.stat().st_size / (1024 * 1024)
            self.status.setText(f"Movie saved! {size_mb:.1f} MB")
        else:
            last_line = details.strip().splitlines()[-1] if details.strip() else "Movie failed"
            self.status.setText(last_line[:70])

        self.refresh_onion_overlay()
        self.refresh_buttons()
        QTimer.singleShot(3000, self.reset_status)

    def render_error(self, _error):
        if not self.rendering:
            return
        self.rendering = False
        self.render_process = None
        self.render_button.setText("MAKE MOVIE")
        self.status.setText("Movie renderer error")
        self.refresh_onion_overlay()
        self.refresh_buttons()
        QTimer.singleShot(3000, self.reset_status)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("PiCap Movie Studio")
    window = PiCapStageFourMJPEG()
    sys.exit(app.exec_())
