"""工具界面模块：各具体标注/推理工具的操作页面。

约定：一个页面模块对应一类工具的操作界面（后续可再按工具拆分子目录）：
    annotate_page    矩形框标注工具页面（人工标注工作台）
    detect_page      目标检测工具页面（AI 预标注工作台）
    export_page      生成数据集工具页面（YOLO 导出）

配套组件（页面实现细节，随工具界面存放）：
    workbench        AnnotationWorkbench —— 标注类页面的通用工作台外壳
    image_canvas     ImageCanvas —— 自绘标注画布（缩放/平移/画框/叠加层）
    sample_strip     SampleStrip —— 底部样本缩略图条
    view_common      标注/检测页共用的视图辅助（来源配色、叠加框构造）

跨工具复用的更底层组件见 ui/common，右侧工作区容器见 ui/parts。
"""
