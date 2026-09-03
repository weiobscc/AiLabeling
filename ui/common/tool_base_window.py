"""流程依赖面板。

右侧工作区面板：初始为空，用户在流程中添加工具（流程旁「＋ 添加工具」
按钮 / 工具节点右键「选择添加工具…」/ 点击流程中的工具节点）后，
展示该工具的**流程依赖**：

    - 上游依赖链：按 alg.tools_registry 中 dependencies 字段递归解析，
      以「工具基类 → 引擎 → 本工具」步骤条形式展示
    - 下游工具：依赖本工具的其他工具
    - 所属分组 / 分类等基本信息

切换工具时整块替换内容容器，避免控件残留。

ToolBaseWindow 保留为独立的 QDialog 包装，便于独立调试与复用。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from alg.tools_registry import TOOL_REGISTRY, get_tool

# 分组 → 主题色（与流程图一致）
_GROUP_COLORS: Dict[str, str] = {
    "通用工具": "#0EA5E9",
    "YOLO工具": "#F59E0B",
    "Paddle工具": "#10B981",
    "系统": "#64748B",
}

# 基础信息区样式
_TITLE_STYLE = "font-size: 20px; font-weight: 700; color: #1E293B;"
_META_STYLE = "font-size: 12px; color: #64748B;"
_DESC_STYLE = "font-size: 13px; color: #475569;"


def _resolve_chain(tool_id: str) -> List[Dict[str, Any]]:
    """递归解析 dependencies，得到从工具基类到本工具的有序链。"""
    chain: List[Dict[str, Any]] = []
    seen: set = set()

    def walk(tid: str) -> None:
        if tid in seen:
            return
        seen.add(tid)
        meta = get_tool(tid)
        for dep in meta.get("dependencies", []):
            walk(dep)
        chain.append(meta)

    walk(tool_id)
    return chain


def _downstream_tools(tool_id: str) -> List[Dict[str, Any]]:
    """返回注册表中直接依赖该工具的其他工具。"""
    return [t for t in TOOL_REGISTRY.values()
            if tool_id in t.get("dependencies", [])]


class ToolBasePanel(QWidget):
    """流程依赖面板：初始为空，添加工具后展示该工具的流程依赖。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tool: Optional[Dict[str, Any]] = None
        self._content: Optional[QWidget] = None

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._show_empty()

    # ------------------------------------------------------------------ #
    # 内容切换：整块替换容器，避免控件残留
    # ------------------------------------------------------------------ #
    def _replace_content(self, new_content: QWidget) -> None:
        """用新内容容器整体替换旧容器。

        旧容器通过 setParent(None) 立即脱离对象树（findChildren 不再可见、
        不再受父面板布局影响），随后 deleteLater 释放内存。
        """
        if self._content is not None:
            old = self._content
            self._root.removeWidget(old)
            old.hide()
            old.setParent(None)
            old.deleteLater()
        self._content = new_content
        self._root.addWidget(new_content)

    def _show_empty(self) -> None:
        """初始空状态：纯空白，不显示任何内容。"""
        self._tool = None
        self._replace_content(QWidget())

    # ------------------------------------------------------------------ #
    # 流程依赖展示
    # ------------------------------------------------------------------ #
    def show_dependency(self, tool_id: str) -> None:
        """展示指定工具的流程依赖。"""
        self._tool = get_tool(tool_id)
        self._replace_content(self._build_content())

    def _build_content(self) -> QWidget:
        assert self._tool is not None

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        tool_id = self._tool["id"]
        group = self._tool["group"]
        color = _GROUP_COLORS.get(group, "#0EA5E9")

        # ---------- 标题区 ----------
        title_row = QHBoxLayout()
        badge = QLabel("●")
        badge.setStyleSheet(f"color: {color}; font-size: 26px;")
        badge.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(badge)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(self._tool["name"])
        title.setStyleSheet(_TITLE_STYLE)
        meta = QLabel(f"{group} · {self._tool['category']}")
        meta.setStyleSheet(_META_STYLE)
        title_box.addWidget(title)
        title_box.addWidget(meta)
        title_row.addLayout(title_box)
        title_row.addStretch()
        layout.addLayout(title_row)

        # ---------- 描述 ----------
        desc = QLabel(self._tool["description"])
        desc.setWordWrap(True)
        desc.setStyleSheet(_DESC_STYLE)
        layout.addWidget(desc)

        # ---------- 流程依赖：上游链路 ----------
        chain = _resolve_chain(tool_id)
        dep_group = QGroupBox("流程依赖")
        dep_group.setStyleSheet(
            "QGroupBox { font-weight: 700; color: #334155; border: 1px solid #E2E8F0;"
            " border-radius: 8px; margin-top: 10px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        dep_layout = QVBoxLayout(dep_group)
        dep_layout.setContentsMargins(14, 12, 14, 14)
        dep_layout.setSpacing(10)

        tip = QLabel("上游依赖链路（按顺序运行）")
        tip.setStyleSheet("font-size: 12px; color: #94A3B8;")
        dep_layout.addWidget(tip)

        steps_row = QHBoxLayout()
        steps_row.setSpacing(6)
        for i, meta in enumerate(chain):
            is_current = i == len(chain) - 1
            steps_row.addWidget(self._make_step(meta["name"], color, is_current))
            if not is_current:
                arrow = QLabel("→")
                arrow.setStyleSheet("color: #94A3B8; font-size: 16px;")
                arrow.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                steps_row.addWidget(arrow)
        steps_row.addStretch()
        dep_layout.addLayout(steps_row)
        layout.addWidget(dep_group)

        # ---------- 下游工具 ----------
        downstream = _downstream_tools(tool_id)
        down_group = QGroupBox("下游工具")
        down_group.setStyleSheet(
            "QGroupBox { font-weight: 700; color: #334155; border: 1px solid #E2E8F0;"
            " border-radius: 8px; margin-top: 10px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        down_layout = QVBoxLayout(down_group)
        down_layout.setContentsMargins(14, 12, 14, 14)
        down_layout.setSpacing(10)

        if downstream:
            tip = QLabel("以下工具运行时依赖本工具：")
            tip.setStyleSheet("font-size: 12px; color: #94A3B8;")
            down_layout.addWidget(tip)
            chips_row = QHBoxLayout()
            chips_row.setSpacing(8)
            for t in downstream:
                chips_row.addWidget(self._make_chip(t["name"], color))
            chips_row.addStretch()
            down_layout.addLayout(chips_row)
        else:
            none_label = QLabel("暂无工具依赖本工具。")
            none_label.setStyleSheet("font-size: 12px; color: #CBD5E1;")
            down_layout.addWidget(none_label)
        layout.addWidget(down_group)

        # ---------- 位置信息 ----------
        pos_label = QLabel(f"所属分组：{group}    分类：{self._tool['category']}")
        pos_label.setStyleSheet(_META_STYLE)
        layout.addWidget(pos_label)

        layout.addStretch()
        return content

    # ------------------------------------------------------------------ #
    # 依赖展示控件
    # ------------------------------------------------------------------ #
    def _make_step(self, name: str, color: str, highlight: bool) -> QWidget:
        """上游链路中的一个步骤：圆点 + 名称。"""
        step = QWidget()
        row = QHBoxLayout(step)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        row.addWidget(dot)

        label = QLabel(name)
        if highlight:
            label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #1E293B;"
                f" border: 1.5px solid {color}; border-radius: 14px;"
                " padding: 3px 12px;"
            )
        else:
            label.setStyleSheet(
                "font-size: 13px; color: #475569;"
                " background: #F1F5F9; border-radius: 12px; padding: 3px 10px;"
            )
        row.addWidget(label)
        return step

    def _make_chip(self, name: str, color: str) -> QWidget:
        """下游工具 chip 标签。"""
        chip = QLabel(name)
        chip.setStyleSheet(
            f"color: {color}; background: #F8FAFC;"
            f" border: 1px solid {color}40; border-radius: 12px;"
            " padding: 3px 12px; font-size: 12px; font-weight: 600;"
        )
        return chip


class ToolBaseWindow(QDialog):
    """流程依赖独立窗口（包装 ToolBasePanel，供独立调试/复用）。"""

    def __init__(self, tool_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        panel = ToolBasePanel(self)
        panel.show_dependency(tool_id)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)
        self.setWindowTitle(f"{get_tool(tool_id)['name']} - 流程依赖")
        self.setMinimumSize(560, 520)
