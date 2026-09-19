#!/usr/bin/env python3
from pathlib import Path
import sys
import time

from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QPushButton
from libcamera import controls

from app import PiCapStageFour, FPS_OPTIONS

PROJECT_DIR = Path.home() / "PiCapMovies" / "stage2-test"
MOVIE_PATH = PROJECT_DIR / "movie.avi"
RENDERER = Path(__file__).with_name("mjpeg_avi_test.py")


class PiCapStageFourMJPEG(PiCapStageFour):
    """Stage 4 UI using the pure-Python MJPEG renderer plus Camera Module 3 focus controls."""

    def __init__(self, project_dir=None):
        super().__init__(project_dir=project_dir)
        self.avi_path = self.project_dir / "movie.avi"

        self.focus_locked = False
        self.focus_timeout_ticks = 0
        self.focus_started_at = 0.0
        self.latest_camera_metadata = {}
        self.latest_metadata_time = 0.0
        # Do not call synchronous capture_metadata() from the Qt GUI thread.
        # Picamera2's preview callback supplies metadata without waiting for a frame.
        self.picam2.post_callback = self.cache_camera_metadata
        self.focus_timer = QTimer(self)
        self.focus_timer.setInterval(150)
        self.focus_timer.timeout.connect(self.check_autofocus)

        focus_style = (
            "QPushButton { background: #B7DEFF; color: #14233E; border: 2px solid #73B3F5; "
            "border-radius: 9px; font-size: 14px; font-weight: 800; padding: 3px; }"
            "QPushButton:pressed { background: #85C7FF; }"
            "QPushButton:disabled { background: #E9EFF8; color: #74849A; border-color: #CBD8EA; }"
        )
        self.focus_style = focus_style
        self.focus_locked_style = (
            "QPushButton { background: #FFCA45; color: #14233E; border: 2px solid #E5AD28;"
            "border-radius: 9px; font-size: 14px; font-weight: 800; padding: 3px; }"
            "QPushButton:pressed { background: #E5AD28; }"
            "QPushButton:disabled { background: #E9EFF8; color: #74849A; border-color: #CBD8EA; }"
        )

        self.autofocus_button = QPushButton("AUTOFOCUS ONCE")
        self.autofocus_button.setFixedHeight(38)
        self.autofocus_button.setStyleSheet(focus_style)
        self.autofocus_button.clicked.connect(self.autofocus_once)

        self.focus_lock_button = QPushButton("LOCK FOCUS")
        self.focus_lock_button.setFixedHeight(38)
        self.focus_lock_button.setStyleSheet(focus_style)
        self.focus_lock_button.clicked.connect(self.toggle_focus_lock)

        focus_row = QHBoxLayout()
        focus_row.setSpacing(5)
        focus_row.addWidget(self.autofocus_button, 1)
        focus_row.addWidget(self.focus_lock_button, 1)

        # Insert directly above MAKE MOVIE without rebuilding the Stage 4 layout.
        self.layout().insertLayout(4, focus_row)

        self.focus_supported = "AfMode" in self.picam2.camera_controls
        if not self.focus_supported:
            self.autofocus_button.setEnabled(False)
            self.focus_lock_button.setEnabled(False)
            self.autofocus_button.setText("NO AUTOFOCUS")
            self.focus_lock_button.setText("FIXED FOCUS")
        else:
            # Camera Module 3 starts in continuous AF for an immediately useful preview.
            try:
                self.picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
                self.status.setText("Autofocus ready")
                QTimer.singleShot(1500, self.reset_status)
            except Exception as exc:
                self.status.setText(f"Focus setup error: {exc}")

    def cache_camera_metadata(self, request):
        """Cache metadata from a frame that the preview is already processing."""
        try:
            self.latest_camera_metadata = request.get_metadata()
            self.latest_metadata_time = time.monotonic()
        except Exception:
            pass

    def autofocus_once(self):
        if not self.focus_supported or self.rendering or self.playing or self.shutting_down:
            return
        try:
            self.focus_locked = False
            self.focus_lock_button.setText("LOCK FOCUS")
            self.focus_lock_button.setStyleSheet(self.focus_style)
            self.autofocus_button.setText("FOCUSING...")
            self.autofocus_button.setEnabled(False)
            self.focus_timeout_ticks = 0
            self.status.setText("Finding focus...")
            self.focus_started_at = time.monotonic()
            self.picam2.set_controls({"AfMode": controls.AfModeEnum.Auto})
            self.picam2.set_controls({"AfTrigger": controls.AfTriggerEnum.Start})
            self.focus_timer.start()
        except Exception as exc:
            self.autofocus_button.setText("AUTOFOCUS ONCE")
            self.autofocus_button.setEnabled(True)
            self.status.setText(f"Focus error: {exc}")

    def check_autofocus(self):
        self.focus_timeout_ticks += 1
        try:
            # Reading cached metadata never blocks the Qt event loop.
            # Ignore the previous autofocus state from before the new cycle.
            metadata = self.latest_camera_metadata if self.latest_metadata_time > self.focus_started_at else {}
            af_state = metadata.get("AfState")
            # libcamera states: Idle, Scanning, Focused, Failed.
            if af_state == controls.AfStateEnum.Focused:
                self.focus_timer.stop()
                self.autofocus_button.setText("AUTOFOCUS ONCE")
                self.autofocus_button.setEnabled(True)
                self.status.setText("Focus found — tap LOCK FOCUS")
                return
            if af_state == controls.AfStateEnum.Failed:
                self.focus_timer.stop()
                self.autofocus_button.setText("AUTOFOCUS ONCE")
                self.autofocus_button.setEnabled(True)
                self.status.setText("Could not focus — try again")
                return
        except Exception as exc:
            self.focus_timer.stop()
            self.autofocus_button.setText("AUTOFOCUS ONCE")
            self.autofocus_button.setEnabled(True)
            self.status.setText(f"Focus error: {exc}")
            return

        # Roughly 6 seconds at 150 ms per check.
        if self.focus_timeout_ticks >= 40:
            self.focus_timer.stop()
            self.autofocus_button.setText("AUTOFOCUS ONCE")
            self.autofocus_button.setEnabled(True)
            self.status.setText("Focus timed out — try again")

    def toggle_focus_lock(self):
        if not self.focus_supported or self.rendering or self.playing or self.shutting_down:
            return
        try:
            if not self.focus_locked:
                # Read the latest preview-frame metadata without waiting for a new frame.
                lens_position = self.latest_camera_metadata.get("LensPosition")
                if lens_position is None:
                    self.status.setText("Lens position unavailable")
                    return
                self.picam2.set_controls({
                    "AfMode": controls.AfModeEnum.Manual,
                    "LensPosition": float(lens_position),
                })
                self.focus_locked = True
                self.focus_lock_button.setText("FOCUS LOCKED")
                self.focus_lock_button.setStyleSheet(self.focus_locked_style)
                self.status.setText("Focus locked for animation")
            else:
                self.picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
                self.focus_locked = False
                self.focus_lock_button.setText("LOCK FOCUS")
                self.focus_lock_button.setStyleSheet(self.focus_style)
                self.status.setText("Continuous autofocus on")
            QTimer.singleShot(1800, self.reset_status)
        except Exception as exc:
            self.status.setText(f"Focus lock error: {exc}")

    def refresh_buttons(self):
        super().refresh_buttons()
        if hasattr(self, "autofocus_button") and getattr(self, "focus_supported", False):
            busy = self.rendering or self.playing or self.shutting_down or self.pending_filename is not None
            if not self.focus_timer.isActive():
                self.autofocus_button.setEnabled(not busy)
            self.focus_lock_button.setEnabled(not busy)

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
        self.render_process.start(sys.executable, [str(RENDERER), str(fps), str(self.project_dir)])

    def render_finished(self, exit_code, _exit_status):
        success = exit_code == 0 and self.avi_path.exists() and self.avi_path.stat().st_size > 0
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
            size_mb = self.avi_path.stat().st_size / (1024 * 1024)
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

    def closeEvent(self, event):
        self.focus_timer.stop()
        self.picam2.post_callback = None
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("PiCap Movie Studio")
    window = PiCapStageFourMJPEG()
    sys.exit(app.exec_())
