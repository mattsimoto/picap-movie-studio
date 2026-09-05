from pathlib import Path
import re
import sys

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget
from picamera2 import Picamera2
from picamera2.previews.qt import QPicamera2


PROJECT_DIR = Path.home() / "PiCapMovies" / "stage2-test"
FRAMES_DIR = PROJECT_DIR / "frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
FRAME_PATTERN = re.compile(r"^frame(\d{4})\.jpg$")


class PiCapStageTwo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PiCap Movie Studio")
        self.setStyleSheet("background: #161922; color: white;")
        self.pending_filename = None
        self.pending_frame_number = None
        self.frame_count = self.find_last_frame_number()
        self.shutting_down = False

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"size": (1280, 720), "format": "RGB888"}
        )
        self.picam2.configure(config)

        self.preview = QPicamera2(self.picam2, width=720, height=300, keep_ar=True)
        self.preview.setMinimumHeight(230)
        self.preview.done_signal.connect(self.capture_done)

        self.frame_label = QLabel()
        self.frame_label.setAlignment(Qt.AlignCenter)
        self.frame_label.setFixedHeight(32)
        self.frame_label.setStyleSheet("font-size: 22px; font-weight: 800;")
        self.update_frame_label()

        self.status = QLabel("Ready")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFixedHeight(24)
        self.status.setStyleSheet("font-size: 15px; font-weight: 600; color: #d8dbe5;")

        self.capture_button = QPushButton("TAKE PICTURE")
        self.capture_button.setFixedHeight(62)
        self.capture_button.setStyleSheet(
            "QPushButton {"
            "background: #f2b84b; color: #111; border: none; border-radius: 14px;"
            "font-size: 22px; font-weight: 800; padding: 6px;"
            "}"
            "QPushButton:pressed { background: #d99d2f; }"
            "QPushButton:disabled { background: #8a7a58; color: #ddd; }"
        )
        self.capture_button.clicked.connect(self.capture_photo)

        self.oops_button = QPushButton("OOPS")
        self.oops_button.setFixedHeight(62)
        self.oops_button.setStyleSheet(
            "QPushButton {"
            "background: #9b3d48; color: white; border: none; border-radius: 14px;"
            "font-size: 18px; font-weight: 800; padding: 6px;"
            "}"
            "QPushButton:pressed { background: #7d3039; }"
            "QPushButton:disabled { background: #50373b; color: #aaa; }"
        )
        self.oops_button.clicked.connect(self.delete_last_frame)

        self.exit_button = QPushButton("EXIT")
        self.exit_button.setFixedHeight(62)
        self.exit_button.setStyleSheet(
            "QPushButton {"
            "background: #343947; color: white; border: none; border-radius: 14px;"
            "font-size: 17px; font-weight: 700; padding: 6px;"
            "}"
            "QPushButton:pressed { background: #242833; }"
        )
        self.exit_button.clicked.connect(self.begin_shutdown)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addWidget(self.capture_button, 5)
        button_row.addWidget(self.oops_button, 2)
        button_row.addWidget(self.exit_button, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.frame_label)
        layout.addWidget(self.status)
        layout.addLayout(button_row)
        self.setLayout(layout)

        self.refresh_buttons()
        self.picam2.start()
        self.showFullScreen()

    def find_last_frame_number(self):
        """Return the highest sequential frame number currently saved."""
        highest = 0
        for path in FRAMES_DIR.glob("frame*.jpg"):
            match = FRAME_PATTERN.match(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest

    def update_frame_label(self):
        self.frame_label.setText(f"FRAMES: {self.frame_count}")

    def refresh_buttons(self):
        busy = self.pending_filename is not None or self.shutting_down
        self.capture_button.setEnabled(not busy)
        self.oops_button.setEnabled((self.frame_count > 0) and not busy)
        self.exit_button.setEnabled(not self.shutting_down)

    def capture_photo(self):
        """Save the next stop-motion frame without blocking the touchscreen UI."""
        if self.pending_filename is not None or self.shutting_down:
            return

        next_number = self.frame_count + 1
        self.pending_frame_number = next_number
        self.pending_filename = FRAMES_DIR / f"frame{next_number:04d}.jpg"
        self.status.setText(f"Taking frame {next_number}...")
        self.refresh_buttons()

        try:
            self.picam2.capture_file(
                str(self.pending_filename),
                wait=False,
                signal_function=self.preview.signal_done,
            )
        except Exception as exc:
            self.pending_filename = None
            self.pending_frame_number = None
            self.status.setText(f"Camera error: {exc}")
            self.refresh_buttons()

    def capture_done(self, job):
        """Complete the asynchronous capture and update the frame counter."""
        if self.shutting_down:
            return

        try:
            self.picam2.wait(job)
            if self.pending_frame_number is not None:
                self.frame_count = self.pending_frame_number
                self.update_frame_label()
                self.status.setText(f"Saved frame {self.frame_count}")
            else:
                self.status.setText("Frame saved")
        except Exception as exc:
            self.status.setText(f"Camera error: {exc}")
        finally:
            self.pending_filename = None
            self.pending_frame_number = None
            self.refresh_buttons()
            QTimer.singleShot(1300, self.reset_status)

    def delete_last_frame(self):
        """Delete only the most recent frame and roll the counter back by one."""
        if self.pending_filename is not None or self.frame_count <= 0 or self.shutting_down:
            return

        filename = FRAMES_DIR / f"frame{self.frame_count:04d}.jpg"
        try:
            if filename.exists():
                filename.unlink()
                deleted_number = self.frame_count
                self.frame_count -= 1
                self.update_frame_label()
                self.status.setText(f"Oops! Deleted frame {deleted_number}")
            else:
                self.frame_count = self.find_last_frame_number()
                self.update_frame_label()
                self.status.setText("Last frame was already missing")
        except Exception as exc:
            self.status.setText(f"Delete error: {exc}")
        finally:
            self.refresh_buttons()
            QTimer.singleShot(1500, self.reset_status)

    def reset_status(self):
        if self.pending_filename is None and not self.shutting_down:
            self.status.setText("Ready")

    def begin_shutdown(self):
        """Stop camera activity first, then close the window on the next Qt tick."""
        if self.shutting_down:
            return
        self.shutting_down = True
        self.status.setText("Closing...")
        self.refresh_buttons()
        QTimer.singleShot(50, self.close)

    def closeEvent(self, event):
        self.shutting_down = True
        try:
            # Disconnect the Qt completion callback before the camera notifier is torn down.
            try:
                self.preview.done_signal.disconnect(self.capture_done)
            except Exception:
                pass

            try:
                self.picam2.stop()
            except Exception:
                pass

            # Let the preview widget release its notifier before closing Picamera2.
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
    window = PiCapStageTwo()
    sys.exit(app.exec_())
