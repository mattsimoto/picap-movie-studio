"""PiCap voice-over editor: one narration take, safe retakes, and MP4 export.

Uses ALSA arecord/aplay and FFmpeg as subprocesses to keep the Qt touchscreen
responsive on Raspberry Pi 3B+. All audio and images stay in the movie project.
"""
import json
import math
import os
import re
import shutil
import tempfile
import wave
from pathlib import Path

from PyQt5.QtCore import QElapsedTimer, QProcess, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImageReader, QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


def capture_device():
    """Use an attached ALSA capture device, preferring USB over onboard audio.

    PICAP_MIC_DEVICE overrides detection for unusual microphones.
    ALSA's plughw device supports conversion to the WAV recording format.
    """
    override = os.environ.get("PICAP_MIC_DEVICE", "").strip()
    if override:
        return override
    try:
        pcm = Path("/proc/asound/pcm").read_text(encoding="utf-8")
        choices = []
        for line in pcm.splitlines():
            match = re.match(r"\\s*(\\d+)-(\\d+):\\s*(.*)", line)
            if match and re.search(r"capture\\s+\\d+", line, re.IGNORECASE):
                card, device, description = match.groups()
                choices.append(("usb" not in description.lower(), card, device))
        if choices:
            choices.sort()
            _, card, device = choices[0]
            return f"plughw:{int(card)},{int(device)}"
    except (OSError, UnicodeError):
        pass
    return "default"


class VoiceDubPage(QWidget):
    back_requested = pyqtSignal()
    movie_saved = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.frames = []
        self.fps = 10
        self.position = -1
        self.elapsed = QElapsedTimer()
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(60)
        self.preview_timer.timeout.connect(self.tick_preview)
        self.recorder = None
        self.audio_player = None
        self.encoder = None
        self.render_staging = None
        self.canceling = False
        self.last_error = ""
        self.recorded_frame_count = 0

        self.title = QLabel("ADD VOICES")
        self.title.setFixedHeight(28)
        self.title.setStyleSheet("font-size:22px;font-weight:900;color:#14233E;")

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(1, 160)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setStyleSheet(
            "background:#091526;color:white;border-radius:10px;"
        )
        self.counter = QLabel("00:00 / 00:00")
        self.counter.setFixedHeight(21)
        self.counter.setStyleSheet("font-size:14px;font-weight:800;color:#14233E;")
        self.status = QLabel("Choose a movie to add voices.")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(38)
        self.status.setStyleSheet("font-size:13px;font-weight:700;color:#34527B;")

        camera_side = QVBoxLayout()
        camera_side.setContentsMargins(0, 0, 0, 0)
        camera_side.setSpacing(3)
        camera_side.addWidget(self.title)
        camera_side.addWidget(self.preview, 1)
        camera_side.addWidget(self.counter)
        camera_side.addWidget(self.status)

        rail = QWidget()
        rail.setObjectName("voiceRail")
        rail.setFixedWidth(184)
        rail.setStyleSheet(
            "QWidget#voiceRail{background:#E4F0FF;border-radius:11px;}"
        )
        buttons = QVBoxLayout(rail)
        buttons.setContentsMargins(5, 6, 5, 6)
        buttons.setSpacing(7)

        def action(label, color, ink="#14233E", height=51):
            button = QPushButton(label)
            button.setFixedHeight(height)
            button.setStyleSheet(
                f"QPushButton{{background:{color};color:{ink};border:0;"
                "border-radius:10px;font-size:15px;font-weight:800;padding:4px;}"
                "QPushButton:pressed{background:#A6C7F4;color:#14233E;}"
                "QPushButton:disabled{background:#D8E1EB;color:#68788C;}"
            )
            return button

        self.record_button = action("RECORD VOICES", "#FFCA45", height=69)
        self.record_button.clicked.connect(self.record_take)
        self.listen_button = action("PLAY TAKE", "#B7DEFF")
        self.listen_button.clicked.connect(self.play_take)
        self.save_button = action("SAVE MP4", "#20BD87", height=61)
        self.save_button.clicked.connect(self.save_mp4)
        self.cancel_button = action("CANCEL TAKE", "#E95370", "#FFFFFF")
        self.cancel_button.clicked.connect(self.cancel_take)
        self.back_button = action("BACK TO MOVIES", "#2778F2", "#FFFFFF")
        self.back_button.clicked.connect(self.go_back)

        buttons.addWidget(self.record_button)
        buttons.addWidget(self.listen_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(5)
        layout.addLayout(camera_side, 1)
        layout.addWidget(rail)
        self.refresh_buttons()

    def open_project(self, project, frames, fps, name):
        if self.busy():
            return False
        self.preview_timer.stop()
        self.project = Path(project)
        self.frames = list(frames)
        self.fps = max(1, int(fps))
        self.position = -1
        self.title.setText("VOICES: " + str(name)[:32])
        self.show_frame(0)
        self.status.setText(
            "Tap RECORD VOICES and speak as the pictures play. "
            "You can redo the whole take before saving."
        )
        if self.voice_is_current():
            self.status.setText("Voice take saved. PLAY TAKE or SAVE MP4.")
        elif self.voice_file().exists():
            self.status.setText(
                "Pictures or FPS changed. Record a new voice take for this version."
            )
        self.refresh_buttons()
        return True

    def voice_file(self):
        return self.project / "narration.wav" if self.project else Path("/nonexistent")

    def voice_is_current(self):
        if not self.project or not self.frames or not self.voice_file().is_file():
            return False
        marker = self.project / "narration.json"
        try:
            saved = json.loads(marker.read_text(encoding="utf-8"))
            return (
                saved.get("frames") == len(self.frames)
                and saved.get("fps") == self.fps
                and self.voice_file().stat().st_size > 1000
            )
        except (OSError, ValueError, TypeError, AttributeError):
            return False

    def busy(self):
        return self.recorder is not None or self.audio_player is not None or self.encoder is not None

    def refresh_buttons(self):
        occupied = self.busy()
        self.record_button.setEnabled(bool(self.frames) and not occupied)
        self.listen_button.setEnabled(self.voice_is_current() and not occupied)
        self.save_button.setEnabled(self.voice_is_current() and not occupied)
        self.cancel_button.setEnabled(self.recorder is not None)
        self.back_button.setEnabled(not occupied)

    def show_frame(self, position):
        if not self.frames:
            self.preview.setText("No pictures in this movie.")
            return
        position = max(0, min(position, len(self.frames) - 1))
        if position != self.position:
            self.position = position
            reader = QImageReader(str(self.frames[position]))
            reader.setAutoTransform(True)
            size = reader.size()
            target = self.preview.size()
            if size.isValid() and target.width() > 0 and target.height() > 0:
                reader.setScaledSize(size.scaled(target, Qt.KeepAspectRatio))
            image = reader.read()
            if image.isNull():
                self.preview.setPixmap(QPixmap())
                self.preview.setText("Unable to read this picture.")
            else:
                self.preview.setPixmap(QPixmap.fromImage(image))
        seconds = position / self.fps
        duration = len(self.frames) / self.fps
        self.counter.setText(
            f"{int(seconds // 60):02d}:{int(seconds % 60):02d} / "
            f"{int(duration // 60):02d}:{int(duration % 60):02d}"
        )

    def start_preview(self):
        self.show_frame(0)
        self.elapsed.start()
        self.preview_timer.start()
        if self.recorder is not None:
            self.status.setText("RECORDING VOICES... Speak as the pictures play.")
        elif self.audio_player is not None:
            self.status.setText("Playing your voice take...")

    def tick_preview(self):
        if not self.frames:
            self.preview_timer.stop()
            return
        millis = self.elapsed.elapsed()
        index = min(len(self.frames) - 1, int(millis * self.fps / 1000))
        self.show_frame(index)
        if millis >= (1000 * len(self.frames) / self.fps):
            self.preview_timer.stop()

    def record_take(self):
        if self.busy() or not self.frames:
            return
        executable = shutil.which("arecord")
        if not executable:
            self.status.setText("Microphone recorder missing: install alsa-utils.")
            return
        self.canceling = False
        temp_audio = self.project / "narration.partial.wav"
        try:
            temp_audio.unlink(missing_ok=True)
        except OSError as exc:
            self.status.setText(f"Cannot prepare microphone recording: {exc}")
            return
        self.recorder = QProcess(self)
        proc = self.recorder
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.started.connect(self.start_preview)
        proc.finished.connect(
            lambda code, status, p=proc: self.record_finished(p, code, status)
        )
        proc.errorOccurred.connect(
            lambda error, p=proc: self.record_error(p, error)
        )
        self.status.setText("Starting USB microphone...")
        self.refresh_buttons()
        seconds = max(1, math.ceil(len(self.frames) / self.fps))
        device = capture_device()
        proc.start(
            executable,
            [
                "-q", "-D", device, "-t", "wav", "-f", "S16_LE", "-r", "44100",
                "-c", "1", "-d", str(seconds), str(temp_audio),
            ],
        )

    def cancel_take(self):
        if self.recorder is None:
            return
        self.canceling = True
        self.status.setText("Cancelling take; the previous recording is safe.")
        self.recorder.kill()

    def record_error(self, proc, error):
        if proc is self.recorder and error == QProcess.FailedToStart:
            self.record_finished(proc, -1, QProcess.CrashExit)

    def record_finished(self, proc, code, _status):
        if proc is not self.recorder:
            return
        self.preview_timer.stop()
        self.recorder = None
        self.show_frame(0)
        raw = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        proc.deleteLater()
        temp_audio = self.project / "narration.partial.wav"
        if self.canceling:
            temp_audio.unlink(missing_ok=True)
            self.status.setText("Take cancelled. Previous recording kept.")
        elif code != 0 or not temp_audio.is_file():
            temp_audio.unlink(missing_ok=True)
            detail = raw.strip().splitlines()
            self.status.setText(
                "Mic could not record. Run arecord -l to check the USB mic. "
                + (detail[-1][:65] if detail else "")
            )
        else:
            try:
                with wave.open(str(temp_audio), "rb") as audio:
                    duration = audio.getnframes() / audio.getframerate()
                if duration < 0.5:
                    raise ValueError("Recording was too short.")
                temp_audio.replace(self.voice_file())
                (self.project / "narration.json").write_text(
                    json.dumps({"frames": len(self.frames), "fps": self.fps}),
                    encoding="utf-8",
                )
                self.status.setText("Voice take saved. Play it back or save an MP4.")
            except (OSError, ValueError, ZeroDivisionError, wave.Error) as exc:
                self.status.setText(f"Could not save the voice take: {exc}")
                temp_audio.unlink(missing_ok=True)
        self.refresh_buttons()

    def play_take(self):
        if self.busy() or not self.voice_is_current():
            return
        executable = shutil.which("aplay")
        if not executable:
            self.status.setText("Audio player missing: install alsa-utils.")
            return
        self.audio_player = QProcess(self)
        proc = self.audio_player
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.started.connect(self.start_preview)
        proc.finished.connect(
            lambda code, status, p=proc: self.play_finished(p, code)
        )
        proc.errorOccurred.connect(
            lambda error, p=proc: self.play_error(p, error)
        )
        self.status.setText("Playing voice take through Pi audio output...")
        self.refresh_buttons()
        proc.start(executable, ["-q", str(self.voice_file())])

    def play_error(self, proc, error):
        if proc is self.audio_player and error == QProcess.FailedToStart:
            self.play_finished(proc, -1)

    def play_finished(self, proc, code):
        if proc is not self.audio_player:
            return
        self.preview_timer.stop()
        self.audio_player = None
        output = bytes(proc.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        ).strip().splitlines()
        proc.deleteLater()
        self.status.setText(
            "Voice playback finished." if code == 0 else
            "Could not play audio. Check Pi speaker/output. " +
            (output[-1][:75] if output else "")
        )
        self.refresh_buttons()

    def save_mp4(self):
        if self.busy() or not self.voice_is_current():
            return
        executable = shutil.which("ffmpeg")
        if not executable:
            self.status.setText("MP4 encoder missing. Install ffmpeg.")
            return
        # FFmpeg image2 needs contiguous numbering. Link stills in a temporary
        # directory instead of copying pictures or changing the real project.
        try:
            staging = tempfile.TemporaryDirectory(prefix="picap_mp4_")
            for i, frame in enumerate(self.frames, 1):
                (Path(staging.name) / f"frame{i:04d}.jpg").symlink_to(
                    frame.resolve(strict=True)
                )
            partial = self.project / "movie.partial.mp4"
            partial.unlink(missing_ok=True)
        except OSError as exc:
            if "staging" in locals():
                staging.cleanup()
            self.status.setText(f"Unable to prepare movie: {exc}")
            return
        self.render_staging = staging
        self.encoder = QProcess(self)
        proc = self.encoder
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(
            lambda code, status, p=proc: self.render_finished(p, code)
        )
        proc.errorOccurred.connect(
            lambda error, p=proc: self.render_error(p, error)
        )
        self.last_error = ""
        proc.readyReadStandardOutput.connect(
            lambda p=proc: self.read_render_output(p)
        )
        self.status.setText(
            "Making MP4 with your voices. Please wait; this may take a few minutes."
        )
        self.refresh_buttons()
        duration = len(self.frames) / self.fps
        args = [
            "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-framerate", str(self.fps), "-start_number", "1",
            "-i", str(Path(staging.name) / "frame%04d.jpg"),
            "-i", str(self.voice_file()),
            "-frames:v", str(len(self.frames)),
            "-t", f"{duration:.4f}",
            "-vf",
            "scale=640:360:force_original_aspect_ratio=decrease,"
            "pad=640:360:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
            "-threads", "1", "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart",
            str(partial),
        ]
        proc.start(executable, args)
        # Avoid waiting forever if an encoder blocks on the Pi.
        QTimer.singleShot(10 * 60 * 1000, lambda p=proc: self.render_timeout(p))

    def read_render_output(self, proc):
        if proc is self.encoder:
            chunk = bytes(proc.readAllStandardOutput()).decode(
                "utf-8", errors="replace"
            )
            self.last_error = (self.last_error + chunk)[-1200:]

    def render_timeout(self, proc):
        if proc is self.encoder:
            self.last_error = "Encoding timed out after 10 minutes."
            proc.kill()

    def render_error(self, proc, error):
        if proc is self.encoder and error == QProcess.FailedToStart:
            self.render_finished(proc, -1)

    def render_finished(self, proc, code):
        if proc is not self.encoder:
            return
        self.read_render_output(proc)
        self.encoder = None
        proc.deleteLater()
        partial = self.project / "movie.partial.mp4"
        if self.render_staging is not None:
            self.render_staging.cleanup()
            self.render_staging = None
        if code == 0 and partial.is_file() and partial.stat().st_size > 1000:
            try:
                partial.replace(self.project / "movie.mp4")
                self.status.setText(
                    "MP4 saved with voices! Open MY MOVIES and tap PHONE QR."
                )
                self.movie_saved.emit(str(self.project))
            except OSError as exc:
                self.status.setText(f"Could not finish MP4: {exc}")
        else:
            partial.unlink(missing_ok=True)
            lines = self.last_error.strip().splitlines()
            self.status.setText(
                "MP4 failed: " + (lines[-1][:135] if lines else "Check ffmpeg installation.")
            )
        self.refresh_buttons()

    def go_back(self):
        if self.busy():
            return
        self.preview_timer.stop()
        self.back_requested.emit()

    def close(self):
        self.preview_timer.stop()
        for proc in (self.recorder, self.audio_player, self.encoder):
            if proc is not None:
                proc.kill()
                proc.waitForFinished(1000)
        self.recorder = None
        self.audio_player = None
        self.encoder = None
        if self.render_staging is not None:
            self.render_staging.cleanup()
            self.render_staging = None
        super().close()
