"""
gui.py - Build Log Studio (PySide6).

A tiny control panel for the manual side of the auto sync:
  - add a manual log entry to the latest episode (or start a new one)
  - pick media files (images -> ImgBB, videos -> Drive) and upload them
  - "Sync Now"  -> runs the same cycle as watcher.py
  - "Commit & Push" -> runs commit.bat

Run:  python gui.py
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

import watcher as W

PROJECT = W.PROJECT


# --------------------------------------------------------------------- workers
class Worker(QThread):
    out = Signal(str)
    done = Signal()

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.fn(self.out.emit)
        except Exception:
            self.out.emit(traceback.format_exc())
        self.done.emit()


# ------------------------------------------------------------------- main window
class Studio(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = W.load_cfg()
        self.files: list[str] = []
        self.setWindowTitle("Build Log Studio - Mark Ong / ZFNO")
        self.resize(760, 720)
        self._build()

    # -------------------------------------------------------------- layout
    def _build(self):
        v = QVBoxLayout(self)

        head = QLabel("BUILD LOG STUDIO")
        head.setStyleSheet("font-size:22px;font-weight:900;color:#ffd400;")
        v.addWidget(head)

        self.repo = QLabel(f"{self.cfg['github']['user']}/{self.cfg['github']['repo']}  "
                           f"@ {self.cfg['github'].get('branch','main')}")
        self.repo.setStyleSheet("color:#8f8a72;")
        v.addWidget(self.repo)

        v.addWidget(QLabel("Title"))
        self.title = QLineEdit()
        self.title.setPlaceholderText("feat: wired the media pipeline")
        v.addWidget(self.title)

        v.addWidget(QLabel("Body / description"))
        self.body = QPlainTextEdit()
        self.body.setPlaceholderText("What changed, why, blockers...")
        self.body.setFixedHeight(110)
        v.addWidget(self.body)

        row = QHBoxLayout()
        row.addWidget(QLabel("Tags"))
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("setup, feature, bugfix")
        row.addWidget(self.tags)
        row.addWidget(QLabel("Side"))
        self.side = QComboBox()
        self.side.addItems(["auto", "left", "right"])
        row.addWidget(self.side)
        v.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Attach to"))
        self.target = QComboBox()
        self.target.addItem("New episode (now)", None)
        self._reload_targets()
        row2.addWidget(self.target, 1)
        v.addLayout(row2)

        v.addWidget(QLabel("Media (images -> ImgBB, videos -> Drive)"))
        self.media = QListWidget()
        self.media.setFixedHeight(110)
        v.addWidget(self.media)
        mr = QHBoxLayout()
        b_add = QPushButton("Add files...")
        b_add.clicked.connect(self.pick_files)
        b_clr = QPushButton("Clear")
        b_clr.clicked.connect(self.clear_files)
        mr.addWidget(b_add)
        mr.addWidget(b_clr)
        mr.addStretch(1)
        v.addLayout(mr)

        br = QHBoxLayout()
        b_entry = QPushButton("Add Entry (upload media)")
        b_entry.setStyleSheet("font-weight:700;")
        b_entry.clicked.connect(self.add_entry)
        b_up = QPushButton("Upload Media Only")
        b_up.clicked.connect(self.upload_only)
        br.addWidget(b_entry)
        br.addWidget(b_up)
        v.addLayout(br)

        ar = QHBoxLayout()
        b_sync = QPushButton("Sync Now")
        b_sync.clicked.connect(self.sync_now)
        b_commit = QPushButton("Commit & Push")
        b_commit.clicked.connect(self.commit_push)
        ar.addWidget(b_sync)
        ar.addWidget(b_commit)
        v.addLayout(ar)

        v.addWidget(QLabel("Log"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family:Consolas,monospace;font-size:12px;")
        v.addWidget(self.log, 1)

    # -------------------------------------------------------------- helpers
    def emit(self, msg: str):
        self.log.appendPlainText(str(msg))

    def _reload_targets(self):
        data = W.load_data(self.cfg)
        eps = sorted(data.get("episodes", []), key=lambda e: e.get("timestamp", ""))
        self.target.clear()
        self.target.addItem("New episode (now)", None)
        for ep in reversed(eps):
            self.target.addItem(f"{ep['id']}  -  {ep.get('summary','')[:48]}", ep["id"])

    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Pick media", str(PROJECT / self.cfg["media_dir"]),
            "Media (*.png *.jpg *.jpeg *.gif *.webp *.mp4 *.mov *.webm *.mkv *.avi)")
        if files:
            self.files.extend(files)
            for f in files:
                self.media.addItem(f)

    def clear_files(self):
        self.files = []
        self.media.clear()

    def _busy(self, on: bool):
        self.setEnabled(not on)
        QApplication.setOverrideCursor(Qt.WaitCursor) if on else QApplication.restoreOverrideCursor()

    def _run(self, fn):
        self._busy(True)
        self.worker = Worker(fn)

        def finished():
            self._busy(False)
            self._reload_targets()

        self.worker.out.connect(self.emit)
        self.worker.done.connect(finished)
        self.worker.start()

    # -------------------------------------------------------------- actions
    def sync_now(self):
        self.emit("--- sync now ---")

        def job(emit):
            W.sync_once(self.cfg)

        self._run(job)

    def upload_only(self):
        self.emit("--- upload media only ---")

        def job(emit):
            W.sync_once(self.cfg, media_only=True)

        self._run(job)

    def add_entry(self):
        title = self.title.text().strip()
        body = self.body.toPlainText().strip()
        if not title and not body:
            QMessageBox.warning(self, "Nothing to add", "Give the entry a title or a body.")
            return
        tags = [t.strip() for t in self.tags.text().split(",") if t.strip()]
        files = list(self.files)
        target = self.target.currentData()
        side = self.side.currentText()
        self.emit("--- add entry ---")

        def job(emit):
            cfg = self.cfg
            tz = W.tz_offset(cfg)
            data = W.load_data(cfg)
            now = datetime.now(tz)

            ep = None
            if target:
                ep = next((e for e in data.get("episodes", []) if e["id"] == target), None)
            if ep is None:
                n = len(data.get("episodes", []))
                s = side if side in ("left", "right") else ("left" if n % 2 == 0 else "right")
                ep = {
                    "id": W.slug(now), "timestamp": now.isoformat(),
                    "name": now.strftime("%b %d - %H:%M"), "summary": title or "(note)",
                    "manual": True, "media": [],
                    "commits": [{
                        "sha": None, "date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M"),
                        "branch": cfg["github"].get("branch", "main"), "side": s,
                        "title": title or "(note)", "body": body, "tags": tags,
                        "images": [], "media": [], "files": [], "stats": {}, "link": "",
                    }],
                }
                data.setdefault("episodes", []).append(ep)
                emit(f"new episode {ep['id']}")
            else:
                ep["commits"][0]["body"] = (ep["commits"][0].get("body") or "") + \
                    (("\n\n" + body) if body else "")
                ep["commits"][0]["tags"] = sorted(set(ep["commits"][0].get("tags", []) + tags))
                emit(f"appended to {ep['id']}")

            service = None
            if any(W.classify(Path(f)) == "video" for f in files):
                try:
                    service = W.drive_service(cfg)
                except Exception as e:
                    emit(f"! drive unavailable: {e}")
            for f in files:
                p = Path(f)
                try:
                    kind, link = W.upload_media(cfg, p, service=service)
                except Exception as e:
                    emit(f"! upload failed {p.name}: {e}")
                    continue
                entry = {"name": p.name, "type": kind, "url": link, "at": now.isoformat()}
                ep.setdefault("media", []).append(entry)
                ep["commits"][0].setdefault("media", []).append(entry)
                if kind == "image":
                    ep["commits"][0].setdefault("images", []).append(link)
                emit(f"+ {kind} {p.name} -> {link}")

            W.write_data(cfg, data, tz)
            emit("saved public/timeline.json")

        self._run(job)

    def commit_push(self):
        bat = PROJECT / "commit.bat"
        if not bat.is_file():
            QMessageBox.warning(self, "Missing", "commit.bat not found in the project folder.")
            return
        self.emit("--- commit & push ---")

        def job(emit):
            import subprocess
            proc = subprocess.run(["cmd", "/c", str(bat)], cwd=str(PROJECT),
                                  capture_output=True, text=True, encoding="utf-8")
            emit(proc.stdout or "")
            if proc.stderr:
                emit(proc.stderr)

        self._run(job)


STYLE = """
QWidget{background:#0b0b0b;color:#fffdf5;font-family:Segoe UI,Arial;font-size:13px;}
QLineEdit,QPlainTextEdit,QListWidget,QComboBox{
  background:#111;border:1px solid #3a3320;color:#fff;padding:6px;selection-background-color:#ffd400;}
QLineEdit:focus,QPlainTextEdit:focus{border-color:#ffd400;}
QPushButton{background:#111;border:1px solid #3a3320;color:#cfcbb8;padding:9px 14px;
  font-weight:700;letter-spacing:1px;text-transform:uppercase;font-size:11px;}
QPushButton:hover{background:#ffd400;color:#000;border-color:#ffd400;}
QPushButton:disabled{opacity:.4;}
QLabel{color:#cfcbb8;}
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = Studio()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
