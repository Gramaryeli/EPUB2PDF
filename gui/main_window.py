# gui/main_window.py
# Version: v3.5.1_UI_Restore
# Last Updated: 2026-01-06
# Description: 修复 UI 布局丢失问题；实现基于密度的静默智能模式切换；日志显示和进度条显示优化

import os
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import psutil
import datetime

from config import APP_VERSION
from utils.logger import CallbackManager
from core.converter import ConverterEngine
from core.merger import PDFMergerEngine
from core.splitter import PDFSplitterEngine


class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"EPUB2PDF {APP_VERSION}")
        self.root.geometry("750x800")

        self.sys_stats = tk.StringVar(value="CPU: 0% | RAM: 0%")
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_convert = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_convert, text=" 📖 EPUB 转 PDF ")
        self._init_convert_tab()

        self.tab_merge = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_merge, text=" 🔗 PDF 工具箱 ")
        self._init_merge_tab()

        self._start_sys_monitor()
        self.current_engine = None
        self.is_running = False

    def _start_sys_monitor(self):
        top_bar = ttk.Frame(self.root, padding=2)
        top_bar.pack(side="top", fill="x", before=self.notebook)
        ttk.Label(top_bar, text="系统状态:", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        ttk.Label(top_bar, textvariable=self.sys_stats, foreground="blue").pack(side="left")

        def update():
            while True:
                try:
                    c = psutil.cpu_percent(interval=1);
                    m = psutil.virtual_memory().percent
                    self.root.after(0, lambda: self.sys_stats.set(f"CPU: {c}% | 内存: {m}%"))
                    import time;
                    time.sleep(1)
                except:
                    break

        t = threading.Thread(target=update, daemon=True);
        t.start()

    # =========================================================================
    # [v3.5.1 修复] UI 布局复原
    # 严格按照 Image_c431e9.png 还原边距、输入框和布局
    # =========================================================================
    def _init_convert_tab(self):
        # 变量初始化
        self.cv_file = tk.StringVar()
        self.cv_paper = tk.StringVar(value="A4")
        self.cv_font = tk.IntVar(value=12)
        self.cv_ml = tk.IntVar(value=25)
        self.cv_mt = tk.IntVar(value=25)
        self.cv_mode = tk.StringVar(value="auto")
        self.cv_auto_merge = tk.BooleanVar(value=True)
        self.cv_prog = tk.DoubleVar()
        self.cv_status = tk.StringVar(value="准备就绪")

        frame = self.tab_convert
        pad = {'padx': 10, 'pady': 5}

        # 区域 1: 输入设置
        g1 = ttk.LabelFrame(frame, text="输入设置", padding=10)
        g1.pack(fill="x", **pad)

        # 文件选择行
        f_row = ttk.Frame(g1)
        f_row.pack(fill="x", pady=(0, 5))
        ttk.Button(f_row, text="选择 EPUB", command=self.cv_sel_file).pack(side="left")
        ttk.Label(f_row, textvariable=self.cv_file, width=55).pack(side="left", padx=10)

        # 模式选择行
        g_mode = ttk.Frame(g1)
        g_mode.pack(fill="x", pady=5)

        m_row1 = ttk.Frame(g_mode)
        m_row1.pack(fill="x", anchor="w")
        ttk.Label(m_row1, text="模式:").pack(side="left")
        ttk.Radiobutton(m_row1, text="智能自动 (推荐)", variable=self.cv_mode, value="auto").pack(side="left", padx=10)
        ttk.Radiobutton(m_row1, text="强制单文件", variable=self.cv_mode, value="single").pack(side="left", padx=10)
        ttk.Radiobutton(m_row1, text="强制分卷", variable=self.cv_mode, value="split").pack(side="left", padx=10)

        # 选项行
        m_row2 = ttk.Frame(g_mode)
        m_row2.pack(fill="x", anchor="w", pady=(5, 0))
        ttk.Label(m_row2, text="选项:").pack(side="left")
        ttk.Checkbutton(m_row2, text="智能/分卷模式下，自动合并为单文件", variable=self.cv_auto_merge).pack(side="left",
                                                                                                           padx=10)

        # 区域 2: 美学设置 (修复：找回丢失的边距设置)
        g2 = ttk.LabelFrame(frame, text="美学设置", padding=10)
        g2.pack(fill="x", **pad)

        # 纸张
        r1 = ttk.Frame(g2)
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="纸张:", width=6).pack(side="left")
        ttk.Combobox(r1, textvariable=self.cv_paper, values=["A4", "A5", "B5"], width=10, state="readonly").pack(
            side="left")

        # 字号
        r2 = ttk.Frame(g2)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="字号:", width=6).pack(side="left")
        ttk.Spinbox(r2, from_=8, to=24, textvariable=self.cv_font, width=6).pack(side="left")

        # 边距
        r3 = ttk.Frame(g2)
        r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="边距:", width=6).pack(side="left")
        ttk.Label(r3, text="左右").pack(side="left")
        ttk.Spinbox(r3, from_=0, to=80, textvariable=self.cv_ml, width=6).pack(side="left", padx=(0, 10))
        ttk.Label(r3, text="上下").pack(side="left")
        ttk.Spinbox(r3, from_=0, to=80, textvariable=self.cv_mt, width=6).pack(side="left")

        # 区域 3: 控制台
        g3 = ttk.LabelFrame(frame, text="控制台", padding=10)
        g3.pack(fill="both", expand=True, **pad)
        ttk.Progressbar(g3, variable=self.cv_prog, maximum=100).pack(fill="x", pady=(0, 5))
        ttk.Label(g3, textvariable=self.cv_status, foreground="green").pack(anchor="w")
        self.cv_log = tk.Text(g3, height=12, font=("Consolas", 9))
        self.cv_log.pack(fill="both", expand=True)

        # 按钮
        self.btn_start = ttk.Button(frame, text="🚀 开始转换", command=self.on_click_start)
        self.btn_start.pack(pady=10, ipadx=20, ipady=5)

    def cv_sel_file(self):
        f = filedialog.askopenfilename(filetypes=[("EPUB", "*.epub")])
        if f: self.cv_file.set(f)

    def cv_log_msg(self, msg):
        self.root.after(0, lambda: self.cv_log.insert("end",
                                                      f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n") or self.cv_log.see(
            "end"))

    # =========================================================================
    # [v3.5.1 新增] 静默智能决策逻辑
    # 逻辑：预检 -> 发现密度高(臃肿) -> 强制切单文件 -> 不弹窗
    # =========================================================================
    def on_click_start(self):
        if self.is_running:
            if messagebox.askyesno("确认", "确定要中止当前任务吗？"):
                self.btn_start.config(state="disabled", text="中止中...")
                if self.current_engine: self.current_engine.stop()
            return

        src = self.cv_file.get()
        if not src: return messagebox.showwarning("提示", "请选择文件")

        # 启动 UI 状态
        self.is_running = True
        self.btn_start.config(state="normal", text="🛑 停止转换")
        self.cv_log.delete(1.0, "end")

        # 线程启动
        threading.Thread(target=self._run_process, args=(src,)).start()

    def _run_process(self, src):
        self.cv_log_msg("正在分析文件结构...")

        # 1. 调用新版密度检测
        is_monolithic, report = ConverterEngine.analyze_structure(src)
        self.cv_log_msg(report)

        # 2. 自动决策 (静默)
        final_mode = self.cv_mode.get()

        # 如果是单体臃肿文件，且用户没选单文件模式 -> 强制覆盖
        if is_monolithic:
            if final_mode != 'single':
                self.cv_log_msg(">>> ⚠️ 策略干预: 检测到结构臃肿(密度高)。")
                self.cv_log_msg(">>> 🤖 自动切换: 【强制单文件】模式 (最优解)。")
                final_mode = 'single'
        else:
            self.cv_log_msg(">>> ✅ 策略保持: 结构健康，按预设模式执行。")

        # 3. 执行
        out = os.path.splitext(src)[0] + ".pdf"
        settings = {
            'paper': self.cv_paper.get(),
            'font_size': self.cv_font.get(),
            'margin_lr': self.cv_ml.get(),
            'margin_tb': self.cv_mt.get(),
            'mode': final_mode,
            'auto_merge': self.cv_auto_merge.get()
        }

        cb = CallbackManager(self.cv_prog, self.cv_status, self.cv_log_msg)
        self.current_engine = ConverterEngine(src, out, settings, cb)
        ok, msg, time_str, path, cleanup = self.current_engine.run()

        self.root.after(0, lambda: self._on_finish(ok, msg, time_str, path, cleanup))

    def _on_finish(self, ok, msg, time_str, final_path, cleanup_target):
        # === [新增/修改区域] ===
        if ok:
            self.cv_log_msg(f"✅ {msg}")  # <--- 1. 补上这句！先把“完成”写入日志
            self.cv_prog.set(100)  # 2. 进度条拉满

        self.root.update()  # 3. 强制刷新（这时候屏幕上就会显示刚才写的日志了）
        # =======================
        self.is_running = False
        self.btn_start.config(state="normal", text="🚀 开始转换")
        self.current_engine = None

        if ok:
            if cleanup_target:
                try:
                    shutil.rmtree(cleanup_target)
                except:
                    pass

            if messagebox.askyesno("完成", f"{msg}\n耗时: {time_str}\n是否打开输出位置？"):
                if final_path:
                    try:
                        os.startfile(os.path.dirname(final_path))
                    except:
                        pass
        else:
            if "中止" in msg:
                self.cv_log_msg("任务已中止")
            else:
                messagebox.showerror("失败", msg)

    # === 工具箱 (保持原样) ===
    def _init_merge_tab(self):
        frame = self.tab_merge;
        pad = {'padx': 10, 'pady': 5}
        paned = tk.PanedWindow(frame, orient="horizontal");
        paned.pack(fill="both", expand=True, **pad)
        left = ttk.LabelFrame(paned, text="批量合并", padding=5);
        paned.add(left, width=320)
        self.mg_list = tk.Listbox(left, selectmode="extended");
        self.mg_list.pack(fill="both", expand=True, pady=5)
        bf = ttk.Frame(left);
        bf.pack(fill="x")
        ttk.Button(bf, text="添加", command=self.mg_add).pack(side="left", fill="x", expand=True)
        ttk.Button(bf, text="删除", command=self.mg_del).pack(side="left", fill="x", expand=True)
        ttk.Button(left, text="开始合并", command=self.mg_start).pack(fill="x", pady=5)
        right = ttk.Frame(paned);
        paned.add(right)
        g_tools = ttk.LabelFrame(right, text="常用工具", padding=10);
        g_tools.pack(fill="x", pady=5)
        self.tl_file = tk.StringVar();
        fr = ttk.Frame(g_tools);
        fr.pack(fill="x", pady=5)
        ttk.Entry(fr, textvariable=self.tl_file).pack(side="left", fill="x", expand=True)
        ttk.Button(fr, text="浏览",
                   command=lambda: self.tl_file.set(filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]))).pack(
            side="left", padx=5)
        ttk.Separator(g_tools, orient="horizontal").pack(fill="x", pady=10)
        ttk.Button(g_tools, text="📊 统计全文字数", command=self.tl_count_words).pack(fill="x", pady=5)
        ttk.Separator(g_tools, orient="horizontal").pack(fill="x", pady=10)
        ttk.Button(g_tools, text="📑 按目录拆分...", command=self.tl_split_toc).pack(fill="x", pady=5)
        self.tl_log = tk.Text(right, height=15, font=("Consolas", 9));
        self.tl_log.pack(fill="both", expand=True, pady=5)
        self.mg_files = []

    def mg_add(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        for f in files: self.mg_files.append(f); self.mg_list.insert("end", os.path.basename(f))

    def mg_del(self):
        for i in reversed(self.mg_list.curselection()): self.mg_list.delete(i); del self.mg_files[i]

    def mg_start(self):
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if out: threading.Thread(target=self.mg_run, args=(out,)).start()

    def mg_run(self, out):
        ok, p = PDFMergerEngine().merge(self.mg_files, out, lambda c, t, m: self.tl_log_msg(f"合并: {m}"))
        self.tl_log_msg(f"完成: {p}" if ok else "失败")

    def tl_count_words(self):
        src = self.tl_file.get();
        if not src: return
        self.tl_log_msg("正在统计...")

        def run():
            ok, p, c = PDFSplitterEngine(CallbackManager(None, None, self.tl_log_msg)).get_pdf_info(src)
            if ok: self.tl_log_msg(f"页数: {p} | 字数: {c}")

        threading.Thread(target=run).start()

    def tl_split_toc(self):
        src = self.tl_file.get();
        if not src: return
        toc = PDFSplitterEngine().get_toc(src)
        if not toc: return messagebox.showinfo("无目录", "无目录")
        top = tk.Toplevel(self.root);
        top.title("导出章节");
        lb = tk.Listbox(top, selectmode="multiple");
        lb.pack(fill="both", expand=True)
        for t, p in toc: lb.insert("end", f"P{p}|{t}")

        def go():
            sel = lb.curselection();
            top.destroy()
            if not sel: return
            tgt = os.path.join(os.path.dirname(src), os.path.splitext(os.path.basename(src))[0] + "_拆分");
            os.makedirs(tgt, exist_ok=True)
            threading.Thread(
                target=lambda: PDFSplitterEngine(CallbackManager(None, None, self.tl_log_msg)).split_by_toc_indices(src,
                                                                                                                    sel,
                                                                                                                    tgt)).start()

        ttk.Button(top, text="导出", command=go).pack()