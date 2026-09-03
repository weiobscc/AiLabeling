"""AI 标注训练软件主窗口。

布局：
    ┌─ 菜单栏 ───────────────────────────────────────────┐
    │  项目管理 | 视图 | 帮助                        │
    ├───────────────┬────────────────────────────────────┤
    │  ◀ 左侧可折叠  │                                    │
    │  工具依赖流程 [＋ 添加工具]                         │
    │  (流程图)     │           右侧工作区（预留）        │
    │  ▲ 点击按钮   │                                    │
    │  右侧弹出工具列表                                  │
    └───────────────┴────────────────────────────────────┘

功能：
    - 项目管理菜单：展开项目列表，可新增项目、删除选中项目、切换当前项目
    - 左侧面板（QDockWidget）可折叠/浮动/关闭，视图菜单可重新显示
    - 「添加工具」按钮位于流程标题最右侧，点击后右侧弹出工具选择列表
    - 依赖流程图 / 工具选择列表中点击工具 → 右侧面板展示工具基类信息（不弹窗）
    - 鼠标悬浮到流程工具节点上 → 显示工具简单说明（tooltip）
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QCursor, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from alg.tools_registry import get_tool
from ui.common.tool_base_window import ToolBasePanel
from ui.common.tool_flow_view import ToolFlowView
from ui.common.tool_panel import ToolPanel

_STYLE = """
QMenuBar {
    background: #FFFFFF;
    color: #1E293B;
    font-size: 13px;
    border-bottom: 1px solid #E2E8F0;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 14px;
}
QMenuBar::item:selected { background: #F1F5F9; border-radius: 4px; }
QMenuBar::item:pressed { background: #DBEAFE; color: #1D4ED8; }
QMenu {
    background: #FFFFFF;
    color: #1E293B;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 6px;
    font-size: 13px;
}
QMenu::item { padding: 7px 26px 7px 18px; border-radius: 4px; }
QMenu::item:selected { background: #DBEAFE; color: #1D4ED8; }
QMenu::item:disabled { color: #94A3B8; }
QMenu::separator { height: 1px; background: #E2E8F0; margin: 5px 10px; }
QStatusBar { background: #F8FAFC; color: #64748B; }
QToolTip { background: #0F172A; color: #E2E8F0; border: none; padding: 4px 8px; }
"""


# ---------------------------------------------------------------------- #
# 项目管理菜单
# ---------------------------------------------------------------------- #
class ProjectMenu(QMenu):
    """项目管理菜单：每次展开时动态重建项目列表。"""

    project_switched = pyqtSignal(str)  # 项目名
    project_added = pyqtSignal(str)  # 项目名
    project_removed = pyqtSignal(str)  # 项目名

    def __init__(self, parent=None) -> None:
        super().__init__("项目管理(&P)", parent)
        self._projects: List[str] = []
        self._current: Optional[str] = None
        self.aboutToShow.connect(self._rebuild)

    # -- 状态读写 -- #
    def set_projects(self, projects: List[str], current: Optional[str]) -> None:
        self._projects = list(projects)
        self._current = current

    def current(self) -> Optional[str]:
        return self._current

    # -- 动态构建 -- #
    def _rebuild(self) -> None:
        self.clear()

        if not self._projects:
            empty = self.addAction("（暂无项目）")
            empty.setEnabled(False)
        else:
            group = QActionGroup(self)
            group.setExclusive(True)
            for name in self._projects:
                act = QAction(name, self)
                act.setCheckable(True)
                act.setChecked(name == self._current)
                act.triggered.connect(
                    lambda checked=False, n=name: self._switch(n)
                )
                group.addAction(act)
                self.addAction(act)

        self.addSeparator()

        add_act = self.addAction("＋ 新增项目…")
        add_act.triggered.connect(self._add_project)
        remove_act = self.addAction("🗑 删除选中项目")
        remove_act.setEnabled(self._current is not None)
        remove_act.triggered.connect(self._remove_project)

    # -- 操作 -- #
    def _switch(self, name: str) -> None:
        self._current = name
        self.project_switched.emit(name)

    def _add_project(self) -> None:
        name, ok = QInputDialog.getText(
            self, "新增项目", "请输入项目名称："
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self._projects:
            QMessageBox.information(self, "提示", "项目已存在。")
            return
        self._projects.append(name)
        self._current = name
        self.project_added.emit(name)
        self.project_switched.emit(name)

    def _remove_project(self) -> None:
        if self._current is None:
            return
        ret = QMessageBox.question(
            self,
            "删除项目",
            f"确定删除项目「{self._current}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        removed = self._current
        self._projects.remove(removed)
        self._current = self._projects[-1] if self._projects else None
        self.project_removed.emit(removed)
        if self._current is not None:
            self.project_switched.emit(self._current)


# ---------------------------------------------------------------------- #
# 主窗口
# ---------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._projects: List[str] = []
        self._current_project: Optional[str] = None

        self.setWindowTitle("AI 标注训练软件")
        self.resize(1280, 800)
        self.setMinimumSize(1000, 660)
        self.setStyleSheet(_STYLE)

        self._tool_picker_panel: QWidget | None = None
        self._initial_ratio_applied = False

        self._build_central()
        self._build_dock()
        self._build_menu()

        self.statusBar().showMessage("就绪")
        self._update_title()

    # ------------------------------------------------------------------ #
    # 初始布局：左右按 4:6 比例
    # ------------------------------------------------------------------ #
    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        super().showEvent(event)
        if self._initial_ratio_applied:
            return
        self._initial_ratio_applied = True
        # 左侧 dock 占 40%，右侧工作区占 60%
        left = max(self._tool_dock.minimumWidth(), int(self.width() * 0.4))
        self.resizeDocks([self._tool_dock], [left], Qt.Orientation.Horizontal)

    # ------------------------------------------------------------------ #
    # 菜单栏
    # ------------------------------------------------------------------ #
    def _build_menu(self) -> None:
        menubar = self.menuBar()
        # 项目管理
        self.project_menu = ProjectMenu(self)
        self.project_menu.project_switched.connect(self._on_project_switched)
        self.project_menu.project_added.connect(self._on_project_added)
        self.project_menu.project_removed.connect(self._on_project_removed)
        menubar.addMenu(self.project_menu)

        # 视图
        view_menu = menubar.addMenu("视图(&V)")
        self._dock_toggle = self.left_dock_toggle_action()
        view_menu.addAction(self._dock_toggle)

        # 帮助
        help_menu = menubar.addMenu("帮助(&H)")
        about_act = QAction("关于(&A)", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    # ------------------------------------------------------------------ #
    # 右侧工作区：初始为空，添加工具后显示流程依赖
    # ------------------------------------------------------------------ #
    def _build_central(self) -> None:
        self._workspace_stack = QStackedWidget()
        self._workspace_stack.setObjectName("workspace")
        self._workspace_stack.setStyleSheet(
            "QWidget#workspace { background: #F8FAFC; }"
        )

        # 流程依赖面板：初始为空
        self._tool_panel = ToolBasePanel()
        self._workspace_stack.addWidget(self._tool_panel)

        self.setCentralWidget(self._workspace_stack)

    # ------------------------------------------------------------------ #
    # 左侧可折叠面板
    # ------------------------------------------------------------------ #
    def _build_dock(self) -> None:
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # 工具依赖流程（占满左侧面板）
        flow_panel = QWidget()
        flow_layout = QVBoxLayout(flow_panel)
        flow_layout.setContentsMargins(10, 10, 10, 4)
        flow_layout.setSpacing(6)

        flow_header = QHBoxLayout()
        flow_title = QLabel("工具依赖流程")
        flow_title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #334155;"
        )
        flow_tip = QLabel("添加工具后，右侧显示流程依赖")
        flow_tip.setStyleSheet("font-size: 11px; color: #94A3B8;")
        flow_header.addWidget(flow_title)
        flow_header.addStretch()
        flow_header.addWidget(flow_tip)
        # 添加工具按钮（位于标题行最右侧）
        self.add_tool_btn = QPushButton("＋ 添加工具")
        self.add_tool_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_tool_btn.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border: none;"
            " border-radius: 6px; padding: 4px 12px; font-size: 12px;"
            " font-weight: 600; }"
            "QPushButton:hover { background: #1D4ED8; }"
            "QPushButton:pressed { background: #1E40AF; }"
        )
        self.add_tool_btn.clicked.connect(self._show_tool_picker)
        flow_header.addWidget(self.add_tool_btn)
        flow_layout.addLayout(flow_header)

        self.tool_flow_view = ToolFlowView()
        self.tool_flow_view.tool_clicked.connect(self.show_tool_in_panel)
        self.tool_flow_view.tool_added.connect(self.show_tool_in_panel)
        flow_layout.addWidget(self.tool_flow_view, 1)

        splitter.addWidget(flow_panel)
        root.addWidget(splitter)

        dock = QDockWidget("工具流程与标注工具", self)
        dock.setObjectName("toolDock")
        dock.setWidget(container)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._tool_dock = dock
        dock.setMinimumWidth(300)

    def left_dock_toggle_action(self) -> QAction:
        """左侧面板的显示/隐藏开关（供视图菜单使用）。"""
        act = self._tool_dock.toggleViewAction()
        act.setText("显示左侧面板")
        return act

    # ------------------------------------------------------------------ #
    # 流程依赖展示（右侧面板）
    # ------------------------------------------------------------------ #
    def show_tool_in_panel(self, tool_id: str, _name: str = "") -> None:
        """添加/点击工具后由右侧面板展示该工具的流程依赖。"""
        try:
            self._tool_panel.show_dependency(tool_id)
        except KeyError:
            self.statusBar().showMessage(f"未知工具：{tool_id}", 3000)
            return
        self._workspace_stack.setCurrentWidget(self._tool_panel)
        self.statusBar().showMessage(
            f"已显示流程依赖：{get_tool(tool_id)['name']}", 3000
        )

    # ------------------------------------------------------------------ #
    # 「添加工具」弹出选择
    # ------------------------------------------------------------------ #
    def _show_tool_picker(self) -> None:
        """在「添加工具」按钮右侧弹出工具选择列表。"""
        if self._tool_picker_panel is None:
            panel = ToolPanel()
            # 作为无边框弹出窗口：点击面板外部自动关闭
            panel.setWindowFlags(
                Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
            )
            panel.tool_clicked.connect(self._on_picker_selected)
            self._tool_picker_panel = panel

        btn = self.sender()
        if isinstance(btn, QPushButton):
            pos = btn.mapToGlobal(QPoint(0, btn.height()))
        else:
            pos = QCursor.pos()

        self._tool_picker_panel.move(pos)
        self._tool_picker_panel.show()
        self._tool_picker_panel.raise_()
        self._tool_picker_panel.activateWindow()

    def _on_picker_selected(self, tool_id: str) -> None:
        """「＋ 添加工具」选中后：把工具加入流程并展示其流程依赖。"""
        if self._tool_picker_panel is not None:
            self._tool_picker_panel.close()
        if tool_id == "tool_base":
            # 工具基类不进入流程，直接展示其流程依赖
            self.show_tool_in_panel("tool_base")
            return
        if self.tool_flow_view.add_tool_to_flow(tool_id):
            self.tool_flow_view.tool_added.emit(tool_id, get_tool(tool_id)["name"])
        else:
            # 已在流程中：仍展示其流程依赖
            self.show_tool_in_panel(tool_id)

    # ------------------------------------------------------------------ #
    # 项目管理回调
    # ------------------------------------------------------------------ #
    def _on_project_switched(self, name: str) -> None:
        self._current_project = name
        self._update_title()
        self.statusBar().showMessage(f"当前项目：{name}", 3000)

    def _on_project_added(self, name: str) -> None:
        if name not in self._projects:
            self._projects.append(name)
        self.statusBar().showMessage(f"已新增项目：{name}", 3000)

    def _on_project_removed(self, name: str) -> None:
        if name in self._projects:
            self._projects.remove(name)
        if self._current_project == name:
            self._current_project = None
        self._update_title()
        self.statusBar().showMessage(f"已删除项目：{name}", 3000)

    def _update_title(self) -> None:
        base = "AI 标注训练软件"
        if self._current_project:
            self.setWindowTitle(f"{base} - [{self._current_project}]")
        else:
            self.setWindowTitle(base)

    # ------------------------------------------------------------------ #
    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            "<h3>AI 标注训练软件</h3>"
            "<p>标注工具流程与工具管理界面框架。</p>"
            "<p>在左侧依赖流程图或工具列表中点击工具，"
            "可在右侧面板查看对应工具基类信息。</p>",
        )
