"""标注/检测页共用的视图辅助：来源配色与叠加框构造。"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor

from core.schema import Annotation, Sample
from ui.tools.image_canvas import Overlay

# 人工标注（蓝） / AI 标注（红）
MANUAL_COLOR = QColor("#2563EB")
AUTO_COLOR = QColor("#EF4444")

# 类别配色（右侧标签面板使用，同一类别稳定同色）
_LABEL_PALETTE = [
    QColor("#2563EB"), QColor("#16A34A"), QColor("#F59E0B"),
    QColor("#EF4444"), QColor("#8B5CF6"), QColor("#06B6D4"),
    QColor("#EC4899"), QColor("#F97316"), QColor("#10B981"),
    QColor("#6366F1"),
]


def label_color(label: str) -> QColor:
    """按标签名稳定映射一个可读颜色（用于面板类别色块）。"""
    idx = sum(ord(c) for c in str(label)) % len(_LABEL_PALETTE)
    return _LABEL_PALETTE[idx]


def build_overlays(
    sample: Optional[Sample],
    show_manual: bool = True,
    show_auto: bool = True,
) -> List[Overlay]:
    """把样本上的标注转换为画布叠加层。"""
    if sample is None:
        return []
    overlays: List[Overlay] = []
    for ann in sample.annotations:
        if len(ann.coords) < 4:
            continue
        x1, y1, x2, y2 = ann.coords[:4]
        is_auto = ann.is_auto
        if is_auto and not show_auto:
            continue
        if not is_auto and not show_manual:
            continue
        color = AUTO_COLOR if is_auto else MANUAL_COLOR
        label = ann.label or ("AI" if is_auto else "?")
        overlays.append(
            Overlay(
                rect=QRectF(x1, y1, x2 - x1, y2 - y1),
                color=color,
                label=label,
                locked=ann.locked or is_auto,  # AI 框在人工画布上不可直接删除
                annotation=ann,
            )
        )
    return overlays


def sample_summary(sample: Optional[Sample]) -> str:
    """样本状态摘要（用于列表与状态栏）。"""
    if sample is None:
        return ""
    manual = len(sample.manual_annotations())
    auto = len(sample.auto_annotations())
    state = {
        "pending": "待标注",
        "labeled": "已标注",
        "skipped": "已跳过",
    }.get(sample.status, sample.status)
    return f"{sample.name} · 人工 {manual} · AI {auto} · {state}"
