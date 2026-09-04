"""标注工具管理面板。

参照「工具箱」布局改造：
    一棵可折叠的多级工具树（工具组 → 分类 → 工具项），
    分组标题深色加粗、可展开折叠，工具项带图标、选中高亮，
    单击工具项时发射 ``tool_clicked`` 信号。

对外提供两种可复用组件：
    ToolTreeWidget  纯工具树（供主窗口左侧常驻「工具箱」面板使用）
    ToolPanel       带标题栏的工具选择弹窗（供「添加工具」按钮 / 流程图右键使用）
"""
from __future__ import annotations

from typing import Dict, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from alg.tools_registry import TOOL_GROUPS, get_tools_by_group

# 分类 → 图标（参照图片，每个工具行前显示一个小图标）
_CATEGORY_ICONS: Dict[str, str] = {
    "基础标注": "📐",
    "辅助标注": "✨",
    "视图工具": "🖼",
    "检测": "🎯",
    "分割": "✂️",
    "分类": "🏷",
    "关键点": "🦴",
    "OCR": "📄",
    "引擎": "⚙",
    "基座": "🧩",
}

_GROUP_ICONS: Dict[str, str] = {g["name"]: g["icon"] for g in TOOL_GROUPS}

_TREE_STYLE = """
QTreeWidget {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    background: white;
    font-size: 12px;
    padding: 4px;
    outline: none;
}
QTreeWidget::item {
    padding: 5px 4px;
    color: #334155;
    border-radius: 5px;
    margin: 1px 0;
}
QTreeWidget::item:hover { background: #F1F5F9; }
QTreeWidget::item:selected {
    background: #DBEAFE;
    color: #1D4ED8;
    font-weight: 600;
}
QTreeWidget::item:selected:!active { background: #DBEAFE; color: #1D4ED8; }
QTreeWidget::branch {
    background: transparent;
    border-image: none;
    image: none;
}
QTreeWidget::branch:has-children:closed { border-image: none; image: none; }
QTreeWidget::branch:has-children:open { border-image: none; image: none; }
"""


def _tool_icon(t: dict) -> str:
    """工具项图标：优先取分类图标，否则用所属工具组图标。"""
    return _CATEGORY_ICONS.get(t["category"], _GROUP_ICONS.get(t["group"], "🛠"))


class ToolTreeWidget(QWidget):
    """可复用的工具分类树（参照图片布局）。

    - 顶层按工具组（通用 / YOLO / Paddle）分组，可折叠
    - 分组下按分类（检测 / 分割 / 分类…）再次分组，可折叠
    - 工具项带图标，单击发射 ``tool_clicked(tool_id)``
    """

    tool_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tree: QTreeWidget | None = None
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setStyleSheet(_TREE_STYLE)
        self._tree.itemClicked.connect(self._on_item_clicked)

        for g in TOOL_GROUPS:
            self._build_group(g["name"])
        root.addWidget(self._tree)

    def _build_group(self, group_name: str) -> None:
        """构建某个工具组下的整棵子树：分组节点 → 分类节点 → 工具项。"""
        gitem = QTreeWidgetItem(self._tree)
        gitem.setText(0, f"{_GROUP_ICONS.get(group_name, '📦')}  {group_name}")
        gitem.setToolTip(0, "工具分组")
        gitem.setFlags(gitem.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = QFont("Microsoft YaHei", 10)
        font.setBold(True)
        gitem.setFont(0, font)
        gitem.setForeground(0, QColor("#0F172A"))

        tools = get_tools_by_group(group_name)
        categories: Dict[str, List[dict]] = {}
        for t in tools:
            categories.setdefault(t["category"], []).append(t)

        for cat, items in categories.items():
            citem = QTreeWidgetItem(gitem)
            citem.setText(0, f"▸ {cat}  ({len(items)})")
            citem.setToolTip(0, cat)
            citem.setFlags(citem.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            cat_font = QFont("Microsoft YaHei", 9)
            cat_font.setBold(True)
            citem.setFont(0, cat_font)
            citem.setForeground(0, QColor("#475569"))

            for t in items:
                child = QTreeWidgetItem(citem)
                child.setText(0, f"{_tool_icon(t)}  {t['name']}")
                child.setToolTip(0, t["description"])
                child.setData(0, Qt.ItemDataRole.UserRole, t["id"])
                child.setForeground(0, QColor("#334155"))
                citem.addChild(child)

            citem.setExpanded(True)

        gitem.setExpanded(True)

    # ------------------------------------------------------------------ #
    def select_group(self, group_name: str) -> None:
        """程序化展开并定位某个工具组（默认定位到右键节点所在分组）。"""
        if not group_name or self._tree is None:
            return
        for i in range(self._tree.topLevelItemCount()):
            gitem = self._tree.topLevelItem(i)
            if group_name in gitem.text(0):
                self._tree.expandItem(gitem)
                for j in range(gitem.childCount()):
                    self._tree.expandItem(gitem.child(j))
                self._tree.scrollToItem(gitem)
                return

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        tool_id = item.data(0, Qt.ItemDataRole.UserRole)
        if tool_id:  # 叶子工具项
            self.tool_clicked.emit(tool_id)


class ToolPanel(QWidget):
    """带标题栏的工具选择弹窗（「＋ 添加工具」按钮 / 流程图右键添加用）。"""

    tool_clicked = pyqtSignal(str)  # tool_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(360, 420)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        title = QLabel("选择要添加的标注工具")
        title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #334155;"
            "padding: 2px 2px 4px 2px;"
        )
        root.addWidget(title)

        self._tree = ToolTreeWidget()
        self._tree.tool_clicked.connect(self.tool_clicked.emit)
        root.addWidget(self._tree, 1)

    def select_group(self, group_name: str) -> None:
        """程序化选中某个工具组。"""
        self._tree.select_group(group_name)
