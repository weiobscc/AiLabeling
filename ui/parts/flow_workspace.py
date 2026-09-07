"""公用界面 —— 右侧工作区容器：承载「一份数据给多个标注/推理工具」的运行环境。

布局（对齐参考工作台，去掉左侧竖列样本库）：
    ┌──────────────────────────────────────────────┐
    │  按工具切换的页面（全宽承载工作台）：           │
    │   · 加载图片（数据源）                         │
    │   · 矩形框标注（人工，自带工作台外壳）           │
    │   · 目标检测（AI 预标注，自带工作台外壳）        │
    │   · 生成数据集（导出）                         │
    │   · 流程依赖（信息）                           │
    └──────────────────────────────────────────────┘
  样本浏览统一落在工作台底部的横向缩略图条（SampleStrip）。

核心：全部页面共享同一个 :class:`RuntimeSession`，因此：
    - 「加载图片」节点只负责一次扫描，样本在各工作台底部列出；
    - 流程中任意标注/推理工具点击后，各自页面直接消费这批样本；
    - 工具写入的标注通过 producer 归属，互不覆盖。
"""
from __future__ import annotations

import os
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImageReader
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from alg.tools_registry import get_tool, kind_of
from core.schema import Sample
from core.session import RuntimeSession
from ui.common.tool_base_window import ToolBasePanel
from ui.tools.annotate_page import AnnotatePage
from ui.tools.detect_page import DetectPage
from ui.tools.export_page import ExportPage

_LINK_STYLE = """
QPushButton { background: #2563EB; color: white; border: none; border-radius: 6px;
  padding: 6px 16px; font-size: 13px; font-weight: 600; }
QPushButton:hover { background: #1D4ED8; }
QPushButton:pressed { background: #1E40AF; }
"""


class SourcePage(QWidget):
    """「加载图片」数据源页：选择文件夹并说明共享语义。"""

    def __init__(self, ws) -> None:
        super().__init__()
        self.ws = ws
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        title = QLabel("加载图片 · 数据源")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A;")
        root.addWidget(title)

        tip = QLabel(
            "选择一个包含图片的文件夹作为数据源。\n"
            "扫描出的图片构成共享样本池，流程中所有标注 / 推理工具"
            "（可并行添加）都消费同一份数据：\n"
            "　· 矩形框标注 —— 逐张人工标注\n"
            "　· 目标检测　—— 对同一批图批量生成 AI 候选框\n"
            "　· 生成数据集 —— 将标注导出为 YOLO 格式（写入当前工程目录）\n"
            "各工具只写自己来源的标注，互不覆盖。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(
            "font-size: 12px; color: #475569; background: #EFF6FF;"
            " border: 1px solid #BFDBFE; border-radius: 8px; padding: 12px;"
        )
        root.addWidget(tip)

        self.btn_choose = QPushButton("📁  选择图片文件夹")
        self.btn_choose.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_choose.setStyleSheet(_LINK_STYLE)
        self.btn_choose.clicked.connect(lambda: self.ws.open_folder_dialog())
        root.addWidget(self.btn_choose, 0, Qt.AlignmentFlag.AlignLeft)

        self.folder_label = QLabel("尚未选择文件夹")
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet(
            "font-size: 12px; color: #64748B; padding: 2px;"
        )
        root.addWidget(self.folder_label)

        self.stat_label = QLabel("")
        self.stat_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #059669;"
        )
        root.addWidget(self.stat_label)

        hint = QLabel(
            "之后：点击工作台底部的样本缩略图即可标注/查看；\n"
            "点击流程中的「目标检测」切换为 AI 预标注视图。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #94A3B8; padding-top: 8px;")
        root.addWidget(hint)
        root.addStretch()

    def refresh(self) -> None:
        s = self.ws.session
        if not s.folder:
            self.folder_label.setText("尚未选择文件夹")
            self.stat_label.setText("")
        else:
            self.folder_label.setText(f"当前文件夹：{s.folder}")
            labeled = sum(1 for sm in s.samples if s.has_manual(sm))
            self.stat_label.setText(
                f"共 {len(s.samples)} 张图片 · {labeled} 张已有人工标注"
            )


class FlowWorkspace(QWidget):
    """右侧工作区主容器。"""

    # 消息上报（主窗口接到状态栏）
    sig_message = pyqtSignal(str, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.session = RuntimeSession()
        self._active_kind = ""
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.pages = QStackedWidget()
        self.source_page = SourcePage(self)
        self.annotate_page = AnnotatePage(self)
        self.detect_page = DetectPage(self)
        self.export_page = ExportPage(self)
        self.info_page = ToolBasePanel()
        info_host = QWidget()
        lay = QVBoxLayout(info_host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.info_page)
        self._info_host = info_host

        for w in (self.source_page, self.annotate_page,
                  self.detect_page, self.export_page, info_host):
            self.pages.addWidget(w)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.pages)
        self.setLayout(root)

        # 初始：数据源引导
        self.pages.setCurrentWidget(self.source_page)
        self.source_page.refresh()

    # ------------------------------------------------------------------ #
    # 消息
    # ------------------------------------------------------------------ #
    def message(self, text: str, timeout: int = 3000) -> None:
        self.sig_message.emit(text, timeout)

    # ------------------------------------------------------------------ #
    # 数据源（加载图片）
    # ------------------------------------------------------------------ #
    def open_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择图片文件夹", os.path.expanduser("~")
        )
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder: str) -> None:
        """扫描文件夹并重建样本池（数据源工具的核心动作）。"""
        samples = self.session.load_folder(folder, recursive=True)
        self._backfill_sizes(samples)
        self.refresh_all()
        self.message(f"数据源已就绪：扫描到 {len(samples)} 张图片", 3000)
        if samples and self._active_kind in ("", "source"):
            # 有样本时默认进入标注页，方便直接查看
            self.activate_tool("rect_label", "矩形框标注")

    def add_samples_dialog(self) -> None:
        """底部「＋」：向样本池追加图片。"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "添加样本图片",
            os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)",
        )
        if files:
            self.add_samples(files)

    def add_samples(self, paths: List[str]) -> None:
        added = self.session.add_files(paths)
        self._backfill_sizes(added)
        self.refresh_all()
        self.message(f"已添加 {len(added)} 张样本", 3000)

    @staticmethod
    def _backfill_sizes(samples: List[Sample]) -> None:
        # 回填图像尺寸（QImageReader 只读头部，不整图解码）
        for sm in samples:
            try:
                size = QImageReader(sm.path).size()
                if size.isValid():
                    sm.width, sm.height = size.width(), size.height()
            except Exception:  # noqa: BLE001 - 个别损坏文件不影响整体
                sm.width = sm.height = 0

    def set_current_sample_index(self, index: int) -> None:
        """底部样本条回调：切换当前样本并刷新各页。"""
        if self.session.set_current_by_index(index):
            self.refresh_all()
            if self._active_kind in ("", "source"):
                # 首次切换样本：若无明确工具页则跳到标注页查看
                self.pages.setCurrentWidget(self.annotate_page)
                self.annotate_page.refresh()

    def refresh_all(self) -> None:
        self.source_page.refresh()
        self.annotate_page.refresh()
        self.detect_page.refresh()
        self.export_page.refresh()

    # ------------------------------------------------------------------ #
    # 工具切换（点击流程图节点时）
    # ------------------------------------------------------------------ #
    def activate_tool(self, tool_id: str, _name: str = "") -> None:
        """流程图节点被点击/添加后，切换到该工具对应的工作区页面。"""
        try:
            meta = get_tool(tool_id)
        except KeyError:
            self.message(f"未知工具：{tool_id}", 3000)
            return
        kind = kind_of(meta)
        self._active_kind = kind

        if kind == "source":
            self.pages.setCurrentWidget(self.source_page)
            self.source_page.refresh()
            self.message("已打开数据源：加载图片工具", 2000)
            return
        if kind == "annotate" and tool_id == "rect_label":
            self.annotate_page.set_tool_info(meta["name"])
            self.annotate_page.refresh()
            self.pages.setCurrentWidget(self.annotate_page)
            self.message("已打开矩形框标注：拖拽绘制人工框", 2000)
            return
        if kind == "infer" and tool_id == "yolo_detect":
            self.detect_page.set_tool_info(
                f"{meta['name']}（Mock 引擎 · 数据流演示）"
            )
            self.detect_page.refresh()
            self.pages.setCurrentWidget(self.detect_page)
            self.message("已打开目标检测：对共享样本批量预标注", 2000)
            return
        if kind == "export":
            self.export_page.set_tool_info(meta["name"])
            self.export_page.refresh()
            self.pages.setCurrentWidget(self.export_page)
            self.message("已打开生成数据集：将已标注样本导出为 YOLO 格式", 2000)
            return
        # 其余工具：右侧展示其流程依赖信息
        try:
            self.info_page.show_dependency(tool_id)
        except KeyError:
            self.message(f"未知工具：{tool_id}", 3000)
            return
        self.pages.setCurrentWidget(self._info_host)
        self.message(f"已显示「{meta['name']}」信息", 2000)

    # ------------------------------------------------------------------ #
    # 「▶ 执行」入口：加载图片 → 流程内推理工具批量预标注 → 生成数据集
    # ------------------------------------------------------------------ #
    def run_flow(self, tool_ids: List[str]) -> None:
        """按流程顺序执行可自动运行的节点。"""
        if not tool_ids:
            self.message("请先向流程中添加工具", 3000)
            return
        if not self.session.folder or not self.session.samples:
            self.message("请先在「加载图片」中选择图片文件夹", 3000)
            self.activate_tool("image_loader", "加载图片")
            return

        unique_ids = list(dict.fromkeys(tool_ids))
        infer_ids = [tid for tid in unique_ids if kind_of(get_tool(tid)) == "infer"]
        annotate_ids = [tid for tid in unique_ids if kind_of(get_tool(tid)) == "annotate"]
        export_ids = [tid for tid in unique_ids if kind_of(get_tool(tid)) == "export"]

        parts: List[str] = []
        if infer_ids:
            names = [get_tool(tid)["name"] for tid in infer_ids]
            parts.append(" + ".join(names))
            self.detect_page.run_all()
        if annotate_ids:
            parts.append("人工标注（需在标注页逐张完成）")
        self.refresh_all()
        if export_ids:
            names = [get_tool(tid)["name"] for tid in export_ids]
            parts.append(" + ".join(names))
            self.export_page.generate()
        self.refresh_all()
        if parts:
            self.message("执行完成：" + "；".join(parts), 4000)
