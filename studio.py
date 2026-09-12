#!/usr/bin/env python3
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime

from PyQt5.QtCore import QProcess, QSize, QTimer, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

BASE_DIR = Path.home() / "PiCapMovies"
PROJECTS_DIR = BASE_DIR / "projects"
WORKING_LINK = BASE_DIR / "stage2-test"
APP_SCRIPT = Path(__file__).with_name("stage4_mjpeg.py")
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


class StudioHome(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PiCap Movie Studio")
        self.setStyleSheet("background:#161922;color:white;")
        self.process = None
        self.selected_project = None
        self.loading_tick = 0

        self.stack = QStackedWidget()
        self.home_page = self.build_home_page()
        self.gallery_page = self.build_gallery_page()
        self.new_page = self.build_new_page()
        self.loading_page = self.build_loading_page()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.gallery_page)
        self.stack.addWidget(self.new_page)
        self.stack.addWidget(self.loading_page)

        root = QVBoxLayout()
        root.setContentsMargins(10, 8, 10, 8)
        root.addWidget(self.stack)
        self.setLayout(root)

        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(450)
        self.loading_timer.timeout.connect(self.animate_loading)

        migrate_legacy_folder()
        self.showFullScreen()
        QApplication.processEvents()
        QTimer.singleShot(50, self.refresh_gallery)

    def big_button(self, text, color="#343947"):
        b = QPushButton(text)
        b.setMinimumHeight(74)
        b.setStyleSheet(
            f"QPushButton{{background:{color};color:white;border:none;border-radius:14px;"
            "font-size:24px;font-weight:800;padding:10px;}"
            "QPushButton:pressed{background:#596174;}"
            "QPushButton:disabled{background:#252832;color:#777;}"
        )
        return b

    def small_button(self, text, color="#343947"):
        b = QPushButton(text)
        b.setMinimumHeight(44)
        b.setStyleSheet(
            f"QPushButton{{background:{color};color:white;border:2px solid #596174;border-radius:10px;"
            "font-size:15px;font-weight:800;padding:5px;}"
            "QPushButton:pressed{background:#596174;}"
            "QPushButton:disabled{background:#252832;color:#777;border-color:#333744;}"
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
        subtitle.setStyleSheet("font-size:16px;color:#d8dbe5;padding-bottom:12px;")

        new_btn = self.big_button("NEW MOVIE", "#527a55")
        new_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.new_page))
        gallery_btn = self.big_button("MY MOVIES", "#35506b")
        gallery_btn.clicked.connect(self.open_gallery)
        exit_btn = self.big_button("EXIT", "#703c45")
        exit_btn.clicked.connect(self.close)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(new_btn)
        layout.addWidget(gallery_btn)
        layout.addWidget(exit_btn)
        layout.addStretch(1)
        return w

    def build_new_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("NEW MOVIE")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:28px;font-weight:900;")
        prompt = QLabel("Give your movie a name")
        prompt.setAlignment(Qt.AlignCenter)
        prompt.setStyleSheet("font-size:17px;color:#d8dbe5;")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("The Great Mouse Picnic")
        self.name_input.setMinimumHeight(62)
        self.name_input.setStyleSheet(
            "QLineEdit{background:white;color:#111;border-radius:10px;font-size:22px;padding:8px;}"
        )
        start_btn = self.big_button("START FILMING", "#527a55")
        start_btn.clicked.connect(self.create_project)
        back_btn = self.small_button("BACK")
        back_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_page))
        layout.addWidget(title)
        layout.addWidget(prompt)
        layout.addWidget(self.name_input)
        layout.addWidget(start_btn)
        layout.addWidget(back_btn)
        layout.addStretch(1)
        return w

    def build_loading_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 35, 20, 35)
        layout.addStretch(1)

        self.loading_title = QLabel("GETTING THE CAMERA READY")
        self.loading_title.setAlignment(Qt.AlignCenter)
        self.loading_title.setStyleSheet("font-size:30px;font-weight:900;color:white;")
        self.loading_project = QLabel("")
        self.loading_project.setAlignment(Qt.AlignCenter)
        self.loading_project.setStyleSheet("font-size:20px;font-weight:700;color:#f2b84b;padding:12px;")
        self.loading_message = QLabel("Setting up your movie...")
        self.loading_message.setAlignment(Qt.AlignCenter)
        self.loading_message.setStyleSheet("font-size:18px;color:#d8dbe5;padding:8px;")
        hint = QLabel("This can take a few seconds. Your movie is safe.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:14px;color:#9da5b4;padding:8px;")

        layout.addWidget(self.loading_title)
        layout.addWidget(self.loading_project)
        layout.addWidget(self.loading_message)
        layout.addWidget(hint)
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
            "QListWidget{background:#202530;color:white;border:2px solid #3b4352;border-radius:10px;"
            "font-size:15px;padding:5px;}"
            "QListWidget::item{background:#292f3b;border:2px solid #3b4352;border-radius:10px;"
            "padding:6px;margin:2px;}"
            "QListWidget::item:selected{background:#35506b;border:2px solid #74a0c8;}"
        )
        self.project_list.itemSelectionChanged.connect(self.gallery_selection_changed)
        self.project_list.itemDoubleClicked.connect(lambda _item: self.open_selected_project())

        primary = QHBoxLayout()
        primary.setSpacing(5)
        self.open_btn = self.small_button("OPEN & ADD SCENES", "#35506b")
        self.open_btn.clicked.connect(self.open_selected_project)
        self.watch_btn = self.small_button("WATCH", "#527a55")
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
        self.delete_btn = self.small_button("DELETE", "#703c45")
        self.delete_btn.clicked.connect(self.delete_selected_project)
        manage.addWidget(self.rename_btn, 1)
        manage.addWidget(self.duplicate_btn, 1)
        manage.addWidget(self.delete_btn, 1)

        layout.addWidget(title)
        layout.addWidget(self.project_list, 1)
        layout.addLayout(primary)
        layout.addLayout(manage)
        return w

    def open_gallery(self):
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
        self.watch_btn.setEnabled(bool(p and movie_path(p).exists()))

    def create_project(self):
        name = self.name_input.text().strip() or f"Movie {datetime.now().strftime('%b %d %H-%M')}"
        project_dir = unique_project_path(name)
        (project_dir / "frames").mkdir(parents=True)
        write_meta(project_dir, name)
        self.name_input.clear()
        self.launch_project(project_dir)

    def open_selected_project(self):
        p = self.selected_project_path()
        if p:
            self.launch_project(p)

    def rename_selected_project(self):
        p = self.selected_project_path()
        if not p:
            return
        meta = project_meta(p)
        old_name = meta.get("name", p.name)
        new_name, ok = QInputDialog.getText(self, "Rename movie", "Movie name:", text=old_name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return

        new_dir = unique_project_path(new_name, exclude=p)
        try:
            if new_dir != p:
                p.rename(new_dir)
                p = new_dir
            write_meta(p, new_name, created=meta.get("created") or None)
            self.refresh_gallery()
        except Exception as exc:
            QMessageBox.warning(self, "Could not rename movie", str(exc))

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
            QMessageBox.critical(self, "Project error", str(exc))
            return

        self.selected_project = project_dir
        self.show_loading(project_dir)

        # Keep the launcher fullscreen behind the camera app. This prevents the
        # desktop or terminal from flashing on screen while Picamera2 starts.
        self.process = QProcess(self)
        self.process.finished.connect(self.project_closed)
        self.process.errorOccurred.connect(self.project_launch_error)
        QTimer.singleShot(80, lambda: self.process.start(sys.executable, [str(APP_SCRIPT)]))

    def project_launch_error(self, _error):
        self.loading_timer.stop()
        self.process = None
        self.selected_project = None
        self.refresh_gallery()
        self.stack.setCurrentWidget(self.gallery_page)
        QMessageBox.warning(self, "Camera did not start", "PiCap could not open the filming screen.")

    def project_closed(self, _code, _status):
        self.loading_timer.stop()
        self.process = None
        if self.selected_project and self.selected_project.exists():
            try:
                meta_path = self.selected_project / "project.json"
                meta_path.touch(exist_ok=True)
            except Exception:
                pass
        self.selected_project = None
        self.refresh_gallery()
        self.showFullScreen()
        self.raise_()
        self.stack.setCurrentWidget(self.gallery_page)

    def watch_selected_project(self):
        p = self.selected_project_path()
        if not p:
            return
        movie = movie_path(p)
        if not movie.exists():
            return
        try:
            subprocess.Popen(["xdg-open", str(movie)])
        except Exception as exc:
            QMessageBox.warning(self, "Could not open movie", str(exc))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("PiCap Movie Studio")
    window = StudioHome()
    sys.exit(app.exec_())
