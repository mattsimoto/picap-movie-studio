#!/usr/bin/env python3
from pathlib import Path
import json
import re
import shutil
import struct
import sys
from datetime import datetime

from PyQt5.QtCore import QSize, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QImageReader, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from stage4_mjpeg import PiCapStageFourMJPEG

BASE_DIR = Path.home() / "PiCapMovies"
PROJECTS_DIR = BASE_DIR / "projects"
WORKING_LINK = BASE_DIR / "stage2-test"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def safe_slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-")
    return slug or datetime.now().strftime("movie-%Y%m%d-%H%M%S")


def project_meta(project_dir: Path):
    meta_path = project_dir / "project.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except Exception:
            pass
    return {"name": project_dir.name.replace("-", " "), "created": ""}


def write_meta(project_dir: Path, name: str, created=None):
    meta = {
        "name": name,
        "created": created or datetime.now().isoformat(timespec="seconds"),
    }
    (project_dir / "project.json").write_text(json.dumps(meta, indent=2))


def frame_paths(project_dir: Path):
    frames_dir = project_dir / "frames"
    if not frames_dir.exists():
        return []
    return sorted(frames_dir.glob("frame*.jpg"))


def frame_count(project_dir: Path) -> int:
    return len(frame_paths(project_dir))


def movie_path(project_dir: Path) -> Path:
    return project_dir / "movie.avi"


def playback_fps(project_dir: Path) -> int:
    """Use the exported AVI's timing when present; older drafts default to 10 fps."""
    avi = movie_path(project_dir)
    if avi.exists():
        try:
            with avi.open("rb") as movie:
                header = movie.read(4096)
            pos = header.find(b"strh")
            if pos >= 0 and pos + 36 <= len(header):
                scale, rate = struct.unpack_from("<II", header, pos + 28)
                if scale and 1 <= rate / scale <= 30:
                    return round(rate / scale)
        except (OSError, ValueError, struct.error, ZeroDivisionError):
            pass
    return 10


def project_thumbnail(project_dir: Path):
    frames = frame_paths(project_dir)
    return frames[-1] if frames else None


def unique_project_path(name: str, exclude=None) -> Path:
    base_slug = safe_slug(name)
    candidate = PROJECTS_DIR / base_slug
    suffix = 2
    while candidate.exists() and candidate != exclude:
        candidate = PROJECTS_DIR / f"{base_slug}-{suffix}"
        suffix += 1
    return candidate


def migrate_legacy_folder():
    if WORKING_LINK.is_symlink() or not WORKING_LINK.exists():
        return

    has_content = any(WORKING_LINK.iterdir())
    if not has_content:
        WORKING_LINK.rmdir()
        return

    target = PROJECTS_DIR / "Recovered-Movie"
    suffix = 2
    while target.exists():
        target = PROJECTS_DIR / f"Recovered-Movie-{suffix}"
        suffix += 1
    shutil.move(str(WORKING_LINK), str(target))
    if not (target / "project.json").exists():
        write_meta(target, "Recovered Movie")


def point_working_link(project_dir: Path):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    migrate_legacy_folder()

    if WORKING_LINK.is_symlink():
        WORKING_LINK.unlink()
    elif WORKING_LINK.exists():
        raise RuntimeError(f"Cannot replace existing {WORKING_LINK}")

    WORKING_LINK.symlink_to(project_dir, target_is_directory=True)


class FilmingWindow(PiCapStageFourMJPEG):
    """Camera window that returns to the gallery only after releasing hardware."""

    studio_closed = pyqtSignal()

    def __init__(self, project_dir):
        super().__init__(project_dir=project_dir)

    def finish_camera_close(self):
        # Base closeEvent schedules this after stopping Qt preview/capture.
        # Do not open a second Picamera2 until the first has been closed.
        super().finish_camera_close()
        self.studio_closed.emit()


class TouchKeyboard(QWidget):
    """Simple built-in keyboard so PiCap never depends on an external keyboard."""

    def __init__(self, target_getter, parent=None):
        super().__init__(parent)
        self.target_getter = target_getter
        self.setStyleSheet("background:transparent;")

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)

        key_style = (
            "QPushButton{background:#FFFFFF;color:#14233E;border:2px solid #A6C7F4;"
            "border-radius:7px;font-size:18px;font-weight:800;padding:2px;}"
            "QPushButton:pressed{background:#BFDCFF;border-color:#2876E8;}"
        )
        wide_style = (
            "QPushButton{background:#2778F2;color:#FFFFFF;border:2px solid #2778F2;"
            "border-radius:7px;font-size:15px;font-weight:800;padding:2px;}"
            "QPushButton:pressed{background:#164EAD;}"
        )

        rows = [
            "1234567890",
            "QWERTYUIOP",
            "ASDFGHJKL",
            "ZXCVBNM",
        ]

        for row_index, chars in enumerate(rows):
            start_col = 0 if row_index < 2 else (1 if row_index == 2 else 2)
            for i, char in enumerate(chars):
                button = QPushButton(char)
                button.setFixedHeight(38)
                button.setStyleSheet(key_style)
                button.clicked.connect(lambda _checked=False, c=char: self.type_char(c))
                grid.addWidget(button, row_index, start_col + i)

        back = QPushButton("⌫")
        back.setFixedHeight(40)
        back.setStyleSheet(wide_style)
        back.clicked.connect(self.backspace)
        grid.addWidget(back, 4, 0, 1, 2)

        hyphen = QPushButton("-")
        hyphen.setFixedHeight(40)
        hyphen.setStyleSheet(key_style)
        hyphen.clicked.connect(lambda: self.insert_text("-"))
        grid.addWidget(hyphen, 4, 2)

        apostrophe = QPushButton("'")
        apostrophe.setFixedHeight(40)
        apostrophe.setStyleSheet(key_style)
        apostrophe.clicked.connect(lambda: self.insert_text("'"))
        grid.addWidget(apostrophe, 4, 3)

        space = QPushButton("SPACE")
        space.setFixedHeight(40)
        space.setStyleSheet(wide_style)
        space.clicked.connect(lambda: self.insert_text(" "))
        grid.addWidget(space, 4, 4, 1, 4)

        clear = QPushButton("CLEAR")
        clear.setFixedHeight(40)
        clear.setStyleSheet(wide_style)
        clear.clicked.connect(self.clear_text)
        grid.addWidget(clear, 4, 8, 1, 2)

    def target(self):
        return self.target_getter()

    def insert_text(self, text):
        target = self.target()
        if target is not None:
            target.insert(text)
            target.setFocus()

    def type_char(self, char):
        target = self.target()
        if target is None:
            return
        current = target.text()
        # Makes kid-entered titles naturally look like title case without a Shift key.
        if not current or current[-1].isspace() or current[-1] in "-'":
            self.insert_text(char.upper())
        else:
            self.insert_text(char.lower())

    def backspace(self):
        target = self.target()
        if target is not None:
            target.backspace()
            target.setFocus()

    def clear_text(self):
        target = self.target()
        if target is not None:
            target.clear()
            target.setFocus()


class GalleryMoviePlayer(QWidget):
    """Play original project JPEGs without depending on AVI/VLC decoding."""

    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frames = []
        self.position = 0
        self.fps = 10
        self.finished = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 6)
        layout.setSpacing(5)
        self.title_label = QLabel("WATCH MOVIE")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFixedHeight(32)
        self.title_label.setStyleSheet("font-size:23px;font-weight:900;color:#14233E;")
        self.screen = QLabel("Choose a movie to watch")
        self.screen.setAlignment(Qt.AlignCenter)
        self.screen.setMinimumHeight(130)
        self.screen.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.screen.setStyleSheet("background:#091526;color:white;border:3px solid #2778F2;border-radius:11px;")
        self.frame_label = QLabel("")
        self.frame_label.setAlignment(Qt.AlignCenter)
        self.frame_label.setFixedHeight(20)
        self.frame_label.setStyleSheet("font-size:14px;font-weight:700;color:#34527B;")

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.play_btn = QPushButton("PAUSE")
        self.play_btn.clicked.connect(self.toggle_play)
        replay_btn = QPushButton("RESTART")
        replay_btn.clicked.connect(self.restart)
        back_btn = QPushButton("BACK TO MOVIES")
        back_btn.clicked.connect(self.go_back)
        for button, color, ink in (
            (self.play_btn, "#FFCA45", "#14233E"),
            (replay_btn, "#20BD87", "#14233E"),
            (back_btn, "#2778F2", "#FFFFFF"),
        ):
            button.setMinimumHeight(50)
            button.setStyleSheet(
                f"QPushButton{{background:{color};color:{ink};border:0;"
                "border-radius:10px;font-size:15px;font-weight:800;padding:5px;}"
                "QPushButton:pressed{background:#B7D7FF;color:#14233E;}"
            )
        actions.addWidget(self.play_btn, 1)
        actions.addWidget(replay_btn, 1)
        actions.addWidget(back_btn, 2)
        layout.addWidget(self.title_label)
        layout.addWidget(self.screen, 1)
        layout.addWidget(self.frame_label)
        layout.addLayout(actions)

    def open_project(self, project_dir):
        self.stop()
        self.frames = frame_paths(project_dir)
        if not self.frames:
            return False
        self.position = 0
        self.finished = False
        self.fps = playback_fps(project_dir)
        self.title_label.setText(project_meta(project_dir).get("name", project_dir.name))
        self.display_frame()
        return True

    def display_frame(self):
        if not self.frames:
            return
        reader = QImageReader(str(self.frames[self.position]))
        reader.setAutoTransform(True)
        size = reader.size()
        target = self.screen.size()
        if size.isValid() and target.width() > 0 and target.height() > 0:
            reader.setScaledSize(size.scaled(target, Qt.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            self.screen.setPixmap(QPixmap())
            self.screen.setText("This picture could not be opened.")
        else:
            self.screen.setPixmap(QPixmap.fromImage(image))
        self.frame_label.setText(f"PICTURE {self.position + 1} / {len(self.frames)}  •  {self.fps} FPS")

    def start(self):
        if not self.frames:
            return
        if self.finished:
            self.position = 0
            self.finished = False
            self.display_frame()
        self.timer.start(max(1, round(1000 / self.fps)))
        self.play_btn.setText("PAUSE")

    def stop(self):
        self.timer.stop()
        self.play_btn.setText("PLAY")

    def toggle_play(self):
        if self.timer.isActive():
            self.stop()
        else:
            self.start()

    def next_frame(self):
        if not self.frames:
            self.stop()
        elif self.position >= len(self.frames) - 1:
            self.finished = True
            self.stop()
            self.play_btn.setText("PLAY AGAIN")
        else:
            self.position += 1
            self.display_frame()

    def restart(self):
        self.stop()
        if self.frames:
            self.position = 0
            self.finished = False
            self.display_frame()
            self.start()

    def go_back(self):
        self.stop()
        self.back_requested.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.frames and not self.timer.isActive():
            QTimer.singleShot(0, self.display_frame)


class StudioHome(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PiCap Movie Studio")
        self.setStyleSheet("background:#F1F7FF;color:#14233E;")

        self.selected_project = None
        self.filming_window = None
        self.loading_tick = 0
        self.title_mode = "new"
        self.rename_target = None

        self.stack = QStackedWidget()
        self.home_page = self.build_home_page()
        self.gallery_page = self.build_gallery_page()
        self.title_page = self.build_title_page()
        self.loading_page = self.build_loading_page()
        self.error_page = self.build_error_page()
        self.player_page = GalleryMoviePlayer()
        self.player_page.back_requested.connect(self.open_gallery)
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.gallery_page)
        self.stack.addWidget(self.title_page)
        self.stack.addWidget(self.loading_page)
        self.stack.addWidget(self.error_page)
        self.stack.addWidget(self.player_page)

        root = QVBoxLayout()
        root.setContentsMargins(10, 8, 10, 14)
        root.addWidget(self.stack)
        self.setLayout(root)

        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(500)
        self.loading_timer.timeout.connect(self.animate_loading)

        migrate_legacy_folder()
        self.showFullScreen()
        QApplication.processEvents()
        QTimer.singleShot(50, self.refresh_gallery)

    def button_colors(self, color):
        # Keep text readable on both bright and pale button backgrounds.
        palette = {
            "#FFCA45": ("#14233E", "#E5AD28"),
            "#2778F2": ("#FFFFFF", "#1555C4"),
            "#20BD87": ("#14233E", "#10A571"),
            "#E95370": ("#FFFFFF", "#C63855"),
            "#DCEAFF": ("#14233E", "#BBD6FB"),
        }
        return palette.get(color, ("#14233E", "#BBD6FB"))

    def big_button(self, text, color="#DCEAFF"):
        ink, pressed = self.button_colors(color)
        b = QPushButton(text)
        b.setMinimumHeight(68)
        b.setStyleSheet(
            f"QPushButton{{background:{color};color:{ink};border:2px solid {color};"
            "border-radius:14px;font-size:23px;font-weight:800;padding:8px;}"
            f"QPushButton:pressed{{background:{pressed};}}"
            "QPushButton:disabled{background:#E9EFF8;color:#78869A;border-color:#CAD5E3;}"
        )
        return b

    def small_button(self, text, color="#DCEAFF"):
        ink, pressed = self.button_colors(color)
        b = QPushButton(text)
        b.setMinimumHeight(54)
        b.setStyleSheet(
            f"QPushButton{{background:{color};color:{ink};border:2px solid {color};"
            "border-radius:12px;font-size:16px;font-weight:800;padding:6px;}"
            f"QPushButton:pressed{{background:{pressed};}}"
            "QPushButton:disabled{background:#E9EFF8;color:#78869A;border-color:#CAD5E3;}"
        )
        return b

    def build_home_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("PiCap Movie Studio")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:32px;font-weight:900;padding:10px;")
        subtitle = QLabel("Make a new movie or keep working on an old one")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:16px;color:#34527B;padding-bottom:12px;")

        new_btn = self.big_button("NEW MOVIE", "#FFCA45")
        new_btn.clicked.connect(self.start_new_title)
        gallery_btn = self.big_button("MY MOVIES", "#2778F2")
        gallery_btn.clicked.connect(self.open_gallery)
        exit_btn = self.big_button("EXIT", "#DCEAFF")
        exit_btn.clicked.connect(self.close)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(new_btn)
        layout.addWidget(gallery_btn)
        layout.addWidget(exit_btn)
        layout.addStretch(1)
        return w

    def build_title_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 2, 4, 8)
        layout.setSpacing(4)

        self.title_heading = QLabel("NEW MOVIE")
        self.title_heading.setAlignment(Qt.AlignCenter)
        self.title_heading.setFixedHeight(32)
        self.title_heading.setStyleSheet("font-size:25px;font-weight:900;")

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Movie title")
        self.title_input.setFixedHeight(48)
        self.title_input.setStyleSheet(
            "QLineEdit{background:#FFFFFF;color:#14233E;border:2px solid #78AAEE;border-radius:9px;font-size:21px;padding:6px;}"
        )

        keyboard = TouchKeyboard(lambda: self.title_input)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.setContentsMargins(0, 4, 0, 8)
        self.title_action_btn = self.small_button("START FILMING", "#FFCA45")
        self.title_action_btn.setMinimumHeight(64)
        self.title_action_btn.clicked.connect(self.commit_title_edit)
        back_btn = self.small_button("BACK")
        back_btn.setMinimumHeight(64)
        back_btn.clicked.connect(self.cancel_title_edit)
        actions.addWidget(self.title_action_btn, 2)
        actions.addWidget(back_btn, 1)

        layout.addWidget(self.title_heading)
        layout.addWidget(self.title_input)
        layout.addWidget(keyboard, 1)
        layout.addLayout(actions)
        return w

    def build_loading_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 35, 20, 35)
        layout.addStretch(1)

        self.loading_title = QLabel("GETTING THE CAMERA READY")
        self.loading_title.setAlignment(Qt.AlignCenter)
        self.loading_title.setStyleSheet("font-size:30px;font-weight:900;color:#14233E;")
        self.loading_project = QLabel("")
        self.loading_project.setAlignment(Qt.AlignCenter)
        self.loading_project.setStyleSheet("font-size:20px;font-weight:700;color:#A85000;padding:12px;")
        self.loading_message = QLabel("Setting up your movie...")
        self.loading_message.setAlignment(Qt.AlignCenter)
        self.loading_message.setStyleSheet("font-size:18px;color:#34527B;padding:8px;")
        hint = QLabel("The camera can take a few seconds to wake up. Please wait here.")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:14px;color:#4C6584;padding:8px;")

        layout.addWidget(self.loading_title)
        layout.addWidget(self.loading_project)
        layout.addWidget(self.loading_message)
        layout.addWidget(hint)
        layout.addStretch(1)
        return w

    def build_error_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addStretch(1)
        title = QLabel("THE CAMERA NEEDS HELP")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:28px;font-weight:900;color:#BF3450;")
        self.error_message = QLabel("PiCap could not start the camera.")
        self.error_message.setWordWrap(True)
        self.error_message.setAlignment(Qt.AlignCenter)
        self.error_message.setStyleSheet("font-size:16px;color:#34527B;padding:14px;")
        retry_btn = self.big_button("TRY AGAIN", "#FFCA45")
        retry_btn.clicked.connect(self.retry_selected_project)
        gallery_btn = self.small_button("BACK TO MY MOVIES")
        gallery_btn.clicked.connect(self.open_gallery)
        layout.addWidget(title)
        layout.addWidget(self.error_message)
        layout.addWidget(retry_btn)
        layout.addWidget(gallery_btn)
        layout.addStretch(1)
        return w

    def build_gallery_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(5)

        title = QLabel("MY MOVIES")
        title.setAlignment(Qt.AlignCenter)
        title.setFixedHeight(34)
        title.setStyleSheet("font-size:26px;font-weight:900;")

        self.project_list = QListWidget()
        self.project_list.setViewMode(QListView.IconMode)
        self.project_list.setMovement(QListView.Static)
        self.project_list.setResizeMode(QListView.Adjust)
        self.project_list.setWrapping(True)
        self.project_list.setWordWrap(True)
        self.project_list.setIconSize(QSize(190, 108))
        self.project_list.setGridSize(QSize(235, 168))
        self.project_list.setSpacing(5)
        self.project_list.setStyleSheet(
            "QListWidget{background:#FFFFFF;color:#14233E;border:2px solid #A6C7F4;border-radius:10px;"
            "font-size:15px;padding:5px;}"
            "QListWidget::item{background:#E4F0FF;color:#14233E;border:2px solid #B5CFF0;border-radius:10px;"
            "padding:6px;margin:2px;}"
            "QListWidget::item:selected{background:#B7D7FF;color:#14233E;border:3px solid #2778F2;}"
        )
        self.project_list.itemSelectionChanged.connect(self.gallery_selection_changed)
        self.project_list.itemDoubleClicked.connect(lambda _item: self.open_selected_project())

        primary = QHBoxLayout()
        primary.setSpacing(5)
        self.open_btn = self.small_button("OPEN & ADD SCENES", "#2778F2")
        self.open_btn.clicked.connect(self.open_selected_project)
        self.watch_btn = self.small_button("WATCH", "#20BD87")
        self.watch_btn.clicked.connect(self.watch_selected_project)
        back_btn = self.small_button("BACK")
        back_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_page))
        primary.addWidget(self.open_btn, 2)
        primary.addWidget(self.watch_btn, 1)
        primary.addWidget(back_btn, 1)

        manage = QHBoxLayout()
        manage.setSpacing(5)
        self.rename_btn = self.small_button("RENAME")
        self.rename_btn.clicked.connect(self.rename_selected_project)
        self.duplicate_btn = self.small_button("DUPLICATE")
        self.duplicate_btn.clicked.connect(self.duplicate_selected_project)
        self.delete_btn = self.small_button("DELETE", "#E95370")
        self.delete_btn.clicked.connect(self.delete_selected_project)
        manage.addWidget(self.rename_btn, 1)
        manage.addWidget(self.duplicate_btn, 1)
        manage.addWidget(self.delete_btn, 1)

        layout.addWidget(title)
        layout.addWidget(self.project_list, 1)
        layout.addLayout(primary)
        layout.addLayout(manage)
        return w

    def start_new_title(self):
        self.title_mode = "new"
        self.rename_target = None
        self.title_heading.setText("NEW MOVIE")
        self.title_action_btn.setText("START FILMING")
        self.title_input.clear()
        self.stack.setCurrentWidget(self.title_page)
        self.title_input.setFocus()

    def cancel_title_edit(self):
        if self.title_mode == "rename":
            self.open_gallery()
        else:
            self.stack.setCurrentWidget(self.home_page)

    def commit_title_edit(self):
        name = self.title_input.text().strip()
        if not name:
            name = f"Movie {datetime.now().strftime('%b %d %H-%M')}"

        if self.title_mode == "rename":
            self.finish_rename(name)
        else:
            self.create_project_with_name(name)

    def create_project_with_name(self, name):
        project_dir = unique_project_path(name)
        (project_dir / "frames").mkdir(parents=True)
        write_meta(project_dir, name)
        self.title_input.clear()
        self.launch_project(project_dir)

    def open_gallery(self):
        self.player_page.stop()
        self.refresh_gallery()
        self.stack.setCurrentWidget(self.gallery_page)

    def make_thumbnail_icon(self, project_dir: Path):
        thumb_path = project_thumbnail(project_dir)
        if thumb_path is None:
            return QIcon()
        pixmap = QPixmap(str(thumb_path))
        if pixmap.isNull():
            return QIcon()
        scaled = pixmap.scaled(190, 108, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        if scaled.width() > 190 or scaled.height() > 108:
            x = max(0, (scaled.width() - 190) // 2)
            y = max(0, (scaled.height() - 108) // 2)
            scaled = scaled.copy(x, y, 190, 108)
        return QIcon(scaled)

    def refresh_gallery(self):
        self.project_list.clear()
        projects = [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]
        projects.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for p in projects:
            meta = project_meta(p)
            count = frame_count(p)
            ready = movie_path(p).exists()
            status = "READY TO WATCH" if ready else "IN PROGRESS"
            label = f"{meta.get('name', p.name)}\n{count} frames • {status}"
            item = QListWidgetItem(self.make_thumbnail_icon(p), label)
            item.setData(Qt.UserRole, str(p))
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            item.setToolTip(meta.get("name", p.name))
            self.project_list.addItem(item)

        self.gallery_selection_changed()

    def selected_project_path(self):
        selected = self.project_list.selectedItems()
        if not selected:
            return None
        return Path(selected[0].data(Qt.UserRole))

    def gallery_selection_changed(self):
        p = self.selected_project_path()
        has = p is not None
        self.open_btn.setEnabled(has)
        self.rename_btn.setEnabled(has)
        self.duplicate_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        self.watch_btn.setEnabled(bool(p and frame_count(p) > 0))

    def open_selected_project(self):
        p = self.selected_project_path()
        if p:
            self.launch_project(p)

    def rename_selected_project(self):
        p = self.selected_project_path()
        if not p:
            return
        self.title_mode = "rename"
        self.rename_target = p
        self.title_heading.setText("RENAME MOVIE")
        self.title_action_btn.setText("SAVE NAME")
        self.title_input.setText(project_meta(p).get("name", p.name))
        self.title_input.selectAll()
        self.stack.setCurrentWidget(self.title_page)
        self.title_input.setFocus()

    def finish_rename(self, new_name):
        p = self.rename_target
        if not p or not p.exists():
            self.open_gallery()
            return
        meta = project_meta(p)
        old_name = meta.get("name", p.name)
        if new_name == old_name:
            self.open_gallery()
            return

        new_dir = unique_project_path(new_name, exclude=p)
        try:
            if WORKING_LINK.is_symlink():
                try:
                    points_to_project = WORKING_LINK.resolve() == p.resolve()
                except Exception:
                    points_to_project = False
            else:
                points_to_project = False

            if new_dir != p:
                p.rename(new_dir)
                p = new_dir

            write_meta(p, new_name, created=meta.get("created") or None)
            if points_to_project:
                point_working_link(p)
            self.rename_target = None
            self.open_gallery()
        except Exception as exc:
            self.error_message.setText(f"Could not rename this movie.\n\n{exc}")
            self.stack.setCurrentWidget(self.error_page)

    def duplicate_selected_project(self):
        p = self.selected_project_path()
        if not p:
            return
        meta = project_meta(p)
        copy_name = f"{meta.get('name', p.name)} Copy"
        target = unique_project_path(copy_name)
        try:
            shutil.copytree(p, target)
            write_meta(target, copy_name)
            self.refresh_gallery()
        except Exception as exc:
            QMessageBox.warning(self, "Could not duplicate movie", str(exc))

    def delete_selected_project(self):
        p = self.selected_project_path()
        if not p:
            return
        name = project_meta(p).get("name", p.name)
        answer = QMessageBox.question(
            self,
            "Delete movie?",
            f"Delete '{name}' and all of its pictures?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            if WORKING_LINK.is_symlink():
                try:
                    if WORKING_LINK.resolve() == p.resolve():
                        WORKING_LINK.unlink()
                except Exception:
                    pass
            shutil.rmtree(p)
            self.refresh_gallery()
        except Exception as exc:
            QMessageBox.warning(self, "Could not delete movie", str(exc))

    def show_loading(self, project_dir: Path):
        name = project_meta(project_dir).get("name", project_dir.name)
        self.loading_tick = 0
        self.loading_project.setText(name)
        self.loading_message.setText("Setting up your movie...")
        self.stack.setCurrentWidget(self.loading_page)
        self.showFullScreen()
        self.raise_()
        QApplication.processEvents()
        self.loading_timer.start()

    def animate_loading(self):
        self.loading_tick = (self.loading_tick + 1) % 4
        dots = "." * self.loading_tick
        messages = [
            "Waking up the camera",
            "Getting the stage ready",
            "Loading your pictures",
            "Almost ready to film",
        ]
        message = messages[(self.loading_tick - 1) % len(messages)]
        self.loading_message.setText(f"{message}{dots}")

    def launch_project(self, project_dir: Path):
        try:
            point_working_link(project_dir)
        except Exception as exc:
            self.error_message.setText(f"PiCap could not open this movie.\n\n{exc}")
            self.stack.setCurrentWidget(self.error_page)
            return

        self.selected_project = project_dir
        self.show_loading(project_dir)
        # Stay in the same Qt application instead of starting a second Python process.
        # This prevents the launcher from falling back to the terminal/gallery when
        # the child process exits and removes a large chunk of startup overhead.
        QTimer.singleShot(120, self.open_filming_window)

    def open_filming_window(self):
        if not self.selected_project or self.filming_window is not None:
            return
        try:
            self.filming_window = FilmingWindow(self.selected_project)
            self.filming_window.studio_closed.connect(self.filming_closed)
            self.filming_window.showFullScreen()
            self.filming_window.raise_()
            self.filming_window.activateWindow()
            self.loading_timer.stop()
        except Exception as exc:
            self.loading_timer.stop()
            self.filming_window = None
            self.error_message.setText(
                "PiCap could not start the camera.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                "Check that the camera is connected, then tap TRY AGAIN."
            )
            self.stack.setCurrentWidget(self.error_page)

    def filming_closed(self):
        self.loading_timer.stop()
        if self.selected_project and self.selected_project.exists():
            try:
                (self.selected_project / "project.json").touch(exist_ok=True)
            except Exception:
                pass
        old_window = self.filming_window
        self.filming_window = None
        self.refresh_gallery()
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.stack.setCurrentWidget(self.gallery_page)
        if old_window is not None:
            QTimer.singleShot(0, old_window.deleteLater)

    def retry_selected_project(self):
        if self.selected_project and self.selected_project.exists():
            self.launch_project(self.selected_project)
        else:
            self.open_gallery()

    def watch_selected_project(self):
        p = self.selected_project_path()
        if not p:
            return
        # Play original frames directly: old AVI movies can freeze on the first
        # frame in VLC even when the JPGs are intact.
        if not self.player_page.open_project(p):
            self.error_message.setText(
                "This movie has no original pictures to play.\n\n"
                "Its old AVI file may not work in VLC. The movie folder has not been changed."
            )
            self.stack.setCurrentWidget(self.error_page)
            return
        self.stack.setCurrentWidget(self.player_page)
        QTimer.singleShot(0, self.player_page.display_frame)
        QTimer.singleShot(0, self.player_page.start)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("PiCap Movie Studio")
    window = StudioHome()
    sys.exit(app.exec_())
