"""AI QQ Friends entry point (tkinter GUI)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aafm_qq.gui import run  # noqa: E402

if __name__ == '__main__':
    run()
