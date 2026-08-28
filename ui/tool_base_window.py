"""工具基类界面。

所有标注工具（依赖流程图 / 工具管理面板中点击）统一跳转到本窗口。
窗口根据 alg.tools_registry 中的工具元数据自动生成：
    - 工具名称 / 分组 / 分类 / 描述
    - 参数配置表单（int / float / str / bool / combo 自动映射控件）
    - 「运行」按钮（占位，实际执行逻辑由 alg.ToolBase 子类接管）
"""
from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

from alg.tools_registry import get_tool, TOOL_GROUPS

# 分组 → 主题色（与流程图一致）
_GROUP_COLORS: Dict[str, str] = {
    "通用工具": "#0EA5E9",
    "YOLO工具": "#F59E0B",
    "Paddle工具": "#10B981",
    "系统": "#64748B",
}


class ToolBaseWindow(QDialog):
    """工具基类界面：展示工具元数据 + 参数表单 + 运行入口。"""

    def __init__(self, tool_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tool = get_tool(tool_id)
        self._param_widgets: Dict[str, QWidget] = {}
        self.setWindowTitle(f"{self._tool['name']} - 工具基类界面")
        self.setMinimumSize(560, 520)
        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # ---------- 标题区 ----------
        title_row = QHBoxLayout()
        group = self._tool["group"]
        color = _GROUP_COLORS.get(group, "#0EA5E9")

        badge = QLabel("●")
        badge.setStyleSheet(f"color: {color}; font-size: 26px;")
        badge.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(badge)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(self._tool["name"])
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #1E293B;")
        meta = QLabel(f"{group} · {self._tool['category']}")
        meta.setStyleSheet("font-size: 12px; color: #64748B;")
        title_box.addWidget(title)
        title_box.addWidget(meta)
        title_row.addLayout(title_box)
        title_row.addStretch()
        root.addLayout(title_row)

        # ---------- 描述 ----------
        desc = QLabel(self._tool["description"])
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 13px; color: #475569;")
        root.addWidget(desc)

        # ---------- 参数表单 ----------
        params_group = QGroupBox("参数配置")
        params_group.setStyleSheet(
            "QGroupBox { font-weight: 700; color: #334155; border: 1px solid #E2E8F0;"
            " border-radius: 8px; margin-top: 10px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        form = QFormLayout(params_group)
        form.setContentsMargins(14, 12, 14, 14)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(18)

        for spec in self._tool.get("params", []):
            widget = self._make_param_widget(spec)
            self._param_widgets[spec["key"]] = widget
            if spec.get("description"):
                label = QLabel(f"{spec['label']}\n<small>{spec['description']}</small>")
                label.setStyleSheet("color: #475569;")
            else:
                label = QLabel(spec["label"])
            form.addRow(label, widget)

        if not self._tool.get("params"):
            hint = QLabel("该工具无需配置参数。")
            hint.setStyleSheet("color: #94A3B8; padding: 8px 0;")
            form.addRow(hint)
        root.addWidget(params_group)

        # ---------- 依赖说明 ----------
        deps = self._tool.get("dependencies", [])
        dep_text = " → ".join(self._display_name(d) for d in deps) if deps else "无"
        dep_label = QLabel(f"依赖链路：{dep_text}")
        dep_label.setStyleSheet("font-size: 12px; color: #94A3B8;")
        root.addWidget(dep_label)

        # ---------- 运行日志（占位） ----------
        log_group = QGroupBox("运行日志")
        log_group.setStyleSheet(
            "QGroupBox { font-weight: 700; color: #334155; border: 1px solid #E2E8F0;"
            " border-radius: 8px; margin-top: 10px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        log_layout = QVBoxLayout(log_group)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("运行输出将显示在这里…")
        self._log.setMinimumHeight(110)
        self._log.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px;"
            "background: #0F172A; color: #E2E8F0; border: none; border-radius: 6px;"
        )
        log_layout.addWidget(self._log)
        root.addWidget(log_group)

        # ---------- 底部按钮 ----------
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        run_btn = QPushButton("▶ 运行工具")
        run_btn.setObjectName("primaryBtn")
        run_btn.setStyleSheet(
            "QPushButton#primaryBtn { background: #2563EB; color: white; border: none;"
            " border-radius: 6px; padding: 8px 26px; font-weight: 600; font-size: 14px; }"
            "QPushButton#primaryBtn:hover { background: #1D4ED8; }"
            "QPushButton#primaryBtn:pressed { background: #1E40AF; }"
        )
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(
            "QPushButton { background: #F1F5F9; color: #334155; border: 1px solid #E2E8F0;"
            " border-radius: 6px; padding: 8px 22px; font-size: 14px; }"
            "QPushButton:hover { background: #E2E8F0; }"
        )
        run_btn.clicked.connect(self._on_run)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(run_btn)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    # 参数控件映射
    # ------------------------------------------------------------------ #
    def _make_param_widget(self, spec: Dict[str, Any]) -> QWidget:
        ptype = spec.get("type", "str")
        default = spec.get("default")
        if ptype == "int":
            w = QSpinBox()
            w.setRange(-10_000_000, 10_000_000)
            if isinstance(default, int):
                w.setValue(default)
            return w
        if ptype == "float":
            w = QDoubleSpinBox()
            w.setRange(-1_000_000.0, 1_000_000.0)
            w.setDecimals(3)
            if isinstance(default, (int, float)):
                w.setValue(float(default))
            return w
        if ptype == "bool":
            w = QCheckBox()
            w.setChecked(bool(default))
            return w
        if ptype == "combo":
            w = QComboBox()
            w.addItems(spec.get("options", []))
            idx = w.findText(str(default))
            if idx >= 0:
                w.setCurrentIndex(idx)
            return w
        # str / 其他
        w = QLineEdit()
        if default is not None:
            w.setText(str(default))
        return w

    # ------------------------------------------------------------------ #
    # 数据读写
    # ------------------------------------------------------------------ #
    def _load_values(self) -> None:
        for key, widget in self._param_widgets.items():
            spec = next(
                (p for p in self._tool.get("params", []) if p["key"] == key), None
            )
            if spec is None:
                continue
            default = spec.get("default")
            if isinstance(widget, QSpinBox):
                if isinstance(default, int):
                    widget.setValue(default)
            elif isinstance(widget, QDoubleSpinBox):
                if isinstance(default, (int, float)):
                    widget.setValue(float(default))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(default))
            elif isinstance(widget, QComboBox):
                idx = widget.findText(str(default))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, QLineEdit):
                if default is not None:
                    widget.setText(str(default))

    def collect_params(self) -> Dict[str, Any]:
        """收集表单当前参数值。"""
        params: Dict[str, Any] = {}
        for key, widget in self._param_widgets.items():
            if isinstance(widget, QSpinBox):
                params[key] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                params[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                params[key] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                params[key] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                params[key] = widget.text()
        return params

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
    def _display_name(self, dep_id: str) -> str:
        try:
            return get_tool(dep_id)["name"]
        except KeyError:
            return dep_id

    def _on_run(self) -> None:
        """运行入口（占位）。后续在此接入 alg.ToolBase 子类的 run()。"""
        params = self.collect_params()
        summary = "、".join(f"{k}={v}" for k, v in params.items()) or "无参数"
        self._log.append(f"[{self._tool['name']}] 准备运行…")
        self._log.append(f"参数：{summary}")
        self._log.append("[占位] 算法执行逻辑尚未接入，请实现 alg.ToolBase.run()。")
        QMessageBox.information(
            self,
            "提示",
            "工具执行引擎尚未接入。\n"
            "当前为界面框架占位，后续可通过实现 alg.ToolBase 子类接入实际算法。",
        )
