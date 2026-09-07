"""底部样本缩略图条（可折叠面板，归属图片列表）。

横向一行，由左至右（折叠箭头悬浮在顶部中央）：
                    ^
    ┌─────────┬─────────┬───────────────────────────────┐
    │ [▽ 筛选] │ [＋]     │   ◻ ◻ ◻ ◻(当前青绿高亮)    …  │
    └─────────┴─────────┴───────────────────────────────┘

职责：
    - 展示共享样本池（:class:`RuntimeSession`）全部样本的缩略图；
    - 左侧「标签筛选」按钮：点击弹出筛选面板，按标签过滤底图；
    - 左侧「添加图片」按钮：与筛选按钮同尺寸，触发宿主添加图片；
    - 顶部中央「^」按钮：折叠 / 展开整个面板；
    - 无样本时显示空态引导，保证图片列表始终可见、可用。

说明：「缩放按钮」仍在左侧工具条底部（见
:class:`~ui.tools.workbench.AnnotationWorkbench`）。
"""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.tools.view_common import label_color

_THUMB = 136        # 缩略图显示宽度
_THUMB_H = 70     # 缩略图显示高度（居中裁剪填满，避免全景图留下空白）
_EXPAND_H = 128     # 展开时面板高度
_COLLAPSE_H = 34    # 折叠时面板高度（仅折叠按钮）


def _cover_crop(pm: QPixmap, w: int, h: int) -> QPixmap:
    """居中裁剪填满 w×h（cover），保证缩略图填满单元格高度，无留白。"""
    if pm.width() == 0 or pm.height() == 0:
        return QPixmap()
    scaled = pm.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - w) // 2)
    y = max(0, (scaled.height() - h) // 2)
    return scaled.copy(x, y, w, h)


_STYLE = """
SampleStrip { background: #FFFFFF; border-top: 1px solid #E2E8F0; }
QListWidget { border: none; background: transparent; outline: none;
  font-size: 11px; }
QListWidget::item { border: 2px solid transparent; border-radius: 6px;
  background: #FFFFFF; margin-right: 8px; padding: 2px; }
QListWidget::item:hover { border: 2px solid #CBD5E1; }
QListWidget::item:selected { border: 2px solid #14B8A6; background: #FFFFFF;
  color: #0F172A; }
QListWidget::item { color: #334155; }

/* 左侧「标签筛选 / 添加图片」按钮（与缩略图同尺寸） */
QPushButton#cellbtn { border: 1px solid #CBD5E1; border-radius: 6px;
  background: #FFFFFF; font-size: 12px; font-weight: 600; color: #334155; }
QPushButton#cellbtn:hover { background: #F1F5F9; color: #0F172A; }
QPushButton#cellbtn:focus { outline: none; }
QPushButton#celladd { border: 1px dashed #CBD5E1; border-radius: 6px;
  background: #FFFFFF; font-size: 26px; color: #64748B; }
QPushButton#celladd:hover { background: #F1F5F9; color: #0F172A; }
QPushButton#celladd:focus { outline: none; }

/* 顶部中央折叠按钮（悬浮，覆盖在条的上缘） */
QPushButton#fold { border: none; background: transparent; color: #94A3B8;
  font-size: 13px; padding: 0; }
QPushButton#fold:hover { color: #0F172A; }
"""


class SampleStrip(QWidget):
    """横向样本缩略图条（标签筛选 + 添加图片 + 缩略图，可折叠）。"""

    # 用户点选了某个样本 → 上报其在 session.samples 中的索引
    sample_activated = pyqtSignal(int)

    def __init__(self, ws, parent=None) -> None:
        super().__init__(parent)
        self.ws = ws
        self.session = ws.session
        # 标签筛选（"" = 不过滤/全部）
        self.filter_label: str = ""
        # 当前可见项对应的 session 索引（过滤后）
        self._visible_idx: List[int] = []
        self._expanded = True
        self._filter_panel: QFrame | None = None
        self._filter_tree: QTreeWidget | None = None
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.setStyleSheet(_STYLE)
        self.setFixedHeight(_EXPAND_H)

        root = QHBoxLayout(self)
        root.setContentsMargins(45, 10, 6, 10)
        root.setSpacing(8)

        # 内容容器：筛选按钮 + 添加按钮 + 缩略图列表
        self._content = QWidget()
        row = QHBoxLayout(self._content)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        # 标签筛选按钮（打开筛选面板）
        self.btn_filter = QPushButton()
        self.btn_filter.setObjectName("cellbtn")
        self.btn_filter.setFixedSize(_THUMB, _THUMB_H)
        self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.setToolTip("按标签筛选图片列表")
        self.btn_filter.clicked.connect(self._show_filter_panel)
        row.addWidget(self.btn_filter)

        # 添加图片按钮
        self.btn_add = QPushButton("＋")
        self.btn_add.setObjectName("celladd")
        self.btn_add.setFixedSize(_THUMB, _THUMB_H)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setToolTip("向样本池添加图片")
        self.btn_add.clicked.connect(self.ws.add_samples_dialog)
        row.addWidget(self.btn_add)

        # 中：横向缩略图（无样本时切换为空态引导页）
        self._stack = QStackedWidget()

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setFlow(QListWidget.Flow.LeftToRight)
        self.list.setWrapping(False)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setSpacing(0)
        self.list.setIconSize(QSize(_THUMB, _THUMB_H))
        self.list.setGridSize(QSize(_THUMB + 16, _THUMB_H + 18))
        self.list.setWordWrap(False)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(self._on_row)
        self._stack.addWidget(self.list)

        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.setContentsMargins(16, 0, 16, 0)
        self.empty_label = QLabel(
            "尚无样本 —— 点击左侧「＋ 添加图片」，"
            "或先在左侧流程运行「加载图片」选择文件夹"
        )
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("font-size: 12px; color: #94A3B8;")
        ev.addWidget(self.empty_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self._stack.addWidget(empty)

        row.addWidget(self._stack, 1)
        root.addWidget(self._content, 1)

        # 折叠 / 展开按钮：覆盖在缩略图列表上方中央（不入布局，手动定位）
        self.btn_fold = QPushButton("^", self)
        self.btn_fold.setObjectName("fold")
        self.btn_fold.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fold.setToolTip("折叠 / 展开图片面板")
        self.btn_fold.setFixedSize(34, 16)
        self.btn_fold.clicked.connect(self._toggle_fold)
        QTimer.singleShot(0, self._reposition_fold)

    # ------------------------------------------------------------------ #
    # 数据刷新
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """重建缩略图、筛选按钮文字与筛选面板（样本/标签/筛选变化后调用）。"""
        s = self.session
        filter_lb = (self.filter_label or "").strip()

        # 缩略图
        self.list.blockSignals(True)
        self.list.clear()
        self._visible_idx = []
        for i, sm in enumerate(s.samples):
            if filter_lb:
                if not any(a.label == filter_lb for a in sm.annotations):
                    continue
            self._visible_idx.append(i)
            item = QListWidgetItem()
            pm = QPixmap(sm.path)
            if not pm.isNull():
                item.setIcon(QIcon(_cover_crop(pm, _THUMB, _THUMB_H)))
            manual = len(sm.manual_annotations())
            auto = len(sm.auto_annotations())
            badge = f"●{manual}" if manual else (f"A{auto}" if auto else "")
            item.setText(f"{sm.name} {badge}" if badge else sm.name)
            item.setToolTip(
                f"{sm.path}\n人工 {manual} · AI {auto} · 状态 {sm.status}"
            )
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(item)
        self.list.blockSignals(False)

        # 有样本 → 缩略图页；无样本 → 空态引导页（列表区域仍可见）
        self._stack.setCurrentIndex(0 if self._visible_idx else 1)

        # 若当前筛选标签已被删除 → 回落到「全部」
        if filter_lb and filter_lb not in s.labels:
            self.filter_label = ""

        self._refresh_filter_button()
        self._refresh_filter_panel()
        self.set_current_index(s.current_index)

    def _refresh_filter_button(self) -> None:
        """刷新「标签筛选」按钮文字。"""
        text = self.filter_label or "所有类别"
        self.btn_filter.setText(f"▽ {text}")

    def set_current_index(self, index: int) -> None:
        """按 session 索引高亮当前样本（若被当前类别过滤则不高亮）。"""
        if index in self._visible_idx:
            row = self._visible_idx.index(index)
            self.list.blockSignals(True)
            self.list.setCurrentRow(row)
            self.list.blockSignals(False)
        else:
            self.list.blockSignals(True)
            if self.list.currentRow() >= 0:
                self.list.clearSelection()
                self.list.setCurrentRow(-1)
            self.list.blockSignals(False)

    # ------------------------------------------------------------------ #
    # 折叠 / 展开
    # ------------------------------------------------------------------ #
    def _toggle_fold(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self.btn_fold.setText("^" if self._expanded else "v")
        self.btn_fold.setToolTip("折叠 / 展开图片面板")
        self.setFixedHeight(_EXPAND_H if self._expanded else _COLLAPSE_H)
        QTimer.singleShot(0, self._reposition_fold)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # 布局变更在 resize 之后才生效，延迟到本帧结束再定位
        QTimer.singleShot(0, self._reposition_fold)

    def _reposition_fold(self) -> None:
        """把折叠按钮置于缩略图列表上方中央（折叠时居中于整条）。"""
        if self.btn_fold is None:
            return
        w = self.btn_fold.width()
        if self._expanded:
            tg = self._stack.mapTo(self, QPoint(0, 0))
            left, span = tg.x(), self._stack.width()
        else:
            left, span = 0, self.width()
        self.btn_fold.move(max(4, left + span // 2 - w // 2), 0)
        self.btn_fold.raise_()

    # ------------------------------------------------------------------ #
    # 标签筛选弹出面板
    # ------------------------------------------------------------------ #
    def _show_filter_panel(self) -> None:
        if self._filter_panel is None:
            self._filter_panel = self._build_filter_panel()
        self._refresh_filter_panel()
        self._filter_panel.adjustSize()
        h = self._filter_panel.height()
        pos = self.btn_filter.mapToGlobal(QPoint(0, -h - 8))
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            pos.setX(max(geo.left() + 8, pos.x()))
        self._filter_panel.move(pos)
        self._filter_panel.show()

    def _build_filter_panel(self) -> QFrame:
        """构建弹出筛选面板（类别名称 + 图片数量），Qt.Popup 点击外部自动关闭。"""
        panel = QFrame()
        panel.setWindowFlag(Qt.WindowType.Popup)
        panel.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 1px solid #E2E8F0;"
            " border-radius: 8px; }"
            "QLabel#ftitle { font-size: 12px; font-weight: 700; color: #0F172A; }"
            "QPushButton#fclear { border: none; background: transparent;"
            " color: #14B8A6; font-size: 12px; padding: 2px 6px; }"
            "QPushButton#fclear:hover { color: #0D9488; }"
            "QTreeWidget { border: none; background: transparent;"
            " outline: none; font-size: 12px; color: #334155; }"
            "QTreeWidget::item { height: 26px; padding: 0 4px; }"
            "QTreeWidget::item:hover { background: #F1F5F9; }"
            "QTreeWidget::item:selected { background: #CCFBF1; color: #0F766E; }"
            "QHeaderView::section { border: none; border-bottom: 1px solid #E2E8F0;"
            " background: #FFFFFF; color: #94A3B8; font-size: 11px;"
            " padding: 2px 4px; }"
        )
        v = QVBoxLayout(panel)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(6)
        title = QLabel("类别筛选")
        title.setObjectName("ftitle")
        head.addWidget(title)
        head.addStretch()
        clear = QPushButton("清除")
        clear.setObjectName("fclear")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.setToolTip("清除筛选（显示全部样本）")
        clear.clicked.connect(self._clear_filter)
        head.addWidget(clear)
        v.addLayout(head)

        tree = QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderLabels(["类别名称", "图片数量"])
        tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        tree.setRootIsDecorated(False)
        tree.setIndentation(0)
        tree.setFixedWidth(210)
        tree.setFixedHeight(200)
        tree.itemClicked.connect(self._on_filter_item)
        self._filter_tree = tree
        v.addWidget(tree)

        return panel

    def _refresh_filter_panel(self) -> None:
        """重建筛选面板中的标签行（名称 + 用量 + 选中态）。"""
        if self._filter_tree is None:
            return
        self._filter_tree.clear()
        all_item = QTreeWidgetItem(["全部样本", str(len(self.session.samples))])
        all_item.setData(0, Qt.ItemDataRole.UserRole, "")
        self._filter_tree.addTopLevelItem(all_item)

        for lb in self.session.labels:
            usage = sum(
                1 for s in self.session.samples
                for a in s.annotations if a.label == lb
            )
            item = QTreeWidgetItem([lb, str(usage)])
            color = label_color(lb)
            item.setForeground(
                0, color if self.filter_label == lb else Qt.GlobalColor.black)
            item.setData(0, Qt.ItemDataRole.UserRole, lb)
            self._filter_tree.addTopLevelItem(item)

        # 标记当前选中
        for i in range(self._filter_tree.topLevelItemCount()):
            it = self._filter_tree.topLevelItem(i)
            if (it.data(0, Qt.ItemDataRole.UserRole) or "") == self.filter_label:
                self._filter_tree.setCurrentItem(it)
                break

    def _on_filter_item(self, item: QTreeWidgetItem, _col: int) -> None:
        self.filter_label = item.data(0, Qt.ItemDataRole.UserRole) or ""
        self._close_filter_panel()
        self.refresh()

    def _clear_filter(self) -> None:
        self.filter_label = ""
        self._close_filter_panel()
        self.refresh()

    def _close_filter_panel(self) -> None:
        if self._filter_panel is not None:
            self._filter_panel.hide()

    # ------------------------------------------------------------------ #
    def _on_row(self, row: int) -> None:
        if 0 <= row < len(self._visible_idx):
            self.sample_activated.emit(self._visible_idx[row])
