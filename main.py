# main.py
import tkinter as tk
from gui.main_window import AppGUI

if __name__ == "__main__":
    root = tk.Tk()
    # 尝试开启高DPI支持 (Windows)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    AppGUI(root)
    root.mainloop()