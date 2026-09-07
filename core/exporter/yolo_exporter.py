"""YOLO 检测格式数据集导出（纯 Python）。

产物结构（自包含、可直接给 ultralytics 训练/校验）：
    <out>/
      ├── images/<unique>.jpg      # 复制图片（copy_images=False 时只生成引用）
      ├── labels/<unique>.txt      # 每行：cls cx cy w h（归一化，6 位小数）
      ├── data.yaml                # path/train/val/nc/names
      └── classes.txt              # 每行一个类别名，行号即类别 id

约定：
    - 只导出 type == "rect" 的标注（YOLO 检测无多边形/分割支持）；
    - 标注来源默认仅人工真值（producer == "manual"），可选并入 AI；
    - 无有效框或缺少尺寸的样本会跳过并计入报告。
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.schema import Annotation, PRODUCER_MANUAL, Sample


@dataclass
class YoloExportReport:
    """一次导出的统计结果。"""

    output_dir: str = ""
    classes: List[str] = field(default_factory=list)
    exported_images: int = 0      # 成功写入标签的图数
    total_boxes: int = 0          # 写入的框总数
    skipped_no_size: int = 0      # 缺少宽高，无法归一化
    skipped_empty: int = 0        # 过滤后无有效框
    skipped_bad_box: int = 0      # 越界/退化框数量（这些框被丢弃，不影响图片导出）
    copied_images: int = 0
    label_files: List[str] = field(default_factory=list)
    created_at: str = ""

    def summary(self) -> str:
        lines = [
            f"输出目录：{self.output_dir}",
            f"导出图片：{self.exported_images} 张 · 标注框 {self.total_boxes} 个",
            f"类别({len(self.classes)})：{', '.join(self.classes) if self.classes else '（无）'}",
        ]
        skips = []
        if self.skipped_empty:
            skips.append(f"无有效框 {self.skipped_empty} 张")
        if self.skipped_no_size:
            skips.append(f"缺尺寸 {self.skipped_no_size} 张")
        if self.skipped_bad_box:
            skips.append(f"退化框 {self.skipped_bad_box} 个已忽略")
        if skips:
            lines.append("跳过：" + "，".join(skips))
        return "\n".join(lines)


# ---------------------------------------------------------------------- #
# 框转换
# ---------------------------------------------------------------------- #
def _rect_to_yolo_line(
    cls_id: int, coords: List[float], width: int, height: int
) -> Optional[str]:
    """把像素 rect [x1,y1,x2,y2] 转 YOLO 一行；退化返回 None。"""
    if width <= 0 or height <= 0 or len(coords) < 4:
        return None
    x1, y1, x2, y2 = (float(coords[0]), float(coords[1]),
                      float(coords[2]), float(coords[3]))
    # 钳制到图像内，避免裁剪子图/越界框产生非法归一化
    x1 = max(0.0, min(float(width), x1))
    x2 = max(0.0, min(float(width), x2))
    y1 = max(0.0, min(float(height), y1))
    y2 = max(0.0, min(float(height), y2))
    bw = x2 - x1
    bh = y2 - y1
    if bw <= 0 or bh <= 0:
        return None
    cx = (x1 + x2) / 2.0 / width
    cy = (y1 + y2) / 2.0 / height
    wn = bw / width
    hn = bh / height
    if cx < 0 or cy < 0 or cx > 1 or cy > 1 or wn <= 0 or hn <= 0:
        return None
    return f"{cls_id} {cx:.6f} {cy:.6f} {wn:.6f} {hn:.6f}"


def _unique_stem(original_stem: str, _ext: str, used: set) -> str:
    """同图重名时追加序号，保证 images/labels 一一对应（按最终 stem 去重）。"""
    candidate = original_stem
    k = 1
    while candidate in used:
        candidate = f"{original_stem}_{k}"
        k += 1
    used.add(candidate)
    return candidate


# ---------------------------------------------------------------------- #
# 统计（供导出页预览，不写盘）
# ---------------------------------------------------------------------- #
def preview_export(
    samples: List[Sample], include_auto: bool = False
) -> Dict[str, int]:
    """统计将导出的图数/框数/类别数。"""
    counts: Dict[str, int] = {
        "images": 0, "boxes": 0, "classes": 0, "no_size": 0, "empty": 0,
    }
    labels: set = set()
    for sm in samples:
        if sm.width <= 0 or sm.height <= 0:
            counts["no_size"] += 1
            continue
        box_ok = 0
        for ann in sm.annotations:
            if ann.type != "rect":
                continue
            if not include_auto and ann.is_auto:
                continue
            if len(ann.coords) >= 4:
                labels.add(ann.label)
                box_ok += 1
        if box_ok:
            counts["images"] += 1
            counts["boxes"] += box_ok
        else:
            counts["empty"] += 1
    counts["classes"] = len(labels)
    return counts


# ---------------------------------------------------------------------- #
# 主导出
# ---------------------------------------------------------------------- #
def export_yolo_dataset(
    samples: List[Sample],
    output_dir: str,
    include_auto: bool = False,
    copy_images: bool = True,
) -> YoloExportReport:
    """把样本池中有效的 rect 标注导出为 YOLO 检测数据集。

    重复运行会先重建 images / labels 子目录（只影响本数据集目录）。
    """
    report = YoloExportReport(output_dir=output_dir)
    images_dir = os.path.join(output_dir, "images")
    labels_dir = os.path.join(output_dir, "labels")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)

    # 重建内部产物（防止上次残留），不动目录外任何文件
    for sub in (images_dir, labels_dir):
        for fn in os.listdir(sub):
            p = os.path.join(sub, fn)
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass

    # 类别 id 稳定映射（按名称排序，与运行顺序无关）
    cls_set: set = set()
    for sm in samples:
        for ann in sm.annotations:
            if ann.type != "rect" or (not include_auto and ann.is_auto):
                continue
            if len(ann.coords) >= 4 and ann.label:
                cls_set.add(ann.label)
    cls_map: Dict[str, int] = {lb: i for i, lb in enumerate(sorted(cls_set))}
    report.classes = sorted(cls_set)

    used: set = set()
    written = 0
    for sm in sorted(samples, key=lambda s: s.path):
        if sm.width <= 0 or sm.height <= 0:
            report.skipped_no_size += 1
            continue
        lines: List[str] = []
        for ann in sm.annotations:
            if ann.type != "rect" or (not include_auto and ann.is_auto):
                continue
            if ann.label not in cls_map:
                continue
            line = _rect_to_yolo_line(cls_map[ann.label], ann.coords,
                                      sm.width, sm.height)
            if line is None:
                report.skipped_bad_box += 1
                continue
            lines.append(line)
        if not lines:
            report.skipped_empty += 1
            continue

        stem, ext = os.path.splitext(sm.path)
        stem = _unique_stem(os.path.basename(stem), ext.lower(), used)
        txt_path = os.path.join(labels_dir, f"{stem}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        report.label_files.append(txt_path)
        report.total_boxes += len(lines)

        if copy_images:
            dst = os.path.join(images_dir, f"{stem}{ext.lower()}")
            try:
                shutil.copyfile(sm.path, dst)
                report.copied_images += 1
            except OSError:
                pass
        written += 1

    report.exported_images = written
    _write_meta(output_dir, report, copy_images)
    return report


def _write_meta(
    output_dir: str, report: YoloExportReport, copy_images: bool
) -> None:
    """写出 data.yaml 与 classes.txt。"""
    names = "\n".join(f"  {i}: {lb}" for i, lb in enumerate(report.classes))
    yaml_text = "\n".join([
        "# 由 AiLabeling「生成数据集」导出（YOLO 检测格式）",
        f"# 类别: {', '.join(report.classes) if report.classes else '无'}",
        f"# 图片: {report.exported_images} · 标签行: {report.total_boxes}",
        f"path: {os.path.abspath(output_dir)}",
        "train: images",
        "val: images",
        f"nc: {len(report.classes)}",
        "names:",
        names,
        "",
    ])
    meta_yaml = os.path.join(output_dir, "data.yaml")
    with open(meta_yaml, "w", encoding="utf-8") as f:
        f.write(yaml_text)

    cls_txt = os.path.join(output_dir, "classes.txt")
    with open(cls_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(report.classes) + "\n")

    readme = os.path.join(output_dir, "README.txt")
    with open(readme, "w", encoding="utf-8") as f:
        f.write(
            "AiLabeling 导出说明（YOLO detection）\n"
            f"输出目录: {os.path.abspath(output_dir)}\n"
            f"labels 每行: <class_id> <x_center> <y_center> <width> <height>（归一化）\n"
            f"类别映射见 classes.txt（行号即 id），训练配置见 data.yaml\n"
            f"图片来源: {'已复制至 images/' if copy_images else '训练时请引用原图路径'}\n"
        )
