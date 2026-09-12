#!/usr/bin/env python3
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime

from PyQt5.QtCore import QProcess, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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


def write_meta(project_dir: Path, name: str):
    meta = {
        "name": name,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    (project_dir / "project.json").write_text(json.dumps(meta, indent=2))


def frame_count(project_dir: Path) -> int:
    frames = project_dir / "frames"
    return len(list(frames.glob("frame*.jpg"))) if frames.exists() else 0


def movie_path(project_dir: Path) -> Path:
    return project_dir / "movie.avi"


def migrate_legacy_folder():
    """Preserve the old stage2-test project before turning it into a project pointer."""
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
        # Safety fallback; migrate_legacy_folder normally handles this.
        raise RuntimeError(f"Cannot replace existing {WORKING_LINK}")

    WORKING_LINK.symlink_to(project_dir, target_is_directory=True)


class StudioHome(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PiCap Movie Studio")
        self.setStyleSheet("background:#161922;color:white;")
        self.process = None
        self.selected_project = None

        self.stack = QStackedWidget()
        self.home_page = self.build_home_page()
        self.gallery_page = self.build_gallery_page()
        self.new_page = self.build_new_page()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.gallery_page)
        self.stack.addWidget(self.new_page)

        root = QVBoxLayout()
        root.setContentsMargins(10, 8, 10, 8)
        root.addWidget(self.stack)
        self.setLayout(root)

        migrate_legacy_folder()
        self.refresh_gallery()
        self.showFullScreen()

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

    def small_button(self, text):
        b = QPushButton(text)
        b.setMinimumHeight(48)
        b.setStyleSheet(
            "QPushButton{background:#343947;color:white;border:2px solid #596174;border-radius:10px;"
            "font-size:16px;font-weight:800;padding:6px;}"
            "QPushButton:pressed{background:#596174;}"
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

    def build_gallery_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("MY MOVIES")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:28px;font-weight:900;")

        self.project_list = QListWidget()
        self.project_list.setStyleSheet(
            "QListWidget{background:#202530;color:white;border:2px solid #3b4352;border-radius:10px;"
            "font-size:18px;padding:4px;}"
            "QListWidget::item{padding:12px;border-bottom:1px solid #343947;}"
            "QListWidget::item:selected{background:#35506b;}"
        )
        self.project_list.itemSelectionChanged.connect(self.gallery_selection_changed)
        self.project_list.itemDoubleClicked.connect(lambda _item: self.open_selected_project())

        buttons = QHBoxLayout()
        self.open_btn = self.small_button("OPEN & ADD SCENES")
        self.open_btn.clicked.connect(self.open_selected_project)
        self.watch_btn = self.small_button("WATCH")
        self.watch_btn.clicked.connect(self.watch_selected_project)
        back_btn = self.small_button("BACK")
        back_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_page))
        buttons.addWidget(self.open_btn, 2)
        buttons.addWidget(self.watch_btn, 1)
        buttons.addWidget(back_btn, 1)

        layout.addWidget(title)
        layout.addWidget(self.project_list, 1)
        layout.addLayout(buttons)
        return w

    def open_gallery(self):
        self.refresh_gallery()
        self.stack.setCurrentWidget(self.gallery_page)

    def refresh_gallery(self):
        self.project_list.clear()
        projects = [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]
        projects.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in projects:
            meta = project_meta(p)
            count = frame_count(p)
            rendered = " • movie ready" if movie_path(p).exists() else ""
            label = f"{meta.get('name', p.name)}   • {count} frames{rendered}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, str(p))
            self.project_list.addItem(item)
        self.gallery_selection_changed()

    def gallery_selection_changed(self):
        selected = self.project_list.selectedItems()
        has = bool(selected)
        self.open_btn.setEnabled(has)
        if has:
            p = Path(selected[0].data(Qt.UserRole))
            self.watch_btn.setEnabled(movie_path(p).exists())
        else:
            self.watch_btn.setEnabled(False)

    def create_project(self):
        name = self.name_input.text().strip() or f"Movie {datetime.now().strftime('%b %d %H-%M')}"
        base_slug = safe_slug(name)
        project_dir = PROJECTS_DIR / base_slug
        suffix = 2
        while project_dir.exists():
            project_dir = PROJECTS_DIR / f"{base_slug}-{suffix}"
            suffix += 1
        (project_dir / "frames").mkdir(parents=True)
        write_meta(project_dir, name)
        self.name_input.clear()
        self.launch_project(project_dir)

    def open_selected_project(self):
        selected = self.project_list.selectedItems()
        if not selected:
            return
        self.launch_project(Path(selected[0].data(Qt.UserRole)))

    def launch_project(self, project_dir: Path):
        try:
            point_working_link(project_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Project error", str(exc))
            return

        self.selected_project = project_dir
        self.hide()
        self.process = QProcess(self)
        self.process.finished.connect(self.project_closed)
        self.process.start(sys.executable, [str(APP_SCRIPT)])

    def project_closed(self, _code, _status):
        self.process = None
        if self.selected_project and self.selected_project.exists():
            # Touch metadata so most recently worked project sorts first.
            try:
                meta_path = self.selected_project / "project.json"
                meta_path.touch(exist_ok=True)
            except Exception:
                pass
        self.selected_project = None
        self.refresh_gallery()
        self.showFullScreen()
        self.stack.setCurrentWidget(self.gallery_page)

    def watch_selected_project(self):
        selected = self.project_list.selectedItems()
        if not selected:
            return
        p = Path(selected[0].data(Qt.UserRole))
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
