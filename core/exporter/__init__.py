"""数据导出器（生成数据集工具的输出实现，纯 Python、不依赖 Qt）。"""
from __future__ import annotations

import os
from typing import List

from core.exporter.yolo_exporter import (
    YoloExportReport,
    export_yolo_dataset,
    preview_export,
)

__all__ = [
    "YoloExportReport",
    "export_yolo_dataset",
    "preview_export",
    "default_export_dir",
]


def default_export_dir(project_root: str) -> str:
    """当前工程目录下的默认数据集输出目录。"""
    return os.path.join(project_root, "yolo_dataset")


__doc__ = """core.exporter 提供「生成数据集」的实际输出能力。

当前支持 YOLO 检测格式导出：
    <out>/
      ├── images/        # 复制后的图片（或原图引用）
      ├── labels/        # 每图一个 <stem>.txt，每行 <cls> <cx> <cy> <w> <h>
      ├── data.yaml      # ultralytics 可直接使用的数据描述
      └── classes.txt    # 类别清单（行号即类别 id）
"""
