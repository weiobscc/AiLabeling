"""AI 标注训练软件 —— 程序入口。

运行：
    python main.py
"""
import sys
import traceback

from PyQt6.QtWidgets import QApplication

from ui.main.main_window import MainWindow

# 模块级引用：防止 QApplication / 主窗口被垃圾回收导致窗口一闪而过
_app: QApplication | None = None
_window: MainWindow | None = None


def main() -> int:
    global _app, _window

    _app = QApplication(sys.argv)
    _app.setApplicationName("AI 标注训练软件")
    _app.setStyle("Fusion")

    _window = MainWindow()
    _window.show()
    return _app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # 启动或运行期间发生异常时，打印完整堆栈而非静默退出
        traceback.print_exc()
        try:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(None, "程序异常", f"{exc}\n\n详情见命令行输出。")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
