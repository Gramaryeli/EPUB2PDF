# gui/main_window.py
import os
import threading
import datetime
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import psutil

# 导入模块
from config import APP_VERSION
from utils.logger import CallbackManager
from core.converter import ConverterEngine
from core.merger import PDFMergerEngine

class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"EPUB2PDF {APP_VERSION}")
        self.root.geometry("700x750")

        self.sys_stats = tk.StringVar(value="CPU: 0% | RAM: 0%")
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_convert = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_convert, text=" 📖 EPUB 转 PDF ")
        self._init_convert_tab()

        self.tab_merge = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_merge, text=" 🔗 PDF 合并工具 ")
        self._init_merge_tab()

        self._start_sys_monitor()

    def _start_sys_monitor(self):
        top_bar = ttk.Frame(self.root, padding=2)
        top_bar.pack(side="top", fill="x", before=self.notebook)
        ttk.Label(top_bar, text="系统状态:", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        ttk.Label(top_bar, textvariable=self.sys_stats, foreground="blue").pack(side="left")

        def update():
            while True:
                try:
                    c = psutil.cpu_percent(interval=1)
                    m = psutil.virtual_memory().percent
                    self.root.after(0, lambda: self.sys_stats.set(f"CPU: {c}% | 内存: {m}%"))
                except:
                    break

        t = threading.Thread(target=update, daemon=True)
        t.start()

    def _init_convert_tab(self):
        self.cv_file = tk.StringVar()
        self.cv_paper = tk.StringVar(value="A4")
        self.cv_font = tk.IntVar(value=12)
        self.cv_ml = tk.IntVar(value=25)
        self.cv_mt = tk.IntVar(value=25)
        self.cv_mode = tk.StringVar(value="auto")
        self.cv_auto_merge = tk.BooleanVar(value=True)  # 默认开启
        self.cv_prog = tk.DoubleVar()
        self.cv_status = tk.StringVar(value="准备就绪")

        frame = self.tab_convert
        pad = {'padx': 10, 'pady': 5}

        # 1. 输入设置
        g1 = ttk.LabelFrame(frame, text="输入设置", padding=10)
        g1.pack(fill="x", **pad)

        f_row = ttk.Frame(g1)
        f_row.pack(fill="x")
        ttk.Button(f_row, text="选择 EPUB", command=self.cv_sel_file).pack(side="left")
        ttk.Label(f_row, textvariable=self.cv_file, width=50).pack(side="left", padx=5)

        # 2. 模式与选项
        g_mode = ttk.Frame(g1)
        g_mode.pack(fill="x", pady=10, side="bottom")

        # 第一行：模式单选
        m_row1 = ttk.Frame(g_mode)
        m_row1.pack(fill="x", anchor="w")
        ttk.Label(m_row1, text="模式:").pack(side="left")
        ttk.Radiobutton(m_row1, text="智能自动 (推荐)", variable=self.cv_mode, value="auto").pack(side="left", padx=5)
        ttk.Radiobutton(m_row1, text="强制单文件", variable=self.cv_mode, value="single").pack(side="left", padx=5)
        ttk.Radiobutton(m_row1, text="强制分卷", variable=self.cv_mode, value="split").pack(side="left", padx=5)

        # 第二行：合并复选框
        m_row2 = ttk.Frame(g_mode)
        m_row2.pack(fill="x", anchor="w", pady=(5, 0))
        ttk.Label(m_row2, text="选项:").pack(side="left")
        ttk.Checkbutton(m_row2, text="智能/分卷模式下，自动合并为单文件", variable=self.cv_auto_merge).pack(side="left",
                                                                                                           padx=5)

        # 3. 排版设置
        g2 = ttk.LabelFrame(frame, text="美学设置", padding=10)
        g2.pack(fill="x", **pad)

        r1 = ttk.Frame(g2);
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="纸张:", width=8).pack(side="left")
        ttk.Combobox(r1, textvariable=self.cv_paper, values=["A4", "A5", "B5"], width=8, state="readonly").pack(
            side="left")
        r2 = ttk.Frame(g2);
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="字号:", width=8).pack(side="left")
        ttk.Spinbox(r2, from_=8, to=24, textvariable=self.cv_font, width=5).pack(side="left")
        r3 = ttk.Frame(g2);
        r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="边距:", width=8).pack(side="left")
        ttk.Label(r3, text="左右").pack(side="left");
        ttk.Spinbox(r3, from_=0, to=80, textvariable=self.cv_ml, width=5).pack(side="left")
        ttk.Label(r3, text="上下").pack(side="left");
        ttk.Spinbox(r3, from_=0, to=80, textvariable=self.cv_mt, width=5).pack(side="left")

        # 4. 控制台
        g3 = ttk.LabelFrame(frame, text="控制台", padding=10)
        g3.pack(fill="both", expand=True, **pad)
        ttk.Progressbar(g3, variable=self.cv_prog, maximum=100).pack(fill="x")
        ttk.Label(g3, textvariable=self.cv_status, foreground="green").pack(anchor="w")
        self.cv_log = tk.Text(g3, height=8, font=("Consolas", 9))
        self.cv_log.pack(fill="both", expand=True)

        ttk.Button(frame, text="🚀 开始转换", command=self.cv_start).pack(pady=10, ipadx=20, ipady=5)

    def cv_sel_file(self):
        f = filedialog.askopenfilename(filetypes=[("EPUB", "*.epub")])
        if f: self.cv_file.set(f)

    def cv_log_msg(self, msg):
        self.root.after(0, lambda: self.cv_log.insert("end",
                                                      f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n") or self.cv_log.see(
            "end"))

    def cv_start(self):
        src = self.cv_file.get()
        if not src: return messagebox.showwarning("错", "请选文件")

        base_dir = os.path.dirname(os.path.abspath(src))
        name = os.path.splitext(os.path.basename(src))[0]
        out = os.path.join(base_dir, f"{name}.pdf")

        settings = {
            'paper': self.cv_paper.get(),
            'font_size': self.cv_font.get(),
            'margin_lr': self.cv_ml.get(),
            'margin_tb': self.cv_mt.get(),
            'mode': self.cv_mode.get(),
            'auto_merge': self.cv_auto_merge.get()
        }

        self.cv_log.delete(1.0, "end")
        t = threading.Thread(target=self.cv_run, args=(src, out, settings))
        t.start()

    def cv_run(self, src, out, settings):
        cb = CallbackManager(self.cv_prog, self.cv_status, self.cv_log_msg)
        eng = ConverterEngine(src, out, settings, cb)
        # 获取 cleanup_target
        ok, result_msg, time_str, final_path, cleanup_target = eng.run()

        self.root.after(0, lambda: self._handle_finish(ok, result_msg, time_str, final_path, cleanup_target))

    def _handle_finish(self, ok, msg, time_str, final_path, cleanup_target):
        if ok:
            # 1. 优先询问清理 (如果需要)
            if cleanup_target and os.path.exists(cleanup_target):
                confirm_clean = messagebox.askyesno(
                    "空间优化",
                    f"转换及合并已完成。\n\n检测到中间生成的【分卷文件夹】占用了空间。\n是否立即删除分卷文件夹？\n(全本 PDF 已安全保存)"
                )
                if confirm_clean:
                    try:
                        shutil.rmtree(cleanup_target)
                        self.cv_log_msg("分卷文件夹已清理")
                    except Exception as e:
                        messagebox.showerror("清理失败", str(e))

            # 2. 提示完成
            info_text = f"{msg}\n\n总耗时: {time_str}\n\n是否打开输出位置？"
            if messagebox.askyesno("任务完成", info_text):
                if final_path and os.path.exists(final_path):
                    # 确保打开的是目录
                    target_dir = final_path if os.path.isdir(final_path) else os.path.dirname(final_path)
                    try:
                        os.startfile(target_dir)
                    except Exception as e:
                        messagebox.showerror("错误", f"无法打开文件夹: {e}")
                else:
                    messagebox.showwarning("警告", "找不到输出路径，可能已被移动或删除")
        else:
            messagebox.showerror("失败", f"错误详情: {msg}")

    # ==========================
    #   Tab 2: 合并功能
    # ==========================
    def _init_merge_tab(self):
        frame = self.tab_merge
        pad = {'padx': 10, 'pady': 5}
        self.mg_list = tk.Listbox(frame, selectmode="extended", height=15)
        self.mg_list.pack(fill="both", expand=True, **pad)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", **pad)
        ttk.Button(btn_frame, text="添加 PDF", command=self.mg_add).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="清空", command=lambda: self.mg_list.delete(0, "end")).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="删除选中", command=self.mg_del).pack(side="left", padx=5)

        self.mg_status = tk.StringVar(value="请添加文件...")
        ttk.Label(frame, textvariable=self.mg_status, relief="sunken").pack(fill="x", **pad)
        ttk.Button(frame, text="🔗 合并为新 PDF", command=self.mg_start).pack(pady=10, ipadx=20, ipady=5)
        self.mg_files = []

    def mg_add(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        for f in files:
            self.mg_files.append(f)
            self.mg_list.insert("end", os.path.basename(f))

    def mg_del(self):
        sel = self.mg_list.curselection()
        for i in reversed(sel):
            self.mg_list.delete(i)
            del self.mg_files[i]

    def mg_start(self):
        if not self.mg_files: return messagebox.showwarning("空", "请至少添加两个文件")
        save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not save_path: return
        t = threading.Thread(target=self.mg_run, args=(save_path,))
        t.start()

    def mg_run(self, out):
        eng = PDFMergerEngine()

        def cb(curr, total, msg): self.mg_status.set(f"({curr}/{total}) {msg}")

        ok, path = eng.merge(self.mg_files, out, cb)
        self.root.after(0, lambda: self._handle_finish(ok, f"手动合并完成: {path}", "N/A", path, None))