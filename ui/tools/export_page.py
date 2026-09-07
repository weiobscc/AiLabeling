"""「生成数据集」导出页（export_yolo）。

把共享样本池中已标注（默认仅人工真值）的 rect 标注
导出为 YOLO 检测格式数据集，写入当前工程目录：
    <工程目录>/yolo_dataset/
      ├── images/  labels/  data.yaml  classes.txt

本页只读样本池，不改变任何标注；可重复导出覆盖上次产物。
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.exporter.yolo_exporter import export_yolo_dataset, preview_export

# 当前工程目录（ui/tools/.. → 工程根），作为默认输出根
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DEFAULT_OUT = os.path.join(_PROJECT_ROOT, "yolo_dataset")

_LINK_STYLE = """
QPushButton { background: #10B981; color: white; border: none; border-radius: 6px;
  padding: 6px 16px; font-size: 13px; font-weight: 600; }
QPushButton:hover { background: #059669; }
QPushButton:pressed { background: #047857; }
"""

_BTN = """
QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px;
  padding: 4px 10px; font-size: 12px; color: #334155; }
QPushButton:hover { background: #F1F5F9; }
QPushButton:disabled { color: #CBD5E1; }
"""


class ExportPage(QWidget):
    """生成数据集导出页。"""

    def __init__(self, ws) -> None:
        super().__init__()
        self.ws = ws
        self.session = ws.session
        self._last_out = _DEFAULT_OUT
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.title = QLabel("生成数据集 · YOLO 检测格式导出")
        self.title.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #1E293B; padding: 2px;"
        )
        root.addWidget(self.title)

        # 选项行
        opt = QHBoxLayout()
        opt.setSpacing(10)
        self.chk_auto = QCheckBox("包含 AI 预标注（默认仅人工真值）")
        self.chk_auto.setStyleSheet("font-size: 12px; color: #475569;")
        self.chk_copy = QCheckBox("复制图片到数据集目录")
        self.chk_copy.setChecked(True)
        self.chk_copy.setStyleSheet("font-size: 12px; color: #475569;")
        opt.addWidget(self.chk_auto)
        opt.addWidget(self.chk_copy)
        self.btn_preview = QPushButton("刷新统计")
        self.btn_preview.setStyleSheet(_BTN)
        self.btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        opt.addStretch()
        opt.addWidget(self.btn_preview)
        root.addLayout(opt)

        # 输出目录行
        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        dir_row.addWidget(QLabel("输出目录："))
        self.dir_edit = QLineEdit(self._last_out)
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setStyleSheet(
            "QLineEdit { border: 1px solid #CBD5E1; border-radius: 6px;"
            " padding: 3px 8px; font-size: 12px; background: #F8FAFC;"
            " color: #334155; }"
        )
        dir_row.addWidget(self.dir_edit, 1)
        self.btn_browse = QPushButton("更改…")
        self.btn_browse.setStyleSheet(_BTN)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        dir_row.addWidget(self.btn_browse)
        root.addLayout(dir_row)

        # 预览统计
        self.preview_label = QLabel("")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet(
            "font-size: 12px; color: #475569; background: #F0FDF4;"
            " border: 1px solid #BBF7D0; border-radius: 6px; padding: 8px;"
        )
        root.addWidget(self.preview_label)

        # 动作
        act = QHBoxLayout()
        self.btn_generate = QPushButton("📦  生成数据集")
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.setStyleSheet(_LINK_STYLE)
        self.btn_open = QPushButton("打开输出文件夹")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setStyleSheet(_BTN)
        act.addWidget(self.btn_generate)
        act.addWidget(self.btn_open)
        act.addStretch()
        root.addLayout(act)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            "QPlainTextEdit { border: 1px solid #E2E8F0; border-radius: 6px;"
            " background: #0F172A; color: #E2E8F0; font-family: Consolas,"
            " 'Courier New', monospace; font-size: 12px; padding: 6px; }"
        )
        root.addWidget(self.log, 1)

        # 接线
        self.chk_auto.toggled.connect(self.refresh)
        self.chk_copy.toggled.connect(self.refresh)
        self.btn_preview.clicked.connect(self.refresh)
        self.btn_browse.clicked.connect(self._browse)
        self.btn_generate.clicked.connect(self.generate)
        self.btn_open.clicked.connect(self._open_output)

    # ------------------------------------------------------------------ #
    def _current_dir(self) -> str:
        text = self.dir_edit.text().strip()
        return text or _DEFAULT_OUT

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择数据集输出目录", self._current_dir()
        )
        if folder:
            self._last_out = folder
            self.dir_edit.setText(folder)
            self.refresh()

    def _open_output(self) -> None:
        out = self._current_dir()
        if not os.path.isdir(out):
            self.ws.message("输出目录还不存在，请先生成数据集", 3000)
            return
        try:
            os.startfile(out)  # noqa: S606 - Windows 下打开资源管理器
        except OSError:
            self.ws.message(f"无法打开目录：{out}", 3000)

    # ------------------------------------------------------------------ #
    def set_tool_info(self, name: str) -> None:
        self.title.setText(f"{name} · YOLO 检测格式导出")

    def refresh(self) -> None:
        s = self.session
        if not s.samples:
            self.preview_label.setText(
                "尚无数据：请先通过「加载图片」选择文件夹并完成标注。"
            )
            self.btn_generate.setEnabled(False)
            return
        self.btn_generate.setEnabled(True)
        inc = self.chk_auto.isChecked()
        st = preview_export(s.samples, include_auto=inc)
        src = "人工 + AI" if inc else "仅人工真值"
        no_manual = sum(
            1 for sm in s.samples if sm.manual_annotations()
        )
        self.preview_label.setText(
            f"来源：{src}　样本 {len(s.samples)} 张 · 人工已标注 {no_manual} 张\n"
            f"将导出：{st['images']} 张图 · {st['boxes']} 个框 · "
            f"{st['classes']} 个类别"
            + (f"\n（{st['empty']} 张无有效标注会被跳过）" if st["empty"] else "")
        )

    # ------------------------------------------------------------------ #
    def generate(self) -> None:
        """执行导出（供页面按钮与 ▶ 执行共用）。"""
        if not self.session.samples:
            self.ws.message("没有数据可导出：请先加载图片并标注", 3000)
            return
        out = self._current_dir()
        try:
            report = export_yolo_dataset(
                self.session.samples,
                out,
                include_auto=self.chk_auto.isChecked(),
                copy_images=self.chk_copy.isChecked(),
            )
        except OSError as exc:  # noqa: BLE001 - 写盘异常给用户可见提示
            self.log.appendPlainText(f"[错误] 写入失败：{exc}")
            self.ws.message(f"导出失败：{exc}", 4000)
            return

        lines = [report.summary(), "", "生成产物：", f"  {os.path.abspath(out)}"]
        lines.append("  ├─ data.yaml / classes.txt")
        lines.append("  ├─ labels/*.txt")
        if report.copied_images:
            lines.append("  └─ images/*")
        else:
            lines.append("  └─ images 未复制（训练时引用原图）")
        if report.label_files:
            lines += ["", "labels 示例（类别 cx cy w h，归一化）："]
            try:
                with open(report.label_files[0], "r", encoding="utf-8") as f:
                    for _ in range(3):
                        row = f.readline()
                        if row:
                            lines.append(f"  {os.path.basename(report.label_files[0])}: {row.strip()}")
            except OSError:
                pass
        if report.exported_images == 0:
            lines.append("")
            lines.append("⚠ 没有任何包含有效标注的图片被导出（请先标注，或勾选包含 AI 预标注）。")
        self.log.setPlainText("\n".join(lines))
        if report.exported_images:
            self.ws.message(
                f"数据集已生成：{report.exported_images} 张 · {report.total_boxes} 框 → {out}",
                4000,
            )
        else:
            self.ws.message("未导出图片：没有可用的有效标注", 4000)
