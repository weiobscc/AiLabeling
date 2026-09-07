"""核心数据模型（纯 Python，不依赖 Qt）。

坐标系约定：
    - 标注框（rect）坐标使用**原图像素坐标系**，以左上角为原点，
      存储形式为 [x1, y1, x2, y2]（x2/y2 为右下角，含端点）。
    - 后续接入预处理/裁剪后，此处保留 ``parent_id`` / ``transform`` 占位，
      保证裁剪子图仍能映射回原图坐标系（不阻塞本次落地）。

多工具共享说明：
    一份数据（Sample 池）可同时被多个工具消费。每个工具写入的标注通过
    ``producer`` 归属区分：
        - 人工标注：  producer == "manual"
        - AI 预标注： producer == "auto:<tool_id>[:<engine>]"
    各工具只增改自己 producer 的标注，互不覆盖。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 支持的标注类型（本轮实现 rect，其余为后续扩展预留）
ANN_TYPES = ("rect", "poly", "obb", "keypoint", "cls")

# 标注来源标记
PRODUCER_MANUAL = "manual"


@dataclass
class Annotation:
    """一条标注。

    Attributes:
        ann_id:    标注唯一 id（时间戳 + 序号生成）
        type:      标注类型（rect / poly / obb / keypoint / cls）
        label:     类别名（如 person / car）
        coords:    坐标。rect 为 [x1, y1, x2, y2]（原图像素坐标系）
        producer:  标注来源（manual 或 auto:<tool_id>）
        confidence:置信度（AI 标注有效，人工标注为 None）
        locked:    是否锁定（锁定标注不可在人工画布上被删除）
        meta:      扩展信息
    """

    ann_id: str
    type: str = "rect"
    label: str = "object"
    coords: List[float] = field(default_factory=list)
    producer: str = PRODUCER_MANUAL
    confidence: Optional[float] = None
    locked: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new(
        label: str,
        coords: List[float],
        producer: str = PRODUCER_MANUAL,
        confidence: Optional[float] = None,
        ann_type: str = "rect",
        locked: bool = False,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "Annotation":
        return Annotation(
            ann_id=f"{time.time_ns():x}",
            type=ann_type,
            label=label,
            coords=[float(v) for v in coords],
            producer=producer,
            confidence=confidence,
            locked=locked,
            meta=meta or {},
        )

    @property
    def is_auto(self) -> bool:
        return self.producer != PRODUCER_MANUAL


@dataclass
class Sample:
    """一个可被多个工具共享处理的样本（一张图，可能来自裁剪子图）。

    Attributes:
        path:         图像文件绝对路径
        sample_id:    唯一标识（默认取 path，便于跨工具引用同一份数据）
        width/height: 图像尺寸（像素），由加载端（解码图片头部）填充
        parent_id:    父样本 id（裁剪子图时非空，原图为空串）
        annotations:  全部工具写入的标注（按 producer 归属）
        status:       pending / labeled / skipped
        meta:         扩展字段（来源工具、检测时间等）
    """

    path: str
    sample_id: str = ""
    width: int = 0
    height: int = 0
    parent_id: str = ""
    annotations: List[Annotation] = field(default_factory=list)
    status: str = "pending"
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sample_id:
            self.sample_id = self.path
        if not self.meta:
            self.meta = {}

    # ------------------------------------------------------------------ #
    @property
    def name(self) -> str:
        import os

        return os.path.basename(self.path)

    def annotations_of(self, producer: str = "") -> List[Annotation]:
        """按 producer 过滤标注；producer 为空返回全部。

        producer 支持前缀匹配：传入 "auto:yolo_detect" 只匹配该工具，
        传入 "auto" 则匹配全部 AI 标注。
        """
        if not producer:
            return list(self.annotations)
        return [a for a in self.annotations
                if a.producer == producer or a.producer.startswith(producer)]

    def manual_annotations(self) -> List[Annotation]:
        return self.annotations_of(PRODUCER_MANUAL)

    def auto_annotations(self) -> List[Annotation]:
        return self.annotations_of("auto")

    def add_annotation(self, ann: Annotation) -> None:
        self.annotations.append(ann)

    def remove_annotation(self, ann: Annotation) -> None:
        if ann in self.annotations:
            self.annotations.remove(ann)

    def clear_producer(self, producer: str) -> int:
        """清除某个 producer 的全部标注，返回移除条数。

        支持前缀：clear_producer("auto:yolo_detect") 或 clear_producer("auto")。
        """
        before = len(self.annotations)
        self.annotations = [
            a for a in self.annotations
            if not (a.producer == producer or a.producer.startswith(producer))
        ]
        return before - len(self.annotations)
