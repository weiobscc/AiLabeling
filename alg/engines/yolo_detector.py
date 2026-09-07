"""目标检测引擎：统一接口 + Mock 实现。

设计目标：先以 Mock 引擎把「一份数据 → 多工具并行消费」的数据流跑通，
后续把真实模型接入时，只需新增一个实现 ``predict`` 的类并在
``create_detector`` 中按 ``params["engine"]`` 分发，流程图、画布、
标注归属均无需改动。
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------- #
# 检测结果结构（与 core.schema.Annotation 对齐，便于直接转写）
# ---------------------------------------------------------------------- #
class Detection:
    """单个检测结果：矩形框（原图像素，x1,y1,x2,y2）+ 类别 + 置信度。"""

    __slots__ = ("label", "bbox", "confidence")

    def __init__(self, label: str, bbox, confidence: float) -> None:
        self.label = label
        self.bbox = tuple(float(v) for v in bbox)  # (x1, y1, x2, y2)
        self.confidence = round(float(confidence), 4)

    @property
    def producer(self) -> str:
        return f"auto:{self.engine_id}"  # type: ignore[attr-defined]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "bbox": list(self.bbox),
            "confidence": self.confidence,
        }


class DetectorBase(ABC):
    """检测引擎抽象基类。"""

    engine_id: str = "unknown"  # 子类覆盖，作为 auto: 标注的来源标记

    def __init__(self, conf: float = 0.45, **options: Any) -> None:
        self.conf = conf
        self.options = options

    @abstractmethod
    def predict(self, width: int, height: int, seed_text: str = "") -> List[Detection]:
        """对单张图执行检测。

        Args:
            width / height: 图像尺寸（像素）。Mock 阶段未接入真实图像数据，
                仅需尺寸即可生成合理的候选框；真实引擎将由调用方改为
                传入图像数组的重载接口 predict_image(image)。
            seed_text:     确定性随机种子（Mock 用图像路径保证稳定结果）。

        Returns:
            检测结果列表（已按置信度过滤）。
        """
        raise NotImplementedError


class MockYoloDetector(DetectorBase):
    """模拟 YOLO 检测器：确定性生成 2~4 个候选框，用于打通数据流。

    说明：仅为演示「加载图片 → 目标检测 → 与人工标注并存」的架构，
    结果不代表真实模型输出。
    """

    engine_id = "yolo_detect:mock"

    _LABELS = [
        "person", "dog", "cat", "car", "truck",
        "bicycle", "bird", "chair",
    ]

    def predict(self, width: int, height: int, seed_text: str = "") -> List[Detection]:
        if width <= 0 or height <= 0:
            return []
        rnd = random.Random(seed_text or "mock")
        count = rnd.randint(2, 4)
        # 为避免每次运行结果不同导致「清除再生成」体验差，种子固定
        results: List[Detection] = []
        for _ in range(count):
            label = rnd.choice(self._LABELS)
            box_w = max(24.0, width * rnd.uniform(0.06, 0.38))
            box_h = max(24.0, height * rnd.uniform(0.06, 0.38))
            x1 = rnd.uniform(0, max(1.0, width - box_w))
            y1 = rnd.uniform(0, max(1.0, height - box_h))
            conf = rnd.uniform(0.42, 0.96)
            if conf < self.conf:  # 按置信度阈值过滤
                continue
            results.append(
                Detection(
                    label=label,
                    bbox=(x1, y1, x1 + box_w, y1 + box_h),
                    confidence=conf,
                )
            )
        return results


def create_detector(
    tool_id: str, params: Optional[Dict[str, Any]] = None
) -> DetectorBase:
    """创建检测器（工厂）。

    Mock 阶段固定返回 MockYoloDetector；后续按
    ``params.get("engine") in ("ultralytics", "paddle")`` 分发真实引擎。
    """
    params = params or {}
    if tool_id == "yolo_detect":
        return MockYoloDetector(conf=float(params.get("conf", 0.45)))
    # 其他检测类工具（如 paddle_det）暂回退到 Mock
    return MockYoloDetector(conf=float(params.get("conf", 0.45)))
