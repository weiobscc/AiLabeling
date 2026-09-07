"""图像标注画布（自绘 QWidget）。

能力：
    - 显示原图并支持滚轮缩放、中键平移、适应窗口（F）
    - 左键拖拽在图像坐标系内绘制矩形框（通过 sig_new_box 上报）
    - 叠加显示已有标注 / AI 候选框（Overlay 由外部传入，颜色区分来源）
    - 单击选中、双击或 Del 删除可编辑框（locked 框不可删）

坐标约定：一切几何量（绘制、上报）均为**原图像素坐标**，由视图变换
（scale/offset）与控件坐标互转，保证数据层只存原图坐标。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

_BG = QColor("#F1F5F9")
_MIN_SCALE = 0.02
_MAX_SCALE = 64.0


@dataclass
class Overlay:
    """画布上叠加显示的一个框（图像像素坐标系）。"""

    rect: QRectF
    color: QColor
    label: str
    locked: bool = False
    annotation: Any = None  # 关联的 Annotation（供删除/编辑回写）


class ImageCanvas(QWidget):
    """可缩放平移的标注画布。"""

    sig_new_box = pyqtSignal(str, object)  # label(页面后填), QRectF
    sig_delete_annotation = pyqtSignal(object)  # Annotation
    sig_zoom_changed = pyqtSignal(float)  # 缩放倍率变化（用于工具条显示 %）

    # 工具模式："select"（仅选择） / "rect"（拖拽画框）
    TOOL_SELECT = "select"
    TOOL_RECT = "rect"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._overlays: List[Overlay] = []
        self._selected: Optional[Overlay] = None
        self._tool = self.TOOL_RECT

        # 视图参数：图像 (0,0) 在控件中的位置 offset，放大倍数 scale
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._auto_fit = True

        # 拖拽画框 / 平移状态
        self._pressed = False
        self._panning = False
        self._press_pos = QPointF()
        self._last_pos = QPointF()
        self._draw_start: Optional[QPointF] = None  # 图像坐标
        self._draw_rect: Optional[QRectF] = None

        self._label_provider = lambda: ""  # 供页面注入，决定新框的默认标签
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumSize(320, 240)

    def set_label_provider(self, provider) -> None:
        """注入新建矩形时的标签获取回调。"""
        self._label_provider = provider

    def set_tool(self, tool: str) -> None:
        """设置交互工具模式：'select' 仅选择，'rect' 拖拽画框。"""
        if tool not in (self.TOOL_SELECT, self.TOOL_RECT):
            return
        self._tool = tool
        self._draw_start = None
        self._draw_rect = None
        self.update()

    # ------------------------------------------------------------------ #
    # 图像与叠加层
    # ------------------------------------------------------------------ #
    def set_image_path(self, path: str) -> bool:
        """加载图像；失败返回 False（保留原图）。"""
        if not path:
            self._pixmap = None
            self._overlays = []
            self._selected = None
            self._auto_fit = True
            self.update()
            return False
        pm = QPixmap(path)
        if pm.isNull():
            return False
        self._pixmap = pm
        self._selected = None
        self.fit_image()  # 每次切换图像都重新适应窗口
        self.update()
        return True

    def image_size(self) -> tuple:
        if self._pixmap is not None:
            return self._pixmap.width(), self._pixmap.height()
        return (0, 0)

    def set_overlays(self, overlays: List[Overlay]) -> None:
        """设置叠加框列表（含人工 + AI）。自动清理失效选择。"""
        self._overlays = list(overlays)
        if self._selected is not None and self._selected not in self._overlays:
            self._selected = None
        self.update()

    # ------------------------------------------------------------------ #
    # 视图变换
    # ------------------------------------------------------------------ #
    def fit_image(self) -> None:
        """整体适应控件可视区域（留边距）。"""
        if self._pixmap is None or self.width() < 8 or self.height() < 8:
            return
        pw, ph = self._pixmap.width(), self._pixmap.height()
        margin = 24.0
        scale = min(
            (self.width() - margin) / pw,
            (self.height() - margin) / ph,
        )
        scale = max(0.05, min(scale, 8.0))
        self._scale = scale
        self._offset = QPointF(
            (self.width() - pw * scale) / 2.0,
            (self.height() - ph * scale) / 2.0,
        )
        self._auto_fit = False
        self.update()
        self.sig_zoom_changed.emit(self._scale)

    def _zoom_at(self, factor: float, anchor: QPointF) -> None:
        old = self._scale
        new = max(_MIN_SCALE, min(old * factor, _MAX_SCALE))
        if abs(new - old) < 1e-6:
            return
        img_x = (anchor.x() - self._offset.x()) / old
        img_y = (anchor.y() - self._offset.y()) / old
        self._scale = new
        self._offset = QPointF(
            anchor.x() - img_x * new, anchor.y() - img_y * new
        )
        self._auto_fit = False
        self.update()
        self.sig_zoom_changed.emit(self._scale)

    def zoom_in(self) -> None:
        """以控件中心放大一拍。"""
        if self._pixmap is None:
            return
        self._zoom_at(
            1.18, QPointF(self.width() / 2.0, self.height() / 2.0)
        )

    def zoom_out(self) -> None:
        """以控件中心缩小一拍。"""
        if self._pixmap is None:
            return
        self._zoom_at(
            1.0 / 1.18, QPointF(self.width() / 2.0, self.height() / 2.0)
        )

    def _w2i(self, pos: QPointF) -> QPointF:
        return QPointF(
            (pos.x() - self._offset.x()) / self._scale,
            (pos.y() - self._offset.y()) / self._scale,
        )

    def _image_rect(self) -> Optional[QRectF]:
        if self._pixmap is None:
            return None
        return QRectF(0, 0, self._pixmap.width(), self._pixmap.height())

    # ------------------------------------------------------------------ #
    # 命中检测
    # ------------------------------------------------------------------ #
    def _overlay_at(self, pos: QPointF) -> Optional[Overlay]:
        if self._pixmap is None:
            return None
        img = self._w2i(pos)
        for ov in reversed(self._overlays):
            if ov.rect.contains(img):
                return ov
        return None

    # ------------------------------------------------------------------ #
    # 鼠标 / 键盘事件
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event) -> None:
        self.setFocus()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._press_pos = event.position()
            self._draw_rect = None
            self._draw_start = None
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position() - self._last_pos
            self._last_pos = event.position()
            self._offset += delta
            self._auto_fit = False
            self.update()
            event.accept()
            return
        if self._pressed and self._tool == self.TOOL_RECT:
            if self._draw_start is None:
                if (event.position() - self._press_pos).manhattanLength() >= 6:
                    self._draw_start = self._w2i(self._press_pos)
            if self._draw_start is not None:
                cur = self._w2i(event.position())
                self._draw_rect = QRectF(self._draw_start, cur).normalized()
                self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            if self._draw_rect is not None and self._draw_start is not None:
                rect = self._draw_rect
                self._draw_rect = None
                self._draw_start = None
                self._commit_rect(rect)
                event.accept()
                return
            self._draw_start = None
            self._select_overlay(event.position())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            ov = self._overlay_at(event.position())
            if ov is not None and not ov.locked:
                self.sig_delete_annotation.emit(ov.annotation)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:
        if self._pixmap is None:
            event.accept()
            return
        step = event.angleDelta().y()
        if step == 0:
            return
        factor = 1.18 if step > 0 else 1.0 / 1.18
        self._zoom_at(factor, event.position())
        event.accept()

    def keyPressEvent(self, event) -> None:
        if (
            event.key() == Qt.Key.Key_Delete
            and self._selected is not None
            and not self._selected.locked
        ):
            ann = self._selected.annotation
            self._selected = None
            self.update()
            self.sig_delete_annotation.emit(ann)
            event.accept()
            return
        if event.key() == Qt.Key.Key_F:
            self.fit_image()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._auto_fit:
            self.fit_image()

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _commit_rect(self, rect: QRectF) -> None:
        img = self._image_rect()
        if img is None or rect.width() < 6 or rect.height() < 6:
            return
        rect = rect.intersected(img)
        if rect.width() < 6 or rect.height() < 6:
            return
        self.sig_new_box.emit(self._label_provider() or "", rect)

    def _select_overlay(self, pos: QPointF) -> None:
        self._selected = self._overlay_at(pos)
        self.update()

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), _BG)

        if self._pixmap is None:
            painter.setPen(QColor("#94A3B8"))
            font = QFont("Microsoft YaHei", 11)
            painter.setFont(font)
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "暂无图像\n在底部样本条中点击一张图片开始标注\n"
                "拖拽画框 · 双击删除 · 滚轮缩放 · 中键平移 · F 适应窗口",
            )
            return

        # 图像
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.save()
        painter.translate(self._offset)
        painter.scale(self._scale, self._scale)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.restore()

        # 叠加层（含进行中矩形）
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.save()
        painter.translate(self._offset)
        painter.scale(self._scale, self._scale)
        for ov in self._overlays:
            self._paint_overlay(painter, ov)
        if self._draw_rect is not None:
            pen = QPen(QColor("#2563EB"), 2.0 / self._scale, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QColor(37, 99, 235, 46))
            painter.drawRect(self._draw_rect)
        painter.restore()

        # 提示栏
        painter.setPen(QColor("#94A3B8"))
        font = QFont("Microsoft YaHei", 8)
        painter.setFont(font)
        painter.drawText(
            10, self.height() - 8,
            "拖拽画框 · 双击/Del 删除 · 滚轮缩放 · 中键平移 · F 适应",
        )

    def _paint_overlay(self, painter: QPainter, ov: Overlay) -> None:
        selected = ov is self._selected
        color = ov.color
        if selected:
            pen = QPen(QColor("#0F172A"), 3.2 / self._scale)
        else:
            pen = QPen(color, 2.0 / self._scale)
        painter.setPen(pen)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 34))
        painter.drawRect(ov.rect)

        # 标签角标
        font = QFont("Microsoft YaHei", 11)
        painter.setFont(font)
        text = ov.label or "?"
        tw = painter.fontMetrics().horizontalAdvance(text) + 16.0 / self._scale
        th = painter.fontMetrics().height()
        label_rect = QRectF(
            ov.rect.x(), ov.rect.y() - th + 4.0 / self._scale,
            max(tw, ov.rect.width()), th,
        )
        if label_rect.y() < 0:
            label_rect.moveTop(ov.rect.y() + 4.0 / self._scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(label_rect, 2, 2)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)
