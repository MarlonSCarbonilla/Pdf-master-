"""Page thumbnail grid with lazy background rendering and a shared bounded cache."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    import main as _main_bootstrap  # noqa: F401

from typing import Optional

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap, QTransform
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem

from core.pdf_render import ThumbnailCache, render_thumbnail, thumbnail_key

THUMB_W = 120
MAX_AUTO_THUMBS = 600  # beyond this pages are still usable, thumbnails stay blank
CACHE = ThumbnailCache(64 * 1024 * 1024)


class ThumbnailLoader(QThread):
    """Renders thumbnails sequentially on its own document handle (fitz docs are not shared across threads)."""

    ready = Signal(int, int, int, bytes)

    def __init__(self, path: str, password: Optional[str], count: int, width: int = THUMB_W):
        super().__init__()
        self.path, self.password, self.count, self.width = path, password, count, width
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        from utils.validators import open_pdf
        try:
            doc = open_pdf(self.path, self.password)
        except Exception:
            return
        try:
            for i in range(min(self.count, MAX_AUTO_THUMBS)):
                if self._stop:
                    return
                key = thumbnail_key(self.path, i, self.width)
                v = CACHE.get(key)
                if v is None:
                    try:
                        v = render_thumbnail(doc[i], self.width)
                    except Exception:
                        continue
                    CACHE.put(key, v)
                self.ready.emit(i, v[0], v[1], v[2])
        finally:
            doc.close()


def _to_pixmap(w: int, h: int, data: bytes) -> QPixmap:
    img = QImage(data, w, h, w * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(img)


class ThumbnailGrid(QListWidget):
    """Grid of page thumbnails.

    Item data: UserRole = (source page index, extra rotation). In `movable` mode items can be
    reordered by drag & drop, duplicated and deleted; otherwise it is a plain page selector.
    """

    plan_changed = Signal()

    def __init__(self, movable: bool = False, parent=None):
        super().__init__(parent)
        self.movable = movable
        self._base: dict[int, QPixmap] = {}
        self._loader: Optional[ThumbnailLoader] = None
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setWrapping(True)
        self.setMovement(QListView.Static)
        self.setIconSize(QSize(THUMB_W, int(THUMB_W * 1.42)))
        self.setGridSize(QSize(THUMB_W + 28, int(THUMB_W * 1.42) + 44))
        self.setSpacing(4)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        if movable:
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(True)
            self.setDragDropMode(QAbstractItemView.InternalMove)
            self.setDefaultDropAction(Qt.MoveAction)
            self.model().rowsMoved.connect(lambda *_: self._after_change())

    # ---- loading ----
    def load(self, path: Optional[str], page_count: int = 0, password: Optional[str] = None) -> None:
        self.stop_loading()
        self.clear()
        self._base.clear()
        if not path:
            return
        for i in range(page_count):
            it = QListWidgetItem(str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            it.setData(Qt.UserRole, (i, 0))
            it.setToolTip(f"Original page {i + 1}")
            self.addItem(it)
        self._loader = ThumbnailLoader(path, password, page_count)
        self._loader.ready.connect(self._on_thumb)
        self._loader.start()
        self.plan_changed.emit()

    def stop_loading(self) -> None:
        if self._loader is not None:
            self._loader.stop()
            self._loader.wait(2000)
            self._loader = None

    def _on_thumb(self, idx: int, w: int, h: int, data: bytes) -> None:
        pm = _to_pixmap(w, h, data)
        self._base[idx] = pm
        for r in range(self.count()):
            it = self.item(r)
            src, rot = it.data(Qt.UserRole)
            if src == idx:
                it.setIcon(self._icon_for(idx, rot))

    def _icon_for(self, src: int, rot: int) -> QIcon:
        pm = self._base.get(src)
        if pm is None:
            return QIcon()
        if rot % 360:
            pm = pm.transformed(QTransform().rotate(rot), Qt.SmoothTransformation)
        return QIcon(pm)

    # ---- editing ----
    def plan(self) -> list[tuple[int, int]]:
        return [self.item(r).data(Qt.UserRole) for r in range(self.count())]

    def selected_rows(self) -> list[int]:
        return sorted(self.row(i) for i in self.selectedItems())

    def selected_source_pages(self) -> list[int]:
        return sorted({self.item(r).data(Qt.UserRole)[0] for r in self.selected_rows()})

    def select_source_pages(self, pages: list[int]) -> None:
        want = set(pages)
        self.blockSignals(True)
        self.clearSelection()
        for r in range(self.count()):
            if self.item(r).data(Qt.UserRole)[0] in want:
                self.item(r).setSelected(True)
        self.blockSignals(False)
        self.itemSelectionChanged.emit()

    def rotate_selected(self, delta: int) -> None:
        for r in self.selected_rows():
            it = self.item(r)
            src, rot = it.data(Qt.UserRole)
            rot = (rot + delta) % 360
            it.setData(Qt.UserRole, (src, rot))
            it.setIcon(self._icon_for(src, rot))
        self._after_change()

    def delete_selected(self) -> None:
        for r in reversed(self.selected_rows()):
            self.takeItem(r)
        self._after_change()

    def duplicate_selected(self) -> None:
        for r in reversed(self.selected_rows()):
            it = self.item(r)
            src, rot = it.data(Qt.UserRole)
            new = QListWidgetItem(it.text())
            new.setTextAlignment(Qt.AlignHCenter)
            new.setData(Qt.UserRole, (src, rot))
            new.setIcon(self._icon_for(src, rot))
            self.insertItem(r + 1, new)
        self._after_change()

    def move_selected(self, delta: int) -> None:
        rows = self.selected_rows()
        if not rows or (delta < 0 and rows[0] == 0) or (delta > 0 and rows[-1] == self.count() - 1):
            return
        for r in (rows if delta < 0 else reversed(rows)):
            it = self.takeItem(r)
            self.insertItem(r + delta, it)
            it.setSelected(True)
        self._after_change()

    def _after_change(self) -> None:
        # Label = new position; tooltip keeps the original number.
        for r in range(self.count()):
            it = self.item(r)
            src, rot = it.data(Qt.UserRole)
            it.setText(str(r + 1))
            it.setToolTip(f"Original page {src + 1}" + (f", rotated {rot}°" if rot else ""))
        self.plan_changed.emit()

    def closeEvent(self, e):
        self.stop_loading()
        super().closeEvent(e)


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
