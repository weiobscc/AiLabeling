"""算法引擎包。

引擎负责把一张图像变成检测/分割等结构化结果。所有引擎遵循统一接口
``predict(sample, image)``，因此 UI 与流程只依赖抽象层；从 Mock 切换到
真实 ultralytics / Paddle 推理只需替换工厂实现，数据流无需改动。
"""
from __future__ import annotations

from typing import Any, Dict

from alg.engines.yolo_detector import MockYoloDetector, create_detector

__all__ = ["MockYoloDetector", "create_detector"]


def make_detector(tool_id: str, params: Dict[str, Any]):
    """按工具与参数创建检测器实例（当前固定 Mock，后续按 engine 字段分发）。"""
    return create_detector(tool_id, params)
