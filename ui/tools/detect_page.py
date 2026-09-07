"""目标检测推理页（yolo_detect，当前 Mock 引擎），基于工作台基类。

    - 对单张 / 全部样本运行检测，结果写入对应样本的
      ``auto:yolo_detect:mock`` 标注（红色叠加显示）
    - 只覆盖本工具自己的 auto 结果，不动人工标注
    - 参数（模型 / 置信度）与注册表 yolo_detect 保持一致

Mock 结果基于图像路径 + 模型名做确定性生成：重跑同一张图结果一致，
便于演示「人工标注与 AI 预标注并存」而不会因重跑漂移。
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from alg.engines import create_detector
from alg.tools_registry import get_tool
from core.schema import Sample
from ui.tools.image_canvas import ImageCanvas
from ui.tools.view_common import build_overlays, sample_summary
from ui.tools.workbench import AnnotationWorkbench

_BTN = """
QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px;
  padding: 3px 10px; font-size: 12px; color: #334155; }
QPushButton:hover { background: #F1F5F9; }
QPushButton:disabled { color: #CBD5E1; }
"""

_RUN_BTN = """
QPushButton { background: #F59E0B; color: #FFFFFF; border: none; border-radius: 6px;
  padding: 4px 14px; font-size: 12px; font-weight: 600; }
QPushButton:hover { background: #D97706; }
QPushButton:pressed { background: #B45309; }
"""

# 本工具写入样本的 auto 前缀（清除/刷新时使用，人工标注不受影响）
AUTO_PREFIX = "auto:yolo_detect"


class DetectPage(AnnotationWorkbench):
    """目标检测推理页。"""

    # 目标检测为 AI 推理，工具条仅保留「选择」，绘图工具预留禁用
    default_active_tool = "select"

    def __init__(self, ws, parent=None) -> None:
        super().__init__(ws, parent)
        self._build_content()
        self.populate_param_panel(self.param_body)
        self.refresh()

    # ------------------------------------------------------------------ #
    # 中央内容
    # ------------------------------------------------------------------ #
    def tool_specs(self):
        specs = super().tool_specs()
        for s in specs:
            if s["id"] != "select":
                s["enabled"] = False
        return specs

    def _build_content(self) -> None:
        meta = get_tool("yolo_detect")
        models = [p["default"] for p in meta["params"] if p["key"] == "model"]
        models = models or ["yolov8n"]
        conf_default = 0.45
        for p in meta["params"]:
            if p["key"] == "conf":
                conf_default = p.get("default", 0.45)

        lay = self.content_lay

        self.title = QLabel("目标检测（Mock 引擎 · 数据流演示）")
        self.title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1E293B;"
        )
        self.title.setToolTip("AI 推理预标注（当前 Mock）：生成候选框供人工参考/修改")

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.title)
        bar.addStretch()
        bar.addWidget(QLabel("模型："))
        self.model_combo = QComboBox()
        for m in models:
            self.model_combo.addItem(f"{m}（模拟）")
        self.model_combo.setStyleSheet(
            "QComboBox { border: 1px solid #CBD5E1; border-radius: 6px;"
            " padding: 3px 8px; font-size: 12px; background: #FFFFFF; }"
        )
        bar.addWidget(self.model_combo)
        bar.addWidget(QLabel("置信度："))
        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.0, 0.99)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(float(conf_default))
        self.conf_spin.setStyleSheet(
            "QDoubleSpinBox { border: 1px solid #CBD5E1; border-radius: 6px;"
            " padding: 2px 4px; font-size: 12px; background: #FFFFFF; }"
        )
        bar.addWidget(self.conf_spin)
        lay.addLayout(bar)

        # 动作条
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_one = QPushButton("检测当前图")
        self.btn_all = QPushButton("检测全部图片")
        self.btn_clear = QPushButton("清除本工具结果")
        for b in (self.btn_one, self.btn_all):
            b.setStyleSheet(_RUN_BTN)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet(_BTN)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        actions.addWidget(self.btn_one)
        actions.addWidget(self.btn_all)
        actions.addWidget(self.btn_clear)

        self.show_manual = QCheckBox("显示人工标注")
        self.show_manual.setChecked(True)
        self.show_manual.setStyleSheet("font-size: 12px; color: #475569;")
        actions.addWidget(self.show_manual)
        actions.addStretch()
        lay.addLayout(actions)

        # 画布（预览检测结果）
        self.canvas = ImageCanvas()
        self.set_canvas(self.canvas)
        lay.addWidget(self.canvas, 1)

        # 接线
        self.btn_one.clicked.connect(self.run_current)
        self.btn_all.clicked.connect(self.run_all)
        self.btn_clear.clicked.connect(self.clear_all)
        self.show_manual.toggled.connect(self.refresh)

    # ------------------------------------------------------------------ #
    # 右侧参数面板（共享「标签管理」Tab + 本页「说明」Tab）
    # ------------------------------------------------------------------ #
    def populate_param_panel(self, tabs) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        self.sample_info = QLabel("尚无样本")
        self.sample_info.setWordWrap(True)
        self.sample_info.setStyleSheet(
            "font-size: 12px; color: #475569; background: #F8FAFC;"
            " border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px;"
        )
        lay.addWidget(self.sample_info)

        self.detect_note = QLabel(
            "检测结果按“auto:yolo_detect”写入样本，红色叠加显示，仅供人工参考。"
        )
        self.detect_note.setWordWrap(True)
        self.detect_note.setStyleSheet("font-size: 12px; color: #94A3B8;")
        lay.addWidget(self.detect_note)
        lay.addStretch()

        tabs.addTab(page, "说明")

    # ------------------------------------------------------------------ #
    def _model_name(self) -> str:
        text = self.model_combo.currentText()
        return text.split("（")[0].strip() if text else "yolov8n"

    def _conf(self) -> float:
        return float(self.conf_spin.value())

    def _detector(self):
        return create_detector(
            "yolo_detect", {"conf": self._conf(), "model": self._model_name()}
        )

    def _current(self) -> Optional[Sample]:
        return self.session.current()

    def _detect_sample(self, sample: Sample) -> int:
        """对单个样本执行检测并写回 auto 标注，返回检测框数。"""
        detector = self._detector()
        # 只清本工具的 auto 结果，保留人工标注
        sample.clear_producer(AUTO_PREFIX)
        dets = detector.predict(
            sample.width, sample.height, seed_text=f"{sample.path}:{self._model_name()}"
        )
        if not dets:
            return 0
        producer = f"auto:{detector.engine_id}"
        for d in dets:
            self.session.add_auto(
                sample,
                label=d.label,
                rect=d.bbox,
                producer=producer,
                confidence=d.confidence,
            )
        labels = [d.label for d in dets]
        self.session.observe_labels(labels)
        return len(dets)

    # ------------------------------------------------------------------ #
    # 对外操作
    # ------------------------------------------------------------------ #
    def run_current(self) -> None:
        sample = self._current()
        if sample is None:
            self.ws.message("请先在底部样本条中点击一张图片", 3000)
            return
        if not sample.width:
            self.ws.message("当前样本缺少尺寸信息，请重新扫描文件夹", 3000)
            return
        n = self._detect_sample(sample)
        self.refresh()
        self.ws.refresh_all()
        self.ws.message(f"当前图检测完成：{n} 个候选框", 2500)

    def run_all(self) -> None:
        if not self.session.samples:
            self.ws.message("没有可检测的样本：请先选择图片文件夹", 3000)
            return
        total = 0
        done = 0
        for sample in self.session.samples:
            if sample.width:
                total += self._detect_sample(sample)
                done += 1
        self.session.collect_labels()
        self.refresh()
        self.ws.refresh_all()
        msg = f"检测完成：{done} 张，共 {total} 个候选框（Mock 引擎）"
        self.ws.message(msg, 4000)

    def clear_all(self) -> None:
        cleared = sum(s.clear_producer(AUTO_PREFIX) for s in self.session.samples)
        self.refresh()
        self.ws.refresh_all()
        self.ws.message(f"已清除本工具结果：{cleared} 条", 3000)

    # ------------------------------------------------------------------ #
    def set_tool_info(self, name: str) -> None:
        self.title.setText(name)
        self.title.setToolTip(
            "AI 推理预标注（当前 Mock）：生成候选框供人工参考/修改"
        )

    def refresh(self) -> None:
        super().refresh()  # 底部样本条
        sample = self._current()
        if sample is None:
            self.canvas.set_image_path("")
            self.sample_info.setText("尚无样本\n请先加载图片文件夹并选择一个样本")
            return
        ok = self.canvas.set_image_path(sample.path)
        if not ok:
            self.sample_info.setText(f"无法加载图像：{sample.path}")
            return
        self.canvas.set_overlays(
            build_overlays(sample, show_manual=self.show_manual.isChecked(), show_auto=True)
        )
        self.sample_info.setText(
            f"{sample.name}（{sample.width}×{sample.height}）\n{sample_summary(sample)}"
        )
