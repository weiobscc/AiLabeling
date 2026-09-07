"""标注工具工作台基类（供各类画布标注/推理工具继承）。

参考工作台布局（三列）：
    ┌──────┬─────────────────────────────────┬────────────────┐
    │ 工具 │                                 │ 图片信息  折叠  ›│
    │ 竖排 │        中央画布区(子类放入内容)    ├────────────────┤
    │      │                                 │ ▸ 标签管理       │
    │ 缩小 │                                 │ ▸ <子类页2...>   │
    │ 100% │                                 │                │
    │ 放大 │                                 │                │
    ├──────┴─────────────────────────────────┤                │
    │  [▽筛选][＋] 缩略图(可折叠)                  [^]           │
    └────────────────────────────────────────┴────────────────┘

基类职责：
    - 左列：竖排绘图工具条（选中态高亮），底部为**缩放**按钮
      「缩小 / 100% / 放大」；
    - 中列：``content_host`` 画布（子类放入内容）+ 底部 ``SampleStrip``
      横向可折叠样本条 —— 左侧「标签筛选 / 添加图片」按钮 + 「^」折叠钮；
    - 右列：**QTabWidget** 参数面板 —— 首个 Tab 为共享的「标签管理」
      （支持新建 / 删除标签）；子类通过 :meth:`populate_param_panel`
      追加各自的功能页。

子类约定：
    - 重写 :meth:`tool_specs` / :attr:`default_active_tool` 控制工具条；
    - 在 ``__init__`` 中向 ``self.content_lay`` 添加中央内容，
      并调用 :meth:`set_canvas` 以便缩放联动；
    - 重写 :meth:`populate_param_panel`，以 ``self.tabs``（QTabWidget）
      为参数为“新增一个功能页”；
    - 重写 :meth:`refresh`（记得调用 ``super().refresh()``）。
"""
from __future__ import annotations

from functools import partial
from typing import Any, Dict, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.tools.sample_strip import SampleStrip
from ui.tools.view_common import label_color

_RAIL_STYLE = """
QFrame#rail { background: #F8FAFC; border-right: 1px solid #E2E8F0; }
QFrame#rail QPushButton { border: none; background: transparent; border-radius: 8px;
  font-size: 15px; font-weight: 600; color: #475569; min-height: 40px;
  min-width: 40px; }
QFrame#rail QPushButton:hover { background: #EEF2F7; color: #0F172A; }
QFrame#rail QPushButton:checked { background: #CCFBF1; color: #0F766E; }
QFrame#rail QPushButton:disabled { color: #CBD5E1; }
QFrame#rail QPushButton#zoom { min-height: 26px; min-width: 40px;
  font-size: 12px; color: #334155; background: #FFFFFF;
  border: 1px solid #E2E8F0; border-radius: 6px; }
QFrame#rail QPushButton#zoom:hover { background: #F1F5F9; color: #0F172A; }
QFrame#rail QLabel#zoomv { color: #64748B; font-size: 12px; font-weight: 600; }
QFrame#rail QFrame#zoomsep { background: #E2E8F0; }
"""

_PANEL_STYLE = """
QFrame#param { background: #FFFFFF; border-left: 1px solid #E2E8F0; }
QLabel#param_head { font-size: 13px; font-weight: 700; color: #0F172A; }
QLabel#param_sub { font-size: 12px; color: #64748B; }
QPushButton#collapse { border: none; background: transparent; color: #94A3B8;
  font-size: 14px; min-width: 22px; }
QPushButton#collapse:hover { color: #0F172A; }
QPushButton#primary { background: #14B8A6; color: #FFFFFF; border: none;
  border-radius: 6px; padding: 3px 10px; font-size: 12px; font-weight: 600; }
QPushButton#primary:hover { background: #0D9488; }
QPushButton#ghost { background: #FFFFFF; border: 1px solid #CBD5E1;
  border-radius: 6px; padding: 3px 10px; font-size: 12px; color: #334155; }
QPushButton#ghost:hover { background: #F1F5F9; }
QPushButton#danger { background: #FFFFFF; border: 1px solid #FCA5A5;
  border-radius: 6px; color: #DC2626; font-size: 11px; padding: 1px 8px; }
QPushButton#danger:hover { background: #FEF2F2; }
QLineEdit { border: 1px solid #CBD5E1; border-radius: 6px; padding: 3px 8px;
  font-size: 12px; background: #FFFFFF; }
QListWidget#labels { border: 1px solid #E2E8F0; border-radius: 6px;
  background: #FFFFFF; outline: none; }
QListWidget#labels::item { border-bottom: 1px solid #F1F5F9; }
"""


class AnnotationWorkbench(QWidget):
    """标注工具工作台（通用外壳）。"""

    sig_message = pyqtSignal(str, int)

    # 子类可覆盖的工具序列与默认激活工具
    def tool_specs(self) -> List[Dict[str, Any]]:
        return [
            {"id": "select", "glyph": "选", "tip": "选择 / 移动", "enabled": True},
            {"id": "rect", "glyph": "矩", "tip": "矩形框标注", "enabled": True},
            {"id": "poly", "glyph": "多", "tip": "多边形（预留）", "enabled": True},
            {"id": "circle", "glyph": "圆", "tip": "圆形（预留）", "enabled": True},
            {"id": "line", "glyph": "线", "tip": "直线（预留）", "enabled": True},
            {"id": "brush", "glyph": "笔", "tip": "涂鸦（预留）", "enabled": True},
        ]

    default_active_tool: str = "rect"

    def __init__(self, ws, parent=None) -> None:
        super().__init__(parent)
        self.ws = ws
        self.session = ws.session
        self.active_tool: str = self.default_active_tool
        self.canvas = None  # 由子类通过 set_canvas 注入
        self._tool_btns: Dict[str, QPushButton] = {}
        self._build_ui()
        # 默认激活的工具（选中态）；内容刷新交由子类在构建后调用 refresh()
        self.set_active_tool(self.active_tool)

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 左列：竖排工具条(上) + 添加图片(下)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        self.rail = self._build_rail()
        left.addWidget(self.rail, 1)
        outer.addLayout(left)

        # 中列：画布(上) + 底部图片列表条(下)
        mid = QVBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)

        self.content_host = QWidget()
        self.content_lay = QVBoxLayout(self.content_host)
        self.content_lay.setContentsMargins(10, 8, 10, 8)
        self.content_lay.setSpacing(6)
        mid.addWidget(self.content_host, 1)

        self.strip = SampleStrip(self.ws)
        self.strip.sample_activated.connect(self.ws.set_current_sample_index)
        mid.addWidget(self.strip)
        outer.addLayout(mid, 1)

        # 右列：参数/信息面板（整列高）
        self._panel_card, self.tabs = self._build_panel()
        self.param_body = self.tabs  # 兼容子类 populate_param_panel(self.param_body)
        outer.addWidget(self._panel_card)

        outer.setStretch(0, 0)
        outer.setStretch(1, 1)
        outer.setStretch(2, 0)

    # ------------------------------------------------------------------ #
    # 最左工具条
    # ------------------------------------------------------------------ #
    def _build_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(58)
        rail.setStyleSheet(_RAIL_STYLE)
        v = QVBoxLayout(rail)
        v.setContentsMargins(7, 10, 7, 8)
        v.setSpacing(4)

        for spec in self.tool_specs():
            btn = QPushButton(spec["glyph"])
            btn.setObjectName("toolbtn")
            btn.setToolTip(spec["tip"])
            btn.setCheckable(True)
            if not spec.get("enabled", True):
                btn.setDisabled(True)
            btn.clicked.connect(
                lambda checked=False, sid=spec["id"]: self._on_tool(sid)
            )
            v.addWidget(btn)
            self._tool_btns[spec["id"]] = btn

        v.addStretch()

        # 分隔线
        sep = QFrame()
        sep.setObjectName("zoomsep")
        sep.setFixedHeight(1)
        v.addWidget(sep)

        # 缩放（缩小 / 100% / 放大）
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomv")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setToolTip("画布缩放比例（画布内滚轮亦可缩放）")
        v.addWidget(self.zoom_label)

        self.btn_zoom_out = QPushButton("缩小")
        self.btn_zoom_out.setObjectName("zoom")
        self.btn_zoom_out.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_out.setToolTip("缩小画布")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        v.addWidget(self.btn_zoom_out)

        self.btn_zoom_in = QPushButton("放大")
        self.btn_zoom_in.setObjectName("zoom")
        self.btn_zoom_in.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_in.setToolTip("放大画布")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        v.addWidget(self.btn_zoom_in)

        return rail

    def _on_tool(self, tool_id: str) -> None:
        self.set_active_tool(tool_id)

    def set_active_tool(self, tool_id: str) -> None:
        """切换当前工具（互斥选中态），并同步给画布。"""
        specs = {s["id"]: s for s in self.tool_specs()}
        spec = specs.get(tool_id)
        if spec is None or not spec.get("enabled", True):
            return
        self.active_tool = tool_id
        for tid, btn in self._tool_btns.items():
            btn.setChecked(tid == tool_id)
        if self.canvas is not None and hasattr(self.canvas, "set_tool"):
            self.canvas.set_tool(tool_id)

    # ------------------------------------------------------------------ #
    # 最右参数面板（QTabWidget：首 Tab「标签管理」共享 + 子类追加页）
    # ------------------------------------------------------------------ #
    def _build_panel(self) -> tuple:
        card = QFrame()
        card.setObjectName("param")
        card.setFixedWidth(278)
        card.setStyleSheet(_PANEL_STYLE)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        # 头部：标题 + 折叠按钮
        head = QHBoxLayout()
        head.setContentsMargins(14, 12, 8, 8)
        head.setSpacing(6)
        title = QLabel("图片信息")
        title.setObjectName("param_head")
        head.addWidget(title)
        head.addStretch()
        self.btn_collapse = QPushButton("›")
        self.btn_collapse.setObjectName("collapse")
        self.btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse.setToolTip("收起 / 展开参数面板")
        head.addWidget(self.btn_collapse)
        cv.addLayout(head)

        # 可折叠主体：Tab 面板
        self._panel_body = QWidget()
        body = QVBoxLayout(self._panel_body)
        body.setContentsMargins(10, 2, 10, 10)
        body.setSpacing(8)

        # Tab 面板
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #E2E8F0; border-radius: 6px;"
            " top: -1px; background: #FFFFFF; }"
            "QTabBar::tab { background: transparent; padding: 5px 12px;"
            " color: #64748B; font-size: 12px; border: none;"
            " border-bottom: 2px solid transparent; }"
            "QTabBar::tab:selected { color: #0F766E; font-weight: 600;"
            " border-bottom: 2px solid #14B8A6; }"
            "QTabBar::tab:hover { color: #0F172A; }"
        )
        body.addWidget(self.tabs, 1)

        cv.addWidget(self._panel_body, 1)
        self.btn_collapse.clicked.connect(self._toggle_panel)

        # 首个共享页：标签管理
        self._build_label_tab()
        return card, self.tabs

    def _toggle_panel(self) -> None:
        vis = not self._panel_body.isVisible()
        self._panel_body.setVisible(vis)
        self.btn_collapse.setText("‹" if vis else "›")
        self.btn_collapse.setToolTip("收起 / 展开参数面板")

    # ------------------------------------------------------------------ #
    # 「标签管理」Tab
    # ------------------------------------------------------------------ #
    def _build_label_tab(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        # 新建行
        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("新标签名（如 person）")
        self.label_edit.returnPressed.connect(self._on_new_label)
        add_row.addWidget(self.label_edit, 1)
        self.btn_label_add = QPushButton("新建")
        self.btn_label_add.setObjectName("primary")
        self.btn_label_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_label_add.setToolTip("新建标签")
        self.btn_label_add.clicked.connect(self._on_new_label)
        add_row.addWidget(self.btn_label_add)
        lay.addLayout(add_row)

        # 已有标签列表（色点 + 名称 + 用量 + 删除）
        self.manage_list = QListWidget()
        self.manage_list.setObjectName("labels")
        self.manage_list.setToolTip("已有标签及标注用量；点击 ✕ 删除标签")
        lay.addWidget(self.manage_list, 1)

        self.tabs.addTab(page, "标签管理")

    def _on_new_label(self) -> None:
        name = self.label_edit.text().strip()
        if not name:
            self.ws.message("请输入标签名", 2000)
            return
        if not self.session.add_label(name):
            self.ws.message(f"标签「{name}」已存在", 2000)
            return
        self.label_edit.clear()
        self.session.collect_labels()
        self.ws.refresh_all()
        self.ws.message(f"已新建标签「{name}」", 2000)

    def _on_delete_label(self, name: str) -> None:
        usage = sum(
            1 for s in self.session.samples
            for a in s.annotations if a.label == name
        )
        if usage > 0:
            ret = QMessageBox.question(
                self,
                "删除标签",
                f"标签「{name}」当前被 {usage} 处标注使用。\n"
                "删除将同时移除这些标注，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
        removed = self.session.remove_label(name)
        self.ws.refresh_all()
        tail = f"，已移除 {removed} 处标注" if removed else ""
        self.ws.message(f"已删除标签「{name}」{tail}", 2500)

    def _label_usage(self, name: str) -> int:
        return sum(
            1 for s in self.session.samples
            for a in s.annotations if a.label == name
        )

    def refresh_label_list(self) -> None:
        """重建「标签管理」列表（会话标签 + 用量 + 删除按钮）。"""
        self.manage_list.clear()
        labels = list(self.session.labels)
        if not labels:
            empty = QListWidgetItem("（暂无标签，请在上方新建）")
            empty.setForeground(Qt.GlobalColor.gray)
            self.manage_list.addItem(empty)
            return
        for lb in labels:
            item = QListWidgetItem()
            usage = self._label_usage(lb)
            row = self._make_label_row(lb, usage)
            self.manage_list.addItem(item)
            self.manage_list.setItemWidget(item, row)
            item.setSizeHint(row.sizeHint())

    def _make_label_row(self, name: str, usage: int) -> QWidget:
        color = label_color(name)
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(8, 3, 6, 3)
        h.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {color.name()}; font-size: 13px; background: transparent;"
        )
        h.addWidget(dot)

        nm = QLabel(name)
        nm.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #1E293B;"
            " background: transparent;"
        )
        h.addWidget(nm, 1)

        cnt = QLabel(f"{usage} 处")
        cnt.setStyleSheet("font-size: 11px; color: #94A3B8; background: transparent;")
        h.addWidget(cnt)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("danger")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip(f"删除标签「{name}」")
        del_btn.clicked.connect(partial(self._on_delete_label, name))
        h.addWidget(del_btn)
        return container

    # ------------------------------------------------------------------ #
    # 子类扩展页：在 QTabWidget 中追加功能 Tab
    # ------------------------------------------------------------------ #
    def populate_param_panel(self, tabs: QTabWidget) -> None:
        """子类实现：向 ``tabs`` 追加自己的参数页。

        例如：
            page = QWidget()
            lay = QVBoxLayout(page); ...
            tabs.addTab(page, "标注")
        """
        page = QWidget()
        tip = QLabel("（由具体标注工具实现参数面板）")
        tip.setStyleSheet("font-size: 12px; color: #94A3B8;")
        v = QVBoxLayout(page)
        v.addWidget(tip)
        tabs.addTab(page, "参数")

    # ------------------------------------------------------------------ #
    # 缩放联动
    # ------------------------------------------------------------------ #
    def set_canvas(self, canvas) -> None:
        self.canvas = canvas
        if canvas is not None and hasattr(canvas, "sig_zoom_changed"):
            canvas.sig_zoom_changed.connect(self.set_zoom)
            if hasattr(canvas, "set_tool"):
                canvas.set_tool(self.active_tool)

    def set_zoom(self, scale: float) -> None:
        pct = int(round(scale * 100))
        self.zoom_label.setText(f"{pct}%")
        self.zoom_label.setToolTip(f"画布缩放比例 {pct}%（画布内滚轮亦可缩放）")

    def zoom_in(self) -> None:
        if self.canvas is not None and hasattr(self.canvas, "zoom_in"):
            self.canvas.zoom_in()

    def zoom_out(self) -> None:
        if self.canvas is not None and hasattr(self.canvas, "zoom_out"):
            self.canvas.zoom_out()

    # ------------------------------------------------------------------ #
    # 刷新
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """刷新底部样本条 / 标签管理（子类在 super() 后刷自己）。"""
        self.strip.refresh()
        self.refresh_label_list()
