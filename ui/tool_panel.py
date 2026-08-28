"""标注工具管理面板。

左侧为三个工具组列表（通用工具 / YOLO工具 / Paddle工具），
切换时右侧显示该组下按分类组织的工具树（如 YOLO 工具 → 检测/分割/分类/关键点）。
单击工具项时发射 tool_clicked 信号，由主窗口跳转工具基类界面。
"""
from __future__ import annotations

from typing import Dict, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from alg.tools_registry import TOOL_GROUPS, get_tools_by_group

_GROUP_COLORS = {
    "通用工具": "#0EA5E9",
    "YOLO工具": "#F59E0B",
    "Paddle工具": "#10B981",
}


class ToolPanel(QWidget):
    """标注工具选择面板（作为「添加工具」按钮的弹出内容）。

    左侧为三个工具组列表（通用工具 / YOLO工具 / Paddle工具），
    切换时右侧显示该组下按分类组织的工具树（如 YOLO 工具 → 检测/分割/分类/关键点）。
    单击工具项时发射 tool_clicked 信号，由主窗口跳转工具基类界面。
    """

    tool_clicked = pyqtSignal(str)  # tool_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group_trees: Dict[str, QTreeWidget] = {}
        self.setFixedSize(520, 360)
        self._build_ui()
        self._select_group(0)

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        # 标题
        title = QLabel("选择要添加的标注工具")
        title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #334155;"
            "padding: 2px 2px 4px 2px;"
        )
        root.addWidget(title)

        # 主体：左侧组列表 + 右侧工具树
        body = QHBoxLayout()
        body.setSpacing(10)

        self._group_list = QListWidget()
        self._group_list.setFixedWidth(108)
        self._group_list.setStyleSheet(
            "QListWidget { border: 1px solid #E2E8F0; border-radius: 6px;"
            " background: white; padding: 4px; }"
            "QListWidget::item { padding: 10px 6px; border-radius: 4px;"
            " font-size: 12px; color: #334155; }"
            "QListWidget::item:hover { background: #F1F5F9; }"
            "QListWidget::item:selected { background: #DBEAFE; color: #1D4ED8;"
            " font-weight: 600; }"
        )
        self._group_list.currentRowChanged.connect(self._select_group)

        self._stack = QStackedWidget()
        for g in TOOL_GROUPS:
            self._group_list.addItem(
                QListWidgetItem(f"{g['icon']}  {g['name']}")
            )
            tree = self._build_tool_tree(g["name"])
            self._group_trees[g["name"]] = tree
            self._stack.addWidget(tree)

        body.addWidget(self._group_list)
        body.addWidget(self._stack, 1)
        root.addLayout(body, 1)

    def _build_tool_tree(self, group_name: str) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setAnimated(True)
        tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #E2E8F0; border-radius: 6px;"
            " background: white; font-size: 12px; }"
            "QTreeWidget::item { padding: 5px 4px; color: #334155; }"
            "QTreeWidget::item:hover { background: #F1F5F9; }"
            "QTreeWidget::item:selected { background: #DBEAFE; color: #1D4ED8; }"
            "QTreeWidget::branch { background: transparent; }"
        )

        tools = get_tools_by_group(group_name)

        # 按分类聚合
        categories: Dict[str, List[dict]] = {}
        for t in tools:
            categories.setdefault(t["category"], []).append(t)

        # 保证分类顺序稳定
        for cat, items in categories.items():
            cat_item = QTreeWidgetItem(tree)
            cat_item.setText(0, f"▸ {cat}  ({len(items)})")
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            font = cat_item.font(0)
            font.setBold(True)
            cat_item.setFont(0, font)
            cat_item.setForeground(0, Qt.GlobalColor.darkBlue)

            for t in items:
                child = QTreeWidgetItem(cat_item)
                child.setText(0, t["name"])
                child.setToolTip(0, t["description"])
                # 存放 tool_id 供点击时读取
                child.setData(0, Qt.ItemDataRole.UserRole, t["id"])
                child.setForeground(0, QColor("#475569"))
                cat_item.addChild(child)

            cat_item.setExpanded(True)

        tree.itemClicked.connect(self._on_item_clicked)
        return tree

    # ------------------------------------------------------------------ #
    def _select_group(self, row: int) -> None:
        if 0 <= row < len(TOOL_GROUPS):
            self._stack.setCurrentIndex(row)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        tool_id = item.data(0, Qt.ItemDataRole.UserRole)
        if tool_id:  # 叶子工具项
            self.tool_clicked.emit(tool_id)
