"""工具依赖流程图。

基于 Qt 视图系统（QGraphicsView / QGraphicsScene / QGraphicsItem）绘制
标注工具之间的依赖关系：
    工具基类 (ToolBase)  ──►  三个工具组  ──►  各具体标注工具

交互：
    - 单击工具节点  → 发射 tool_clicked 信号（主窗口据此打开工具基类界面）
    - 单击/框选节点 → 选中高亮
    - 滚轮缩放、中键拖拽平移、双击空白适应视图
"""
from __future__ import annotations

import math
from typing import Dict, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QStyle,
)

from alg.tools_registry import TOOL_GROUPS, get_tools_by_group

# ---------------------------------------------------------------------- #
# 常量与配色
# ---------------------------------------------------------------------- #
NODE_W = 156.0
NODE_H = 52.0

GROUP_COLORS: Dict[str, QColor] = {
    "通用工具": QColor("#0EA5E9"),
    "YOLO工具": QColor("#F59E0B"),
    "Paddle工具": QColor("#10B981"),
}

_BG_COLOR = QColor("#F1F5F9")
_EDGE_COLOR = QColor("#94A3B8")


# ---------------------------------------------------------------------- #
# 流程节点
# ---------------------------------------------------------------------- #
class FlowNodeItem(QGraphicsItem):
    """流程图中的节点：圆角矩形 + 标题 + 副标题。"""

    def __init__(
        self,
        node_id: str,
        title: str,
        subtitle: str = "",
        node_type: str = "tool",  # base / group / tool
        tool_id: Optional[str] = None,
        accent: Optional[QColor] = None,
    ) -> None:
        super().__init__()
        self.node_id = node_id
        self.title = title
        self.subtitle = subtitle
        self.node_type = node_type
        self.tool_id = tool_id
        self.accent = accent or QColor("#2563EB")
        self._hovered = False
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

    # -- 几何 -- #
    def boundingRect(self) -> QRectF:
        return QRectF(-NODE_W / 2, -NODE_H / 2, NODE_W, NODE_H)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self.boundingRect(), 9, 9)
        return path

    def center(self) -> QPointF:
        return self.scenePos()

    def bottom_anchor(self) -> QPointF:
        return QPointF(self.center().x(), self.center().y() + NODE_H / 2)

    def top_anchor(self) -> QPointF:
        return QPointF(self.center().x(), self.center().y() - NODE_H / 2)

    # -- 样式 -- #
    def _palette(self):
        if self.node_type == "base":
            return QColor("#2563EB"), QColor("#1D4ED8"), QColor("#FFFFFF")
        if self.node_type == "group":
            return QColor("#FFFFFF"), QColor("#CBD5E1"), QColor("#1E293B")
        # tool
        return QColor("#EFF6FF"), QColor("#BFDBFE"), QColor("#1E293B")

    # -- 绘制 -- #
    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill, border, text_color = self._palette()
        rect = self.boundingRect().adjusted(1.5, 1.5, -1.5, -1.5)

        # 阴影
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 34))
        painter.drawRoundedRect(QRectF(rect.x() + 2, rect.y() + 3, rect.width(), rect.height()), 9, 9)

        # 主体
        painter.setBrush(fill)
        pen = QPen(border, 1.4)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 9, 9)

        # 选中 / 悬停高亮
        hovered = self._hovered or (
            option.state & QStyle.StateFlag.State_Selected
        )
        if hovered:
            painter.setPen(QPen(self.accent, 2.4))
            painter.drawRoundedRect(rect, 9, 9)
            painter.setPen(QPen(QColor(255, 255, 255, 40), 0))
            painter.setBrush(QColor(255, 255, 255, 28))
            painter.drawRoundedRect(rect, 9, 9)

        # 分组节点的左侧色条
        if self.node_type == "group":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.accent)
            painter.drawRoundedRect(
                QRectF(rect.x(), rect.y() + 4, 5, rect.height() - 8), 2, 2
            )

        # 标题
        title_font = QFont("Microsoft YaHei", 9)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(text_color)
        title_rect = QRectF(
            rect.x() + 6, rect.y() + (4 if self.subtitle else 8),
            rect.width() - 12, 20,
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self.title)

        # 副标题
        if self.subtitle:
            sub_font = QFont("Microsoft YaHei", 8)
            painter.setFont(sub_font)
            painter.setPen(QColor("#64748B"))
            sub_rect = QRectF(
                rect.x() + 6, rect.y() + 26, rect.width() - 12, 16
            )
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, self.subtitle)

    # -- 悬停 -- #
    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)


# ---------------------------------------------------------------------- #
# 连接箭头
# ---------------------------------------------------------------------- #
class ArrowItem(QGraphicsItem):
    """带箭头的三次贝塞尔曲线连线。"""

    def __init__(
        self,
        start: QPointF,
        end: QPointF,
        color: QColor = _EDGE_COLOR,
        width: float = 1.8,
    ) -> None:
        super().__init__()
        self._start = QPointF(start)
        self._end = QPointF(end)
        self._color = color
        self._width = width
        self.setZValue(-10)

    def boundingRect(self) -> QRectF:
        return QRectF(self._start, self._end).normalized().adjusted(-14, -14, 14, 14)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color, self._width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(self._color)

        path = QPainterPath(self._start)
        path.cubicTo(
            self._start.x(), self._start.y() + 16,
            self._end.x(), self._end.y() - 16,
            self._end.x(), self._end.y(),
        )
        painter.drawPath(path)

        # 箭头头部（沿终点切线方向）
        near = path.pointAtPercent(0.88)
        dx, dy = self._end.x() - near.x(), self._end.y() - near.y()
        length = math.hypot(dx, dy) or 1.0
        angle = math.atan2(dy / length, dx / length)
        spread = 0.45
        tip_len = 11.0
        arrow = QPolygonF(
            [
                self._end,
                self._end - QPointF(math.cos(angle - spread), math.sin(angle - spread)) * tip_len,
                self._end - QPointF(math.cos(angle + spread), math.sin(angle + spread)) * tip_len,
            ]
        )
        painter.drawPolygon(arrow)


# ---------------------------------------------------------------------- #
# 依赖流程图视图
# ---------------------------------------------------------------------- #
class ToolFlowView(QGraphicsView):
    """工具依赖流程图视图。"""

    # 工具节点被单击时发射 (tool_id, tool_name)
    tool_clicked = pyqtSignal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._nodes: Dict[str, FlowNodeItem] = {}
        self._panning = False
        self._pan_start = QPointF()
        self._fitted = False

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
        )
        self.setBackgroundBrush(_BG_COLOR)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setMouseTracking(True)

        self._build_graph()

    # ------------------------------------------------------------------ #
    # 构建图
    # ------------------------------------------------------------------ #
    def _create_node(
        self,
        node_id: str,
        title: str,
        subtitle: str,
        node_type: str,
        accent: Optional[QColor] = None,
    ) -> FlowNodeItem:
        tool_id = node_id if node_type in ("base", "tool") else None
        node = FlowNodeItem(
            node_id=node_id,
            title=title,
            subtitle=subtitle,
            node_type=node_type,
            tool_id=tool_id,
            accent=accent,
        )
        self._scene.addItem(node)
        self._nodes[node_id] = node
        return node

    def _connect(self, src: FlowNodeItem, dst: FlowNodeItem) -> None:
        self._scene.addItem(ArrowItem(src.bottom_anchor(), dst.top_anchor()))

    def _build_graph(self) -> None:
        # 第 1 层：工具基类
        base = self._create_node(
            "tool_base", "工具基类", "ToolBase", node_type="base"
        )
        base.setPos(0, 40)

        # 第 2 层：三个工具组
        group_x = [-252, 0, 252]
        group_nodes = []
        for i, g in enumerate(TOOL_GROUPS):
            accent = GROUP_COLORS.get(g["name"], QColor("#0EA5E9"))
            node = self._create_node(
                f"group:{g['name']}", g["name"], g["description"],
                node_type="group", accent=accent,
            )
            node.setPos(group_x[i], 230)
            self._connect(base, node)
            group_nodes.append((g, node))

        # 第 3 层：各工具（按注册顺序单列排列，subtitle 显示分类）
        for g, gnode in group_nodes:
            tools = get_tools_by_group(g["name"])
            accent = GROUP_COLORS.get(g["name"], QColor("#0EA5E9"))
            for i, t in enumerate(tools):
                node = self._create_node(
                    t["id"], t["name"], t["category"],
                    node_type="tool", accent=accent,
                )
                node.setPos(
                    gnode.pos().x(),
                    gnode.pos().y() + 130 + i * 92,
                )
                self._connect(gnode, node)

        self._scene.setSceneRect(
            self._scene.itemsBoundingRect().adjusted(-140, -100, 140, 120)
        )

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
    def _node_at(self, pos) -> Optional[FlowNodeItem]:
        item = self.itemAt(pos)
        return item if isinstance(item, FlowNodeItem) else None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            node = self._node_at(event.position().toPoint())
            if node is not None and node.node_type in ("base", "tool"):
                # 单击工具/基类节点 → 跳转工具基类界面
                self.tool_clicked.emit(node.tool_id, node.title)
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            node = self._node_at(event.position().toPoint())
            if node is None:
                # 双击空白 → 适应视图
                self.fit_graph()
                return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    # ------------------------------------------------------------------ #
    # 视图辅助
    # ------------------------------------------------------------------ #
    def fit_graph(self) -> None:
        self.fitInView(
            self._scene.itemsBoundingRect().adjusted(-140, -100, 140, 120),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            self.fit_graph()

    def contextMenuEvent(self, event) -> None:
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        act_fit = menu.addAction("适应视图")
        act_zoom_in = menu.addAction("放大")
        act_zoom_out = menu.addAction("缩小")
        chosen = menu.exec(event.globalPos())
        if chosen == act_fit:
            self.fit_graph()
        elif chosen == act_zoom_in:
            self.scale(1.2, 1.2)
        elif chosen == act_zoom_out:
            self.scale(1.0 / 1.2, 1.0 / 1.2)
