"""矩形框人工标注页（rect_label），基于工作台基类。

在本页对一个样本：
    - 拖拽绘制人工框（蓝色，producer=manual）
    - 叠加显示 AI 预标注框（红色，可开关，不能在此删除）
    - 双击 / Del 删除人工框
    - 上/下一张切换样本

布局沿用参考工作台：最左竖排工具条、中央画布、右侧「图片信息」
面板（标签管理）、底部横向样本条。
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.schema import PRODUCER_MANUAL, Sample
from ui.tools.image_canvas import ImageCanvas
from ui.tools.view_common import build_overlays, label_color, sample_summary
from ui.tools.workbench import AnnotationWorkbench

_BTN = """
QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px;
  padding: 3px 10px; font-size: 12px; color: #334155; }
QPushButton:hover { background: #F1F5F9; }
QPushButton:disabled { color: #CBD5E1; }
"""

_LIST_STYLE = """
QListWidget { border: 1px solid #E2E8F0; border-radius: 6px;
  background: #FFFFFF; outline: none; }
QListWidget::item { padding: 4px 6px; font-size: 12px; color: #1E293B;
  border-bottom: 1px solid #F1F5F9; }
QListWidget::item:hover { background: #F8FAFC; }
QListWidget::item:selected { background: #F0FDF4; color: #0F766E; }
"""


class AnnotatePage(AnnotationWorkbench):
    """人工矩形框标注页。"""

    def __init__(self, ws, parent=None) -> None:
        super().__init__(ws, parent)
        self._tool_name = "矩形框标注"
        self._labels_synced = 0
        # 先建面板页（含 label_combo），供 _build_content 填充类别建议使用
        self.populate_param_panel(self.param_body)
        self._build_content()
        self.refresh()

    # ------------------------------------------------------------------ #
    # 中央内容（工具条 + 画布）
    # ------------------------------------------------------------------ #
    def _build_content(self) -> None:
        lay = self.content_lay

        self.title = QLabel("矩形框标注")
        self.title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1E293B;"
        )
        self.title.setToolTip("人工标注：拖拽画蓝框；AI 预标注为红框叠加参考")

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.title)
        bar.addStretch()

        self.btn_prev = QPushButton("◀ 上一张")
        self.btn_next = QPushButton("下一张 ▶")
        for b in (self.btn_prev, self.btn_next):
            b.setStyleSheet(_BTN)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            bar.addWidget(b)

        self.show_auto = QCheckBox("显示 AI 预标注")
        self.show_auto.setChecked(True)
        self.show_auto.setStyleSheet("font-size: 12px; color: #475569;")
        bar.addWidget(self.show_auto)
        lay.addLayout(bar)

        # 画布
        self.canvas = ImageCanvas()
        self.set_canvas(self.canvas)
        lay.addWidget(self.canvas, 1)

        # 接线
        self.canvas.set_label_provider(self._current_label)
        self.canvas.sig_new_box.connect(self._on_new_box)
        self.canvas.sig_delete_annotation.connect(self._on_delete)
        self.btn_prev.clicked.connect(lambda: self._step(-1))
        self.btn_next.clicked.connect(lambda: self._step(1))
        self.show_auto.toggled.connect(self.refresh)

        self._fill_label_suggestions()

    # ------------------------------------------------------------------ #
    # 右侧「图片信息」面板：标签管理（共享 Tab，见 workbench）+ 标注页
    # ------------------------------------------------------------------ #
    def populate_param_panel(self, tabs) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        # 样本信息
        self.sample_info = QLabel("尚无样本")
        self.sample_info.setWordWrap(True)
        self.sample_info.setStyleSheet(
            "font-size: 12px; color: #475569; background: #F8FAFC;"
            " border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;"
        )
        lay.addWidget(self.sample_info)

        # 标注子头
        sub = QHBoxLayout()
        sub.addWidget(QLabel("✔ 标注"))
        sub.addStretch()
        lay.addLayout(sub)

        # 当前激活类别（新框默认标签）
        lb_row = QHBoxLayout()
        lb_row.setSpacing(6)
        lb_row.addWidget(QLabel("类别："))
        self.label_combo = QComboBox()
        self.label_combo.setEditable(True)
        self.label_combo.setMinimumWidth(120)
        self.label_combo.setToolTip("所选类别作为新绘制框的默认标签")
        self.label_combo.setStyleSheet(
            "QComboBox { border: 1px solid #CBD5E1; border-radius: 6px;"
            " padding: 3px 8px; font-size: 12px; background: #FFFFFF; }"
        )
        lb_row.addWidget(self.label_combo, 1)
        lay.addLayout(lb_row)

        self.label_list = QListWidget()
        self.label_list.setStyleSheet(_LIST_STYLE)
        self.label_list.setToolTip("当前样本各类别的框数量（点击设为激活类别）")
        self.label_list.itemClicked.connect(self._on_label_row)
        lay.addWidget(self.label_list, 1)

        tabs.addTab(page, "标注")

    def _on_label_row(self, item: QListWidgetItem) -> None:
        """点击类别行 → 设为当前激活类别。"""
        text = item.data(Qt.ItemDataRole.UserRole)
        if text:
            self.label_combo.setCurrentText(text)

    # ------------------------------------------------------------------ #
    # 数据访问
    # ------------------------------------------------------------------ #
    def _current(self) -> Optional[Sample]:
        return self.session.current()

    def _fill_label_suggestions(self) -> None:
        """用会话收集到的类别填充下拉建议（保留当前选择）。"""
        current = self.label_combo.currentText() if self.label_combo.count() else ""
        self.label_combo.clear()
        self.session.collect_labels()
        for lb in self.session.labels:
            self.label_combo.addItem(lb)
        if current:
            self.label_combo.setCurrentText(current)
        elif self.session.labels:
            self.label_combo.setCurrentText(self.session.labels[0])

    def _current_label(self) -> str:
        text = self.label_combo.currentText().strip()
        return text or "object"

    def _sync_label_combo(self) -> None:
        """类别集合变化时才刷新下拉（避免打断输入）。"""
        self.session.collect_labels()
        if len(self.session.labels) == self._labels_synced:
            return
        self._labels_synced = len(self.session.labels)
        self._fill_label_suggestions()

    def _populate_label_list(self) -> None:
        """按当前样本重建右侧类别列表（色块 + 类名 + 数量）。"""
        sample = self._current()
        self.label_list.clear()
        if sample is None:
            return
        counts: dict = {}
        for ann in sample.annotations:
            counts[ann.label] = counts.get(ann.label, 0) + 1
        for lb in self.session.labels:
            if lb not in counts:
                continue
            cnt = counts[lb]
            item = QListWidgetItem(f"● {lb}　{cnt}")
            color = label_color(lb)
            item.setForeground(color)
            item.setData(Qt.ItemDataRole.UserRole, lb)
            self.label_list.addItem(item)

    # ------------------------------------------------------------------ #
    # 标注操作
    # ------------------------------------------------------------------ #
    def _on_new_box(self, label: str, rect) -> None:
        sample = self._current()
        if sample is None:
            return
        x1, y1 = rect.x(), rect.y()
        x2, y2 = x1 + rect.width(), y1 + rect.height()
        self.session.add_manual(
            sample, label=label, rect=(round(x1), round(y1), round(x2), round(y2))
        )
        sample.status = "labeled"
        self.session.observe_labels([label])
        self.refresh()
        self.ws.refresh_all()

    def _on_delete(self, annotation) -> None:
        sample = self._current()
        if sample is None or annotation is None:
            return
        if annotation.producer != PRODUCER_MANUAL:
            return
        sample.remove_annotation(annotation)
        if not sample.manual_annotations():
            sample.status = "pending"
        self.refresh()
        self.ws.refresh_all()

    # ------------------------------------------------------------------ #
    # 导航与刷新
    # ------------------------------------------------------------------ #
    def _step(self, delta: int) -> None:
        if self.session.step(delta):
            self.ws.set_current_sample_index(self.session.current_index)

    def set_tool_info(self, name: str) -> None:
        self._tool_name = name
        self.title.setText(f"{name}")
        self.title.setToolTip("人工标注：拖拽画蓝框；AI 预标注为红框叠加参考")

    def refresh(self) -> None:
        super().refresh()  # 底部样本条
        sample = self._current()
        if sample is None:
            self.canvas.set_image_path("")
            self.sample_info.setText("尚无样本\n请先加载图片文件夹并选择一个样本")
            self._populate_label_list()
            return
        ok = self.canvas.set_image_path(sample.path)
        if not ok:
            self.sample_info.setText(f"无法加载图像：{sample.path}")
            return
        self.canvas.set_overlays(
            build_overlays(sample, show_manual=True, show_auto=self.show_auto.isChecked())
        )
        self._sync_label_combo()
        self._populate_label_list()
        self.sample_info.setText(
            f"{sample.name}（{sample.width}×{sample.height}）\n{sample_summary(sample)}"
        )
