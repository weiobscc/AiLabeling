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
    QCursor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QMenu,
    QMessageBox,
    QStyle,
)

from alg.tools_registry import TOOL_GROUPS, get_tool
from ui.tool_panel import ToolPanel

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
        if self.node_type == "group":
            # 分组节点标题用更大字号
            title_font.setPointSize(10)
        painter.setFont(title_font)
        painter.setPen(text_color)
        if self.node_type == "group":
            # 分组节点只显示组名（居中），描述保留在 tooltip 中
            title_rect = QRectF(
                rect.x() + 6, rect.y() + 4, rect.width() - 12, rect.height() - 8
            )
        else:
            title_rect = QRectF(
                rect.x() + 6, rect.y() + (4 if self.subtitle else 8),
                rect.width() - 12, 20,
            )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self.title)

        # 副标题（分组节点不显示，避免截断）
        if self.subtitle and self.node_type != "group":
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
    """带箭头的三次贝塞尔曲线连线（引用源/目标节点，可随节点移动刷新）。"""

    def __init__(
        self,
        src: "FlowNodeItem",
        dst: "FlowNodeItem",
        color: QColor = _EDGE_COLOR,
        width: float = 1.8,
    ) -> None:
        super().__init__()
        self._src = src
        self._dst = dst
        self._color = color
        self._width = width
        self.setZValue(-10)
        self._start = QPointF()
        self._end = QPointF()
        self.refresh()

    def refresh(self) -> None:
        """根据源/目标节点当前位置重新计算连线。"""
        self.prepareGeometryChange()
        self._start = self._src.bottom_anchor()
        self._end = self._dst.top_anchor()
        self.update()

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
    # 工具被添加到流程中时发射 (tool_id, tool_name)
    tool_added = pyqtSignal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._nodes: Dict[str, FlowNodeItem] = {}
        self._group_node: Dict[str, FlowNodeItem] = {}
        self._group_tool_nodes: Dict[str, list] = {}
        self._hint_item: Optional[QGraphicsSimpleTextItem] = None
        self._picker_panel: Optional[ToolPanel] = None
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
        # 悬停显示工具简单说明
        if tool_id:
            try:
                meta = get_tool(tool_id)
                node.setToolTip(
                    f"<b>{meta['name']}</b>　{meta['category']}<br>"
                    f"{meta['description']}"
                )
            except KeyError:
                pass
        elif node_type == "group":
            node.setToolTip(f"<b>{title}</b><br>{subtitle}")
        self._scene.addItem(node)
        self._nodes[node_id] = node
        return node

    def _connect(self, src: FlowNodeItem, dst: FlowNodeItem) -> ArrowItem:
        arrow = ArrowItem(src, dst)
        self._scene.addItem(arrow)
        return arrow

    def _refresh_arrow(self, src: FlowNodeItem, dst: FlowNodeItem) -> None:
        """刷新某条 src→dst 连线的端点位置。"""
        for item in self._scene.items():
            if isinstance(item, ArrowItem) and item._src is src and item._dst is dst:
                item.refresh()

    def _update_scene_rect(self) -> None:
        self._update_hint()
        self._scene.setSceneRect(
            self._scene.itemsBoundingRect().adjusted(-140, -100, 140, 120)
        )

    def _update_hint(self) -> None:
        """空画布时显示引导提示，出现任何节点后自动移除。"""
        if self._nodes:
            if self._hint_item is not None:
                self._scene.removeItem(self._hint_item)
                self._hint_item = None
        elif self._hint_item is None:
            hint = QGraphicsSimpleTextItem(
                "尚未添加任何工具\n点击「＋ 添加工具」开始\n右键空白处也可选择工具"
            )
            hint.setBrush(QColor("#CBD5E1"))
            font = QFont("Microsoft YaHei", 11)
            hint.setFont(font)
            hint.setPos(-95, -50)
            self._scene.addItem(hint)
            self._hint_item = hint

    def _build_graph(self) -> None:
        # 初始为空画布：工具分组与工具节点均由用户添加后按需创建
        self._update_scene_rect()

    # ------------------------------------------------------------------ #
    # 工具节点增删（右键菜单）
    # ------------------------------------------------------------------ #
    def _group_of_node(self, node: FlowNodeItem) -> Optional[str]:
        """返回节点所属的工具组名。"""
        for gname, nodes in self._group_tool_nodes.items():
            if node in nodes:
                return gname
        return None

    def _ensure_group_node(self, group: str) -> FlowNodeItem:
        """按需创建工具分组节点。

        画布初始为空，首个工具添加时自动创建其所属分组节点；
        分组节点从左到右依次排布，工具随后挂载到分组下方。
        """
        gnode = self._group_node.get(group)
        if gnode is not None:
            return gnode
        accent = GROUP_COLORS.get(group, QColor("#0EA5E9"))
        desc = next(
            (g["description"] for g in TOOL_GROUPS if g["name"] == group), ""
        )
        gnode = self._create_node(
            f"group:{group}", group, desc, node_type="group", accent=accent,
        )
        x = 0.0
        for n in self._group_node.values():
            x = max(x, n.pos().x() + 260.0)
        gnode.setPos(x, 0)
        self._group_node[group] = gnode
        self._group_tool_nodes[group] = []
        return gnode

    def add_tool_to_flow(self, tool_id: str) -> bool:
        """把工具添加到其所属分组末尾（「＋ 添加工具」按钮 / 右键分组菜单）。

        分组节点不存在时自动创建。已在流程中或工具不存在时返回 False。
        """
        if tool_id in self._nodes:
            return False
        try:
            meta = get_tool(tool_id)
        except KeyError:
            return False
        group = meta["group"]
        gnode = self._ensure_group_node(group)
        accent = GROUP_COLORS.get(group, QColor("#0EA5E9"))
        node = self._create_node(
            meta["id"], meta["name"], meta["category"],
            node_type="tool", accent=accent,
        )
        nodes = self._group_tool_nodes[group]
        if nodes:
            node.setPos(nodes[-1].pos().x(), nodes[-1].pos().y() + 92)
        else:
            node.setPos(gnode.pos().x(), gnode.pos().y() + 130)
        self._connect(gnode, node)
        nodes.append(node)
        self._update_scene_rect()
        return True

    def _insert_tool_after(
        self, after: FlowNodeItem, meta: dict
    ) -> FlowNodeItem:
        """在 after 节点之后插入一个新工具节点，后续节点依次下移。"""
        group = self._group_of_node(after)
        if group is None:
            return after
        gnode = self._group_node[group]
        nodes = self._group_tool_nodes[group]
        idx = nodes.index(after)

        # 被插入位置之后的节点整体下移一格
        for n in nodes[idx + 1:]:
            n.setPos(n.pos().x(), n.pos().y() + 92)

        accent = GROUP_COLORS.get(group, QColor("#0EA5E9"))
        node = self._create_node(
            meta["id"], meta["name"], meta["category"],
            node_type="tool", accent=accent,
        )
        node.setPos(after.pos().x(), after.pos().y() + 92)
        nodes.insert(idx + 1, node)
        self._connect(gnode, node)

        # 刷新被下移节点的连线
        for n in nodes[idx + 2:]:
            self._refresh_arrow(gnode, n)
        self._update_scene_rect()
        return node

    def _remove_tool_node(self, node: FlowNodeItem) -> None:
        """删除指定工具节点及其连线，后续节点整体上移。"""
        group = self._group_of_node(node)
        if group is None:
            return
        gnode = self._group_node[group]
        nodes = self._group_tool_nodes[group]
        idx = nodes.index(node)
        nodes.pop(idx)
        self._nodes.pop(node.node_id, None)

        # 先删除与节点相关的连线，再删除节点本身
        for item in list(self._scene.items()):
            if isinstance(item, ArrowItem) and (
                item._src is node or item._dst is node
            ):
                self._scene.removeItem(item)
        self._scene.removeItem(node)

        # 后续节点整体上移一格并刷新连线
        for n in nodes[idx:]:
            n.setPos(n.pos().x(), n.pos().y() - 92)
            self._refresh_arrow(gnode, n)
        self._update_scene_rect()

    # -- 添加工具：弹出展开的工具选择列表 -- #
    def _pick_and_add_tool(self, node: Optional[FlowNodeItem]) -> None:
        panel = ToolPanel()
        panel.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        panel.tool_clicked.connect(
            lambda tid, n=node, p=panel: self._on_pick_add(n, tid, p)
        )
        # 默认定位到右键节点所在分组，方便就近选择
        group = self._group_of_node(node)
        if group is None and node is not None and node.node_type == "group":
            group = node.title
        if group:
            panel.select_group(group)
        self._picker_panel = panel
        panel.move(QCursor.pos())
        panel.show()
        panel.raise_()
        panel.activateWindow()

    def _on_pick_add(self, after, tool_id: str, panel: ToolPanel) -> None:
        panel.close()
        if tool_id == "tool_base":
            # 工具基类：流程视图中定位并高亮基类节点，同时打开工具基类界面
            base = self._nodes.get("tool_base")
            if base is not None:
                base.setSelected(True)
                self.centerOn(base)
            self.tool_clicked.emit("tool_base", "工具基类")
            return
        if tool_id in self._nodes:
            QMessageBox.information(
                self, "添加工具", f"「{get_tool(tool_id)['name']}」已在流程中。"
            )
            return
        if after is None or after.node_type == "group":
            # 空白处/分组节点右键：添加到该分组末尾（分组不存在时自动创建）
            self.add_tool_to_flow(tool_id)
        else:
            self._insert_tool_after(after, get_tool(tool_id))
        self.tool_added.emit(tool_id, get_tool(tool_id)["name"])

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
        node = self._node_at(event.pos())
        if node is not None and node.node_type == "group":
            self._show_group_menu(node, event)
            return
        if node is not None and node.node_type == "tool":
            self._show_tool_menu(node, event)
            return
        self._show_view_menu(event)

    def _show_group_menu(self, node: FlowNodeItem, event) -> None:
        """分组节点右键菜单：向该分组添加工具。"""
        menu = QMenu(self)
        act_add = menu.addAction("＋ 添加工具…")
        act_pick = menu.addAction("选择添加工具…")
        chosen = menu.exec(event.globalPos())
        if chosen in (act_add, act_pick):
            self._pick_and_add_tool(node)

    def _show_tool_menu(self, node: FlowNodeItem, event) -> None:
        """工具节点右键菜单：添加工具 / 移除此工具 / 选择添加工具。

        添加类操作均展开工具选择列表，由用户挑选要添加的工具。
        """
        menu = QMenu(self)
        act_add = menu.addAction("＋ 添加工具…")
        act_remove = menu.addAction("🗑 移除此工具")
        act_pick = menu.addAction("选择添加工具…")
        chosen = menu.exec(event.globalPos())
        if chosen in (act_add, act_pick):
            self._pick_and_add_tool(node)
        elif chosen == act_remove:
            self._remove_tool_node(node)

    def _show_view_menu(self, event) -> None:
        """空白处右键菜单：添加工具 + 视图辅助操作。"""
        menu = QMenu(self)
        act_pick = menu.addAction("选择添加工具…")
        menu.addSeparator()
        act_fit = menu.addAction("适应视图")
        act_zoom_in = menu.addAction("放大")
        act_zoom_out = menu.addAction("缩小")
        chosen = menu.exec(event.globalPos())
        if chosen == act_pick:
            self._pick_and_add_tool(None)
        elif chosen == act_fit:
            self.fit_graph()
        elif chosen == act_zoom_in:
            self.scale(1.2, 1.2)
        elif chosen == act_zoom_out:
            self.scale(1.0 / 1.2, 1.0 / 1.2)
