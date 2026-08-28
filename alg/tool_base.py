"""标注工具基类抽象。

所有标注工具（通用工具 / YOLO 工具 / Paddle 工具）统一继承 :class:`ToolBase`，
UI 层（工具基类界面、依赖流程图、工具管理面板）均基于本模块的元数据渲染。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParamSpec:
    """单个工具参数的规格描述，用于自动生成参数表单。"""

    key: str  # 参数键名
    label: str  # 界面显示名称
    type: str = "str"  # 参数类型: int / float / str / bool / combo
    default: Any = None  # 默认值
    options: List[str] = field(default_factory=list)  # combo 类型时的候选项
    description: str = ""  # 参数说明


class ToolBase(ABC):
    """所有标注工具的抽象基类。

    子类只需实现 :meth:`run`，元数据（名称、分组、分类、参数等）在初始化时传入，
    也可通过 :meth:`meta` 直接构造注册表条目。
    """

    def __init__(
        self,
        tool_id: str,
        name: str,
        group: str = "通用工具",  # 所属工具组：通用工具 / YOLO工具 / Paddle工具
        category: str = "",  # 分类：检测 / 分割 / 分类 / 关键点 / OCR ...
        description: str = "",
        params: Optional[List[ParamSpec]] = None,
        dependencies: Optional[List[str]] = None,  # 依赖的工具 id 列表
    ) -> None:
        self.tool_id = tool_id
        self.name = name
        self.group = group
        self.category = category
        self.description = description
        self.params: List[ParamSpec] = params or []
        self.dependencies: List[str] = dependencies or []

    # ------------------------------------------------------------------ #
    # 元数据
    # ------------------------------------------------------------------ #
    def meta(self) -> Dict[str, Any]:
        """返回注册表条目所需的元数据字典。"""
        return {
            "id": self.tool_id,
            "name": self.name,
            "group": self.group,
            "category": self.category,
            "description": self.description,
            "params": [
                {
                    "key": p.key,
                    "label": p.label,
                    "type": p.type,
                    "default": p.default,
                    "options": p.options,
                    "description": p.description,
                }
                for p in self.params
            ],
            "dependencies": self.dependencies,
        }

    # ------------------------------------------------------------------ #
    # 子类实现
    # ------------------------------------------------------------------ #
    @abstractmethod
    def run(self, context: Optional[Dict[str, Any]] = None, **params: Any) -> Any:
        """执行标注工具。

        :param context: 运行上下文（图像、标注数据、项目信息等）
        :param params: 用户填写的参数
        """
        raise NotImplementedError

    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """校验参数，返回错误信息列表（空列表表示通过）。"""
        errors: List[str] = []
        for spec in self.params:
            value = params.get(spec.key)
            if value is None or value == "":
                continue
            try:
                if spec.type == "int":
                    int(value)
                elif spec.type == "float":
                    float(value)
            except (TypeError, ValueError):
                errors.append(f"参数「{spec.label}」类型不合法")
        return errors

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"<{self.__class__.__name__} {self.group}/{self.category}:{self.name}>"
