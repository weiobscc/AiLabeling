"""运行会话：多工具共享的同一份数据（样本池）。

设计要点：
    - ``folder`` / ``samples`` 由「加载图片」数据源工具填充，
      其后流程中的所有标注 / 推理工具都共享本会话里的同一批 Sample；
    - 各工具只通过 ``Sample.annotations`` 的 producer 增改自己的标注，
      实现「一份数据给多个标注工具 / 标注工具旁并行推理工具」；
    - 本模块不依赖 Qt：像素加载、缩略图等由 UI 层负责，
      图像尺寸由 UI 解码图片头部后回填到 ``Sample.width/height``。

线程模型：MVP 在 UI 线程直接运行，故不加锁；接入真实推理引擎后
再为耗时节点引入后台执行，届时由执行器持锁写入。
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Set

from core.schema import Annotation, Sample

# 支持的图像扩展名（与 QPixmap 支持范围保持一致）
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif")


class RuntimeSession:
    """共享数据会话（单例持有，UI 各页共用同一实例）。"""

    def __init__(self) -> None:
        self.folder: Optional[str] = None
        self.samples: List[Sample] = []
        self._index_by_id: Dict[str, int] = {}
        self.current_index: int = -1
        # 观察到的类别（人工 + AI 标注累积），用于标注页类别下拉建议
        self.labels: List[str] = ["object"]

    # ------------------------------------------------------------------ #
    # 数据源
    # ------------------------------------------------------------------ #
    def scan_folder(
        self, folder: str, recursive: bool = True
    ) -> List[str]:
        """扫描文件夹下全部图片路径（排序），不修改会话内容。

        图片尺寸不在扫描阶段读取（避免全量解码）。
        """
        found: List[str] = []
        if recursive:
            for root, _dirs, files in os.walk(folder):
                for fn in sorted(files):
                    if fn.lower().endswith(IMAGE_EXTS):
                        found.append(os.path.join(root, fn))
        else:
            for fn in sorted(os.listdir(folder)):
                full = os.path.join(folder, fn)
                if os.path.isfile(full) and fn.lower().endswith(IMAGE_EXTS):
                    found.append(full)
        return found

    def load_folder(
        self, folder: str, recursive: bool = True
    ) -> List[Sample]:
        """把指定文件夹作为数据源，重置样本池并构建 Sample 列表。"""
        self.folder = folder
        paths = self.scan_folder(folder, recursive)
        self.samples = [Sample(path=p) for p in paths]
        self._index_by_id = {
            s.sample_id: i for i, s in enumerate(self.samples)
        }
        self.current_index = 0 if self.samples else -1
        return self.samples

    def add_files(self, paths: List[str]) -> List[Sample]:
        """向样本池追加指定图片路径（去重），返回新增的 Sample 列表。

        不改动已有样本与当前选中项；若原本为空则顺带选中第一项。
        """
        existing = {s.path for s in self.samples}
        added: List[Sample] = []
        for p in paths:
            p = os.path.abspath(p)
            if p in existing:
                continue
            s = Sample(path=p)
            self.samples.append(s)
            existing.add(p)
            added.append(s)
        if added:
            self._index_by_id = {
                s.sample_id: i for i, s in enumerate(self.samples)
            }
            if self.current_index < 0:
                self.current_index = 0
        return added

    # ------------------------------------------------------------------ #
    # 当前样本与导航
    # ------------------------------------------------------------------ #
    @property
    def count(self) -> int:
        return len(self.samples)

    def current(self) -> Optional[Sample]:
        if 0 <= self.current_index < len(self.samples):
            return self.samples[self.current_index]
        return None

    def set_current_by_index(self, index: int) -> bool:
        if 0 <= index < len(self.samples):
            self.current_index = index
            return True
        return False

    def set_current_by_path(self, path: str) -> bool:
        idx = self._index_by_id.get(path, -1)
        if idx < 0:
            return False
        self.current_index = idx
        return True

    def step(self, delta: int) -> bool:
        """前进/后退（循环到头时钳制在边界，返回是否发生移动）。"""
        if not self.samples:
            return False
        target = self.current_index + delta
        if target < 0 or target >= len(self.samples):
            return False
        self.current_index = target
        return True

    def has_manual(self, sample: Sample) -> bool:
        return len(sample.manual_annotations()) > 0

    # ------------------------------------------------------------------ #
    # 类别收集
    # ------------------------------------------------------------------ #
    def observe_labels(self, labels) -> None:
        """把一批类别并入观察集合（供类别下拉建议）。"""
        changed = False
        for lb in labels:
            lb = str(lb).strip()
            if lb and lb not in self.labels:
                self.labels.append(lb)
                changed = True
        return changed

    def collect_labels(self) -> None:
        """从当前样本池所有标注中收集类别。"""
        for s in self.samples:
            for a in s.annotations:
                if a.label and a.label not in self.labels:
                    self.labels.append(a.label)

    # ------------------------------------------------------------------ #
    # 标签管理（供右侧「标签管理」面板新建/删除）
    # ------------------------------------------------------------------ #
    def add_label(self, name: str) -> bool:
        """注册一个标签（去空、去重）。"""
        name = str(name).strip()
        if not name or name in self.labels:
            return False
        self.labels.append(name)
        return True

    def remove_label(self, name: str, purge: bool = True) -> int:
        """注销一个标签；可选同时删除样本池中该标签的全部标注。

        返回被删除的标注条数。
        """
        name = str(name).strip()
        if name in self.labels:
            self.labels.remove(name)
        removed = 0
        if purge:
            for s in self.samples:
                for a in list(s.annotations):
                    if a.label == name:
                        s.remove_annotation(a)
                        removed += 1
        return removed

    # ------------------------------------------------------------------ #
    # 标注增删（辅助：真正的写入直接操作 Sample.annotations）
    # ------------------------------------------------------------------ #
    @staticmethod
    def add_manual(
        sample: Sample,
        label: str,
        rect: tuple,  # (x1, y1, x2, y2)，原图像素
    ) -> Annotation:
        ann = Annotation.new(label=label, coords=list(rect))
        sample.add_annotation(ann)
        return ann

    @staticmethod
    def add_auto(
        sample: Sample,
        label: str,
        rect: tuple,
        producer: str,
        confidence: Optional[float] = None,
        locked: bool = True,
    ) -> Annotation:
        ann = Annotation.new(
            label=label,
            coords=list(rect),
            producer=producer,
            confidence=confidence,
            locked=locked,
            meta={"ts": ""},
        )
        sample.add_annotation(ann)
        return ann
