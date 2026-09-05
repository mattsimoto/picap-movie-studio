from pathlib import Path
from datetime import datetime
import sys

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget
from picamera2 import Picamera2
from picamera2.previews.qt import QPicamera2


PHOTO_DIR = Path.home() / "PiCapMovies" / "camera-test"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)


class PiCapStageOne(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PiCap Movie Studio")
        self.setStyleSheet("background: #161922; color: white;")

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"size": (1280, 720), "format": "RGB888"}
        )
        self.picam2.configure(config)

        # Use the software Qt preview rather than the OpenGL preview.
        # This is more compatible with the Pi 3B+ / 7-inch touchscreen stack.
        self.preview = QPicamera2(self.picam2, width=720, height=300, keep_ar=True)
        self.preview.setMinimumHeight(240)

        self.status = QLabel("Ready")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFixedHeight(30)
        self.status.setStyleSheet("font-size: 18px; font-weight: 700;")

        self.capture_button = QPushButton("TAKE PICTURE")
        self.capture_button.setFixedHeight(64)
        self.capture_button.setStyleSheet(
            "QPushButton {"
            "background: #f2b84b; color: #111; border: none; border-radius: 14px;"
            "font-size: 24px; font-weight: 800; padding: 8px;"
            "}"
            "QPushButton:pressed { background: #d99d2f; }"
        )
        self.capture_button.clicked.connect(self.capture_photo)

        self.exit_button = QPushButton("EXIT")
        self.exit_button.setFixedHeight(64)
        self.exit_button.setStyleSheet(
            "QPushButton {"
            "background: #343947; color: white; border: none; border-radius: 14px;"
            "font-size: 18px; font-weight: 700; padding: 8px;"
            "}"
            "QPushButton:pressed { background: #242833; }"
        )
        self.exit_button.clicked.connect(self.close)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addWidget(self.capture_button, 4)
        button_row.addWidget(self.exit_button, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.status)
        layout.addLayout(button_row)
        self.setLayout(layout)

        self.picam2.start()
        self.showFullScreen()

    def capture_photo(self):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = PHOTO_DIR / f"picap-{timestamp}.jpg"

        self.capture_button.setEnabled(False)
        self.status.setText("Taking picture...")

        try:
            self.picam2.capture_file(str(filename))
            self.status.setText(f"Saved {filename.name}")
        except Exception as exc:
            self.status.setText(f"Camera error: {exc}")
        finally:
            self.capture_button.setEnabled(True)
            QTimer.singleShot(2200, lambda: self.status.setText("Ready"))

    def closeEvent(self, event):
        try:
            self.picam2.stop()
            self.picam2.close()
        finally:
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("PiCap Movie Studio")
    window = PiCapStageOne()
    sys.exit(app.exec_())
