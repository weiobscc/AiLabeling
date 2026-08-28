"""标注工具注册表。

集中定义全部标注工具（通用工具 / YOLO 工具 / Paddle 工具），
供 UI 层的依赖流程图、工具管理面板、工具基类界面共同使用。

数据结构：
    TOOL_GROUPS: 工具组列表，每一项为
        {"name": 组名, "icon": 图标字符, "description": 组说明}
    TOOL_REGISTRY: 工具字典，键为工具 id，值为工具元数据（见 ToolBase.meta）。
"""
from __future__ import annotations

from typing import Any, Dict, List

# ---------------------------------------------------------------------- #
# 工具组定义（左侧面板的三个 list）
# ---------------------------------------------------------------------- #
TOOL_GROUPS: List[Dict[str, Any]] = [
    {
        "name": "通用工具",
        "icon": "🛠",
        "description": "与算法框架无关的基础标注工具",
    },
    {
        "name": "YOLO工具",
        "icon": "🎯",
        "description": "基于 YOLO 系列算法的标注/推理工具",
    },
    {
        "name": "Paddle工具",
        "icon": "🐳",
        "description": "基于 PaddlePaddle 生态的标注/推理工具",
    },
]

# ---------------------------------------------------------------------- #
# 工具注册表
# ---------------------------------------------------------------------- #
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ------------------------- 通用工具 ------------------------- #
    "rect_label": {
        "id": "rect_label",
        "name": "矩形框标注",
        "group": "通用工具",
        "category": "基础标注",
        "description": "通过拖拽绘制矩形标注框，是最常用的目标标注方式。",
        "dependencies": ["tool_base"],
        "params": [
            {"key": "label", "label": "默认标签", "type": "str", "default": "object",
             "description": "新建矩形框时默认使用的标签"},
            {"key": "line_width", "label": "线宽", "type": "int", "default": 2,
             "description": "矩形框绘制线宽（像素）"},
            {"key": "fill_opacity", "label": "填充透明度", "type": "float", "default": 0.2,
             "description": "矩形框内部填充透明度，0~1"},
        ],
    },
    "polygon_label": {
        "id": "polygon_label",
        "name": "多边形标注",
        "group": "通用工具",
        "category": "基础标注",
        "description": "通过逐点单击构成多边形，适合不规则物体轮廓标注。",
        "dependencies": ["tool_base"],
        "params": [
            {"key": "label", "label": "默认标签", "type": "str", "default": "object",
             "description": "新建多边形时默认使用的标签"},
            {"key": "smooth", "label": "轮廓平滑", "type": "bool", "default": True,
             "description": "是否对多边形轮廓做平滑处理"},
        ],
    },
    "smart_label": {
        "id": "smart_label",
        "name": "智能辅助标注",
        "group": "通用工具",
        "category": "辅助标注",
        "description": "基于边缘检测的交互式智能辅助标注（预标注）。",
        "dependencies": ["tool_base"],
        "params": [
            {"key": "sensitivity", "label": "灵敏度", "type": "combo",
             "default": "中", "options": ["低", "中", "高"],
             "description": "边缘检测灵敏度"},
            {"key": "auto_confirm", "label": "自动确认", "type": "bool", "default": False,
             "description": "AI 建议框达到置信度后自动确认"},
        ],
    },
    "image_viewer": {
        "id": "image_viewer",
        "name": "图像浏览",
        "group": "通用工具",
        "category": "视图工具",
        "description": "图像缩放、平移、亮度对比度调节等视图辅助工具。",
        "dependencies": ["tool_base"],
        "params": [
            {"key": "zoom_step", "label": "缩放步长", "type": "float", "default": 1.2,
             "description": "鼠标滚轮每次缩放的比例"},
            {"key": "fit_window", "label": "适应窗口", "type": "bool", "default": True,
             "description": "打开图像时是否自动适应窗口"},
        ],
    },

    # ------------------------- YOLO 工具 ------------------------- #
    "yolo_detect": {
        "id": "yolo_detect",
        "name": "目标检测",
        "group": "YOLO工具",
        "category": "检测",
        "description": "使用 YOLO 模型自动检测图像中的目标并生成候选标注框。",
        "dependencies": ["tool_base", "yolo_engine"],
        "params": [
            {"key": "model", "label": "模型", "type": "combo",
             "default": "yolov8n", "options": ["yolov8n", "yolov8s", "yolov8m", "yolov8l"],
             "description": "使用的 YOLO 模型权重"},
            {"key": "conf", "label": "置信度阈值", "type": "float", "default": 0.45,
             "description": "低于该置信度的检测结果将被过滤"},
            {"key": "iou", "label": "IoU 阈值", "type": "float", "default": 0.5,
             "description": "NMS 去重时的 IoU 阈值"},
            {"key": "imgsz", "label": "推理尺寸", "type": "combo",
             "default": "640", "options": ["320", "640", "1280"],
             "description": "推理时图像缩放尺寸"},
        ],
    },
    "yolo_segment": {
        "id": "yolo_segment",
        "name": "实例分割",
        "group": "YOLO工具",
        "category": "分割",
        "description": "使用 YOLOv8-seg 模型输出实例掩码，自动生成多边形标注。",
        "dependencies": ["tool_base", "yolo_engine"],
        "params": [
            {"key": "model", "label": "模型", "type": "combo",
             "default": "yolov8n-seg", "options": ["yolov8n-seg", "yolov8s-seg", "yolov8m-seg"],
             "description": "使用的分割模型权重"},
            {"key": "conf", "label": "置信度阈值", "type": "float", "default": 0.4,
             "description": "低于该置信度的掩码将被过滤"},
            {"key": "point_count", "label": "多边形点数", "type": "int", "default": 64,
             "description": "掩码转多边形时的最大顶点数"},
        ],
    },
    "yolo_classify": {
        "id": "yolo_classify",
        "name": "图像分类",
        "group": "YOLO工具",
        "category": "分类",
        "description": "使用 YOLO 分类模型对整张图像打标签。",
        "dependencies": ["tool_base", "yolo_engine"],
        "params": [
            {"key": "model", "label": "模型", "type": "combo",
             "default": "yolov8n-cls", "options": ["yolov8n-cls", "yolov8s-cls"],
             "description": "使用的分类模型权重"},
            {"key": "topk", "label": "Top-K", "type": "int", "default": 5,
             "description": "保留置信度最高的前 K 个类别"},
        ],
    },
    "yolo_pose": {
        "id": "yolo_pose",
        "name": "姿态估计",
        "group": "YOLO工具",
        "category": "关键点",
        "description": "使用 YOLOv8-pose 输出关键点，自动生成人体姿态标注。",
        "dependencies": ["tool_base", "yolo_engine"],
        "params": [
            {"key": "model", "label": "模型", "type": "combo",
             "default": "yolov8n-pose", "options": ["yolov8n-pose", "yolov8s-pose"],
             "description": "使用的姿态模型权重"},
            {"key": "conf", "label": "关键点置信度", "type": "float", "default": 0.25,
             "description": "低于该置信度的关键点将被忽略"},
        ],
    },
    "yolo_obb": {
        "id": "yolo_obb",
        "name": "旋转框检测",
        "group": "YOLO工具",
        "category": "检测",
        "description": "使用 YOLOv8-OBB 检测旋转目标（如遥感图像中的车辆）。",
        "dependencies": ["tool_base", "yolo_engine"],
        "params": [
            {"key": "model", "label": "模型", "type": "combo",
             "default": "yolov8n-obb", "options": ["yolov8n-obb", "yolov8s-obb"],
             "description": "使用的旋转框模型权重"},
            {"key": "conf", "label": "置信度阈值", "type": "float", "default": 0.4,
             "description": "低于该置信度的结果将被过滤"},
        ],
    },

    # ------------------------- Paddle 工具 ------------------------- #
    "paddle_det": {
        "id": "paddle_det",
        "name": "目标检测",
        "group": "Paddle工具",
        "category": "检测",
        "description": "使用 PaddleDetection 系列模型自动生成检测框标注。",
        "dependencies": ["tool_base", "paddle_engine"],
        "params": [
            {"key": "model", "label": "模型", "type": "combo",
             "default": "ppyoloe_s", "options": ["ppyoloe_s", "ppyoloe_m", "ppyoloe_l"],
             "description": "使用的 PaddleDetection 模型"},
            {"key": "conf", "label": "置信度阈值", "type": "float", "default": 0.4,
             "description": "低于该置信度的检测结果将被过滤"},
        ],
    },
    "paddle_seg": {
        "id": "paddle_seg",
        "name": "语义分割",
        "group": "Paddle工具",
        "category": "分割",
        "description": "使用 PaddleSeg 输出像素级分割掩码，转成标注区域。",
        "dependencies": ["tool_base", "paddle_engine"],
        "params": [
            {"key": "model", "label": "模型", "type": "combo",
             "default": "deeplabv3p", "options": ["deeplabv3p", "ocrnet", "pp_liteseg"],
             "description": "使用的 PaddleSeg 模型"},
            {"key": "min_area", "label": "最小区域面积", "type": "int", "default": 50,
             "description": "小于该面积的连通域将被忽略"},
        ],
    },
    "paddle_ocr": {
        "id": "paddle_ocr",
        "name": "文字识别 OCR",
        "group": "Paddle工具",
        "category": "OCR",
        "description": "使用 PaddleOCR 检测并识别图像中的文字，生成文本标注。",
        "dependencies": ["tool_base", "paddle_engine"],
        "params": [
            {"key": "lang", "label": "语言", "type": "combo",
             "default": "ch", "options": ["ch", "en", "japan", "korean"],
             "description": "识别语言"},
            {"key": "use_gpu", "label": "使用 GPU", "type": "bool", "default": True,
             "description": "是否使用 GPU 加速推理"},
        ],
    },
    "paddle_cls": {
        "id": "paddle_cls",
        "name": "图像分类",
        "group": "Paddle工具",
        "category": "分类",
        "description": "使用 PaddleClas 对图像分类并自动打标签。",
        "dependencies": ["tool_base", "paddle_engine"],
        "params": [
            {"key": "model", "label": "模型", "type": "combo",
             "default": "PPLCNet", "options": ["PPLCNet", "ResNet50", "ViT_base"],
             "description": "使用的分类模型"},
            {"key": "topk", "label": "Top-K", "type": "int", "default": 5,
             "description": "保留置信度最高的前 K 个类别"},
        ],
    },
    "paddle_pose": {
        "id": "paddle_pose",
        "name": "关键点检测",
        "group": "Paddle工具",
        "category": "关键点",
        "description": "使用 PaddleDetection 姿态估计模型输出人体关键点标注。",
        "dependencies": ["tool_base", "paddle_engine"],
        "params": [
            {"key": "model", "label": "模型", "type": "combo",
             "default": "hrnet", "options": ["hrnet", "tinypose"],
             "description": "使用的姿态估计模型"},
            {"key": "conf", "label": "关键点置信度", "type": "float", "default": 0.3,
             "description": "低于该置信度的关键点将被忽略"},
        ],
    },
    # ------------------- 引擎/基座（作为流程图中非工具节点） ------------------- #
    "tool_base": {
        "id": "tool_base",
        "name": "工具基类",
        "group": "系统",
        "category": "基座",
        "description": "所有标注工具的抽象基类，提供参数校验与统一执行入口。",
        "dependencies": [],
        "params": [],
    },
    "yolo_engine": {
        "id": "yolo_engine",
        "name": "YOLO 引擎",
        "group": "系统",
        "category": "引擎",
        "description": "YOLO 推理引擎，封装模型加载、推理与结果解析。",
        "dependencies": ["tool_base"],
        "params": [],
    },
    "paddle_engine": {
        "id": "paddle_engine",
        "name": "Paddle 引擎",
        "group": "系统",
        "category": "引擎",
        "description": "PaddlePaddle 推理引擎，封装模型加载与推理。",
        "dependencies": ["tool_base"],
        "params": [],
    },
}


def get_tools_by_group(group_name: str) -> List[Dict[str, Any]]:
    """按工具组名称返回工具列表（保持注册表顺序）。"""
    return [t for t in TOOL_REGISTRY.values() if t["group"] == group_name]


def get_tool(tool_id: str) -> Dict[str, Any]:
    """按 id 获取工具元数据。"""
    return TOOL_REGISTRY[tool_id]
