from pathlib import Path
import re
import shutil
import sys

from PyQt5.QtCore import QProcess, QSize, QTimer, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)
from picamera2 import Picamera2
from picamera2.previews.qt import QPicamera2


PROJECT_DIR = Path.home() / "PiCapMovies" / "stage2-test"
FRAMES_DIR = PROJECT_DIR / "frames"
MOVIE_PATH = PROJECT_DIR / "movie.mp4"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
FRAME_PATTERN = re.compile(r"^frame(\d{4})\.jpg$")
FPS_OPTIONS = [6, 10, 15]
ONION_LEVELS = [("LOW", 0.22), ("MED", 0.38), ("HIGH", 0.55)]


class PiCapStageFour(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PiCap Movie Studio")
        self.setStyleSheet("background: #161922; color: white;")

        self.pending_filename = None
        self.pending_frame_number = None
        self.frame_count = self.find_last_frame_number()
        self.shutting_down = False
        self.onion_enabled = False
        self.onion_level_index = 1
        self.playing = False
        self.playback_index = 0
        self.fps_index = 1
        self.rendering = False
        self.render_process = None

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"size": (1280, 720), "format": "RGB888"}
        )
        self.picam2.configure(config)

        self.preview = QPicamera2(self.picam2, width=720, height=215, keep_ar=True)
        self.preview.setMinimumHeight(170)
        self.preview.done_signal.connect(self.capture_done)

        self.onion_overlay = QLabel()
        self.onion_overlay.setAlignment(Qt.AlignCenter)
        self.onion_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.onion_overlay.setStyleSheet("background: transparent;")
        self.onion_effect = QGraphicsOpacityEffect(self.onion_overlay)
        self.onion_effect.setOpacity(ONION_LEVELS[self.onion_level_index][1])
        self.onion_overlay.setGraphicsEffect(self.onion_effect)
        self.onion_overlay.hide()

        self.playback_view = QLabel()
        self.playback_view.setAlignment(Qt.AlignCenter)
        self.playback_view.setStyleSheet("background: black;")
        self.playback_view.hide()

        self.camera_stack = QWidget()
        stack = QStackedLayout(self.camera_stack)
        stack.setStackingMode(QStackedLayout.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self.preview)
        stack.addWidget(self.onion_overlay)
        stack.addWidget(self.playback_view)

        self.frame_label = QLabel()
        self.frame_label.setAlignment(Qt.AlignCenter)
        self.frame_label.setFixedHeight(25)
        self.frame_label.setStyleSheet("font-size: 19px; font-weight: 800;")
        self.update_frame_label()

        self.status = QLabel("Ready")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFixedHeight(18)
        self.status.setStyleSheet("font-size: 12px; font-weight: 600; color: #d8dbe5;")

        tool_style = (
            "QPushButton { background: #343947; color: white; border: 2px solid #596174; "
            "border-radius: 10px; font-size: 14px; font-weight: 800; padding: 4px; }"
            "QPushButton:pressed { background: #596174; }"
            "QPushButton:disabled { background: #252832; color: #777; border-color: #333744; }"
        )

        self.onion_button = QPushButton("ONION OFF")
        self.onion_button.setFixedHeight(44)
        self.onion_button.setStyleSheet(tool_style)
        self.onion_button.clicked.connect(self.toggle_onion)

        self.strength_button = QPushButton("GHOST MED")
        self.strength_button.setFixedHeight(44)
        self.strength_button.setStyleSheet(tool_style)
        self.strength_button.clicked.connect(self.cycle_onion_strength)

        self.fps_button = QPushButton("10 FPS")
        self.fps_button.setFixedHeight(44)
        self.fps_button.setStyleSheet(tool_style)
        self.fps_button.clicked.connect(self.cycle_fps)

        self.play_button = QPushButton("PLAY")
        self.play_button.setFixedHeight(44)
        self.play_button.setStyleSheet(tool_style)
        self.play_button.clicked.connect(self.toggle_playback)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(5)
        tools_row.addWidget(self.onion_button, 1)
        tools_row.addWidget(self.strength_button, 1)
        tools_row.addWidget(self.fps_button, 1)
        tools_row.addWidget(self.play_button, 1)

        self.render_button = QPushButton("MAKE MOVIE")
        self.render_button.setFixedHeight(48)
        self.render_button.setStyleSheet(
            "QPushButton { background: #527a55; color: white; border: none; border-radius: 11px;"
            "font-size: 18px; font-weight: 800; padding: 5px; }"
            "QPushButton:pressed { background: #3f6042; }"
            "QPushButton:disabled { background: #354737; color: #999; }"
        )
        self.render_button.clicked.connect(self.render_movie)

        self.capture_button = QPushButton("TAKE PICTURE")
        self.capture_button.setFixedHeight(58)
        self.capture_button.setStyleSheet(
            "QPushButton { background: #f2b84b; color: #111; border: none; border-radius: 12px;"
            "font-size: 21px; font-weight: 800; padding: 5px; }"
            "QPushButton:pressed { background: #d99d2f; }"
            "QPushButton:disabled { background: #8a7a58; color: #ddd; }"
        )
        self.capture_button.clicked.connect(self.capture_photo)

        self.oops_button = QPushButton("OOPS")
        self.oops_button.setFixedHeight(58)
        self.oops_button.setStyleSheet(
            "QPushButton { background: #9b3d48; color: white; border: none; border-radius: 12px;"
            "font-size: 18px; font-weight: 800; padding: 5px; }"
            "QPushButton:pressed { background: #7d3039; }"
            "QPushButton:disabled { background: #50373b; color: #aaa; }"
        )
        self.oops_button.clicked.connect(self.delete_last_frame)

        self.exit_button = QPushButton("EXIT")
        self.exit_button.setFixedHeight(58)
        self.exit_button.setStyleSheet(
            "QPushButton { background: #343947; color: white; border: none; border-radius: 12px;"
            "font-size: 17px; font-weight: 700; padding: 5px; }"
            "QPushButton:pressed { background: #242833; }"
        )
        self.exit_button.clicked.connect(self.begin_shutdown)

        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        button_row.addWidget(self.capture_button, 5)
        button_row.addWidget(self.oops_button, 2)
        button_row.addWidget(self.exit_button, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(3)
        layout.addWidget(self.camera_stack, 1)
        layout.addWidget(self.frame_label)
        layout.addWidget(self.status)
        layout.addLayout(tools_row)
        layout.addWidget(self.render_button)
        layout.addLayout(button_row)
        self.setLayout(layout)

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self.advance_playback)

        self.refresh_buttons()
        self.picam2.start()
        self.showFullScreen()
        QTimer.singleShot(250, self.refresh_onion_overlay)

    def find_last_frame_number(self):
        highest = 0
        for path in FRAMES_DIR.glob("frame*.jpg"):
            match = FRAME_PATTERN.match(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest

    def frame_path(self, number):
        return FRAMES_DIR / f"frame{number:04d}.jpg"

    def update_frame_label(self):
        self.frame_label.setText(f"FRAMES: {self.frame_count}")

    def refresh_buttons(self):
        busy = (
            self.pending_filename is not None
            or self.shutting_down
            or self.playing
            or self.rendering
        )
        self.capture_button.setEnabled(not busy)
        self.oops_button.setEnabled((self.frame_count > 0) and not busy)
        self.exit_button.setEnabled(not self.shutting_down and not self.rendering)
        self.onion_button.setEnabled(not self.playing and not self.shutting_down and not self.rendering)
        self.strength_button.setEnabled(not self.playing and not self.shutting_down and not self.rendering)
        self.fps_button.setEnabled(not self.shutting_down and not self.rendering)
        self.play_button.setEnabled((self.frame_count > 0) and not self.shutting_down and not self.rendering)
        self.render_button.setEnabled((self.frame_count > 0) and not busy)

    def capture_photo(self):
        if self.pending_filename is not None or self.shutting_down or self.playing or self.rendering:
            return
        next_number = self.frame_count + 1
        self.pending_frame_number = next_number
        self.pending_filename = self.frame_path(next_number)
        self.status.setText(f"Taking frame {next_number}...")
        self.refresh_buttons()
        try:
            self.picam2.capture_file(
                str(self.pending_filename), wait=False, signal_function=self.preview.signal_done
            )
        except Exception as exc:
            self.pending_filename = None
            self.pending_frame_number = None
            self.status.setText(f"Camera error: {exc}")
            self.refresh_buttons()

    def capture_done(self, job):
        if self.shutting_down:
            return
        try:
            self.picam2.wait(job)
            if self.pending_frame_number is not None:
                self.frame_count = self.pending_frame_number
                self.update_frame_label()
                self.status.setText(f"Saved frame {self.frame_count}")
                self.refresh_onion_overlay()
        except Exception as exc:
            self.status.setText(f"Camera error: {exc}")
        finally:
            self.pending_filename = None
            self.pending_frame_number = None
            self.refresh_buttons()
            QTimer.singleShot(1100, self.reset_status)

    def delete_last_frame(self):
        if self.pending_filename is not None or self.frame_count <= 0 or self.shutting_down or self.playing or self.rendering:
            return
        filename = self.frame_path(self.frame_count)
        try:
            if filename.exists():
                filename.unlink()
                deleted_number = self.frame_count
                self.frame_count -= 1
                self.update_frame_label()
                self.status.setText(f"Deleted frame {deleted_number}")
                self.refresh_onion_overlay()
            else:
                self.frame_count = self.find_last_frame_number()
                self.update_frame_label()
                self.refresh_onion_overlay()
        except Exception as exc:
            self.status.setText(f"Delete error: {exc}")
        finally:
            self.refresh_buttons()
            QTimer.singleShot(1200, self.reset_status)

    def toggle_onion(self):
        self.onion_enabled = not self.onion_enabled
        self.onion_button.setText("ONION ON" if self.onion_enabled else "ONION OFF")
        self.refresh_onion_overlay()

    def cycle_onion_strength(self):
        self.onion_level_index = (self.onion_level_index + 1) % len(ONION_LEVELS)
        label, opacity = ONION_LEVELS[self.onion_level_index]
        self.strength_button.setText(f"GHOST {label}")
        self.onion_effect.setOpacity(opacity)
        if self.onion_enabled:
            self.refresh_onion_overlay()

    def preview_target_size(self):
        return QSize(max(1, self.preview.width()), max(1, self.preview.height()))

    def refresh_onion_overlay(self):
        if not self.onion_enabled or self.frame_count <= 0 or self.playing:
            self.onion_overlay.hide()
            return
        path = self.frame_path(self.frame_count)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.onion_overlay.hide()
            return
        scaled = pixmap.scaled(self.preview_target_size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.onion_overlay.setPixmap(scaled)
        self.onion_overlay.show()
        self.onion_overlay.raise_()

    def cycle_fps(self):
        self.fps_index = (self.fps_index + 1) % len(FPS_OPTIONS)
        fps = FPS_OPTIONS[self.fps_index]
        self.fps_button.setText(f"{fps} FPS")
        if self.playing:
            self.playback_timer.setInterval(max(1, round(1000 / fps)))

    def toggle_playback(self):
        if self.playing:
            self.stop_playback()
        else:
            self.start_playback()

    def start_playback(self):
        if self.frame_count <= 0 or self.shutting_down or self.rendering:
            return
        self.playing = True
        self.playback_index = 1
        self.onion_overlay.hide()
        self.playback_view.show()
        self.playback_view.raise_()
        self.play_button.setText("STOP")
        self.status.setText("Playing...")
        self.refresh_buttons()
        self.show_playback_frame()
        fps = FPS_OPTIONS[self.fps_index]
        self.playback_timer.start(max(1, round(1000 / fps)))

    def advance_playback(self):
        if not self.playing:
            return
        self.playback_index += 1
        if self.playback_index > self.frame_count:
            self.stop_playback()
            return
        self.show_playback_frame()

    def show_playback_frame(self):
        pixmap = QPixmap(str(self.frame_path(self.playback_index)))
        if not pixmap.isNull():
            target = QSize(max(1, self.playback_view.width()), max(1, self.playback_view.height()))
            self.playback_view.setPixmap(
                pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def stop_playback(self):
        self.playback_timer.stop()
        self.playing = False
        self.playback_view.hide()
        self.play_button.setText("PLAY")
        self.status.setText("Ready")
        self.refresh_onion_overlay()
        self.refresh_buttons()

    def render_movie(self):
        if self.frame_count <= 0 or self.rendering or self.playing or self.shutting_down:
            return

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.status.setText("FFmpeg missing")
            return

        self.rendering = True
        self.onion_overlay.hide()
        self.render_button.setText("MAKING MOVIE...")
        self.status.setText("Making movie...")
        self.refresh_buttons()

        fps = FPS_OPTIONS[self.fps_index]
        input_pattern = str(FRAMES_DIR / "frame%04d.jpg")

        args = [
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-start_number",
            "1",
            "-i",
            input_pattern,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(MOVIE_PATH),
        ]

        self.render_process = QProcess(self)
        self.render_process.finished.connect(self.render_finished)
        self.render_process.errorOccurred.connect(self.render_error)
        self.render_process.start(ffmpeg, args)

    def render_finished(self, exit_code, exit_status):
        success = exit_code == 0 and MOVIE_PATH.exists()
        self.rendering = False
        self.render_process = None
        self.render_button.setText("MAKE MOVIE")
        if success:
            self.status.setText("Movie saved!")
        else:
            self.status.setText("Movie failed")
        self.refresh_onion_overlay()
        self.refresh_buttons()
        QTimer.singleShot(2200, self.reset_status)

    def render_error(self, _error):
        if not self.rendering:
            return
        self.rendering = False
        self.render_process = None
        self.render_button.setText("MAKE MOVIE")
        self.status.setText("Movie error")
        self.refresh_onion_overlay()
        self.refresh_buttons()
        QTimer.singleShot(2200, self.reset_status)

    def reset_status(self):
        if (
            self.pending_filename is None
            and not self.shutting_down
            and not self.playing
            and not self.rendering
        ):
            self.status.setText("Ready")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.refresh_onion_overlay)
        if self.playing:
            QTimer.singleShot(0, self.show_playback_frame)

    def begin_shutdown(self):
        if self.shutting_down or self.rendering:
            return
        self.shutting_down = True
        self.playback_timer.stop()
        self.status.setText("Closing...")
        self.refresh_buttons()
        QTimer.singleShot(50, self.close)

    def closeEvent(self, event):
        self.shutting_down = True
        self.playback_timer.stop()
        if self.render_process is not None:
            try:
                self.render_process.kill()
            except Exception:
                pass
        try:
            try:
                self.preview.done_signal.disconnect(self.capture_done)
            except Exception:
                pass
            try:
                self.picam2.stop()
            except Exception:
                pass
            try:
                self.preview.hide()
                self.preview.deleteLater()
            except Exception:
                pass
            QTimer.singleShot(0, self.finish_camera_close)
            event.accept()
        except Exception:
            event.accept()

    def finish_camera_close(self):
        try:
            self.picam2.close()
        except Exception:
            pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("PiCap Movie Studio")
    window = PiCapStageFour()
    sys.exit(app.exec_())
