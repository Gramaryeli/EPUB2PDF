# gui/main_window.py
# Version: v3.6.1_Batch_Final
# Last Updated: 2026-01-06
# Description: 批量转换完整版；集成Listbox队列；极简结果汇报；UI布局修复。

import os
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import psutil
import datetime
import glob

from config import APP_VERSION
from utils.logger import CallbackManager
from core.converter import ConverterEngine
from core.merger import PDFMergerEngine
from core.splitter import PDFSplitterEngine


class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"EPUB2PDF {APP_VERSION} (批量增强版)")
        self.root.geometry("800x850")

        self.sys_stats = tk.StringVar(value="CPU: 0% | RAM: 0%")
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_convert = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_convert, text=" 📖 EPUB 转 PDF (批量) ")
        self._init_convert_tab()

        self.tab_merge = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_merge, text=" 🔗 PDF 工具箱 ")
        self._init_merge_tab()

        self._start_sys_monitor()
        self.current_engine = None
        self.is_running = False
        self.batch_file_paths = []  # 批量队列

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
                    import time;
                    time.sleep(1)
                except:
                    break

        t = threading.Thread(target=update, daemon=True);
        t.start()

    # =========================================================================
    # [UI] 批量转换界面 (Listbox + 按钮组)
    # =========================================================================
    def _init_convert_tab(self):
        self.cv_paper = tk.StringVar(value="A4")
        self.cv_font = tk.IntVar(value=12)
        self.cv_ml = tk.IntVar(value=25);
        self.cv_mt = tk.IntVar(value=25)
        self.cv_mode = tk.StringVar(value="auto")
        self.cv_auto_merge = tk.BooleanVar(value=True)
        self.cv_prog = tk.DoubleVar()
        self.cv_status = tk.StringVar(value="准备就绪")

        frame = self.tab_convert
        pad = {'padx': 10, 'pady': 5}

        # 区域 1: 批量文件队列
        g1 = ttk.LabelFrame(frame, text="待处理文件队列", padding=10)
        g1.pack(fill="x", **pad)

        btn_bar = ttk.Frame(g1)
        btn_bar.pack(fill="x", pady=(0, 5))
        ttk.Button(btn_bar, text="➕ 添加文件", command=self.cv_add_files).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="📂 添加文件夹", command=self.cv_add_folder).pack(side="left", padx=2)
        ttk.Frame(btn_bar, width=20).pack(side="left")
        ttk.Button(btn_bar, text="➖ 移除选中", command=self.cv_remove_sel).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="🗑️ 清空列表", command=self.cv_clear_list).pack(side="left", padx=2)

        list_frame = ttk.Frame(g1);
        list_frame.pack(fill="x", expand=True)
        scrollbar = ttk.Scrollbar(list_frame);
        scrollbar.pack(side="right", fill="y")
        self.cv_listbox = tk.Listbox(list_frame, height=5, selectmode="extended", yscrollcommand=scrollbar.set,
                                     font=("Consolas", 9))
        self.cv_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.cv_listbox.yview)

        # 区域 2: 转换策略
        g_mode = ttk.LabelFrame(frame, text="转换策略", padding=10)
        g_mode.pack(fill="x", **pad)
        m_row1 = ttk.Frame(g_mode);
        m_row1.pack(fill="x", anchor="w")
        ttk.Label(m_row1, text="模式优先:").pack(side="left")
        ttk.Radiobutton(m_row1, text="智能自动 (推荐)", variable=self.cv_mode, value="auto").pack(side="left", padx=10)
        ttk.Radiobutton(m_row1, text="强制单文件", variable=self.cv_mode, value="single").pack(side="left", padx=10)
        ttk.Radiobutton(m_row1, text="强制分卷", variable=self.cv_mode, value="split").pack(side="left", padx=10)
        ttk.Checkbutton(m_row1, text="分卷后自动合并", variable=self.cv_auto_merge).pack(side="right", padx=10)

        # 区域 3: 美学设置
        g2 = ttk.LabelFrame(frame, text="美学设置", padding=10)
        g2.pack(fill="x", **pad)
        r1 = ttk.Frame(g2);
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="纸张:").pack(side="left")
        ttk.Combobox(r1, textvariable=self.cv_paper, values=["A4", "A5", "B5"], width=5, state="readonly").pack(
            side="left", padx=5)
        ttk.Label(r1, text="字号:").pack(side="left", padx=(15, 0))
        ttk.Spinbox(r1, from_=8, to=24, textvariable=self.cv_font, width=5).pack(side="left", padx=5)
        ttk.Label(r1, text="边距(左右/上下):").pack(side="left", padx=(15, 0))
        ttk.Spinbox(r1, from_=0, to=80, textvariable=self.cv_ml, width=5).pack(side="left")
        ttk.Spinbox(r1, from_=0, to=80, textvariable=self.cv_mt, width=5).pack(side="left", padx=5)

        # 区域 4: 控制台
        g3 = ttk.LabelFrame(frame, text="控制台", padding=10)
        g3.pack(fill="both", expand=True, **pad)
        ttk.Progressbar(g3, variable=self.cv_prog, maximum=100).pack(fill="x", pady=(0, 5))
        ttk.Label(g3, textvariable=self.cv_status, foreground="blue").pack(anchor="w")
        self.cv_log = tk.Text(g3, height=12, font=("Consolas", 9));
        self.cv_log.pack(fill="both", expand=True)

        self.btn_start = ttk.Button(frame, text="🚀 开始批量转换", command=self.on_click_start)
        self.btn_start.pack(pady=10, ipadx=20, ipady=5)

    # --- 队列操作 ---
    def cv_add_files(self):
        files = filedialog.askopenfilenames(filetypes=[("EPUB", "*.epub")])
        for f in files:
            if f not in self.batch_file_paths:
                self.batch_file_paths.append(f);
                self.cv_listbox.insert("end", f)

    def cv_add_folder(self):
        d = filedialog.askdirectory()
        if d:
            found = glob.glob(os.path.join(d, "*.epub"))
            count = 0
            for f in found:
                f_abs = os.path.abspath(f)
                if f_abs not in self.batch_file_paths:
                    self.batch_file_paths.append(f_abs);
                    self.cv_listbox.insert("end", f_abs);
                    count += 1
            messagebox.showinfo("添加成功", f"已从文件夹添加 {count} 个文件")

    def cv_remove_sel(self):
        for i in reversed(self.cv_listbox.curselection()): self.cv_listbox.delete(i); del self.batch_file_paths[i]

    def cv_clear_list(self):
        self.cv_listbox.delete(0, "end");
        self.batch_file_paths = []

    def cv_log_msg(self, msg):
        self.root.after(0, lambda: self.cv_log.insert("end",
                                                      f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n") or self.cv_log.see(
            "end"))

    # =========================================================================
    # [核心] 批量调度逻辑 (含容错与状态隔离)
    # =========================================================================
    def on_click_start(self):
        if self.is_running:
            if messagebox.askyesno("确认", "确定要中止所有任务吗？"):
                self.btn_start.config(state="disabled", text="中止中...")
                self.is_running = False
                if self.current_engine: self.current_engine.stop()
            return

        if not self.batch_file_paths: return messagebox.showwarning("提示", "队列为空")

        self.is_running = True
        self.btn_start.config(state="normal", text="🛑 停止所有任务")
        self.cv_log.delete(1.0, "end")
        threading.Thread(target=self._run_batch_process).start()

    def _run_batch_process(self):
        total_files = len(self.batch_file_paths)
        success_count = 0
        fail_count = 0

        self.cv_log_msg(f"=== 开始批量任务，共 {total_files} 个文件 ===")

        for idx, src in enumerate(self.batch_file_paths):
            if not self.is_running:
                self.cv_log_msg(">>> 🚫 用户中止任务。");
                break

            filename = os.path.basename(src)
            current_idx = idx + 1

            # 更新总状态 (引擎不覆盖此状态)
            self.root.after(0,
                            lambda s=f"[进度 {current_idx}/{total_files}] 正在处理: {filename}": self.cv_status.set(s))
            self.cv_log_msg(f"\n--------- 处理第 {current_idx} / {total_files} 本: {filename} ---------")

            try:
                is_monolithic, report = ConverterEngine.analyze_structure(src)
                self.cv_log_msg(report.split('\n')[-2])  # 简略日志

                final_mode = self.cv_mode.get()
                if is_monolithic and final_mode != 'single':
                    self.cv_log_msg(">>> ⚠️ 自动切换为【强制单文件】模式")
                    final_mode = 'single'

                out = os.path.splitext(src)[0] + ".pdf"
                settings = {'paper': self.cv_paper.get(), 'font_size': self.cv_font.get(),
                            'margin_lr': self.cv_ml.get(), 'margin_tb': self.cv_mt.get(), 'mode': final_mode,
                            'auto_merge': self.cv_auto_merge.get()}

                # 传入 None 给 status_cb，防止引擎覆盖总进度
                cb = CallbackManager(self.cv_prog, None, self.cv_log_msg)
                self.current_engine = ConverterEngine(src, out, settings, cb)

                ok, msg, time_str, path, cleanup = self.current_engine.run()

                if ok:
                    success_count += 1
                    self.cv_log_msg(f"✅ [成功] {filename}")
                    if cleanup and os.path.exists(cleanup):
                        try:
                            shutil.rmtree(cleanup)
                        except:
                            pass
                else:
                    if "中止" in msg:
                        self.cv_log_msg(f"🚫 [中止] {filename}"); break
                    else:
                        fail_count += 1
                        self.cv_log_msg(f"❌ [失败] {filename}: {msg}")
                        self.cv_log_msg(">>> 跳过此文件，继续下一本...")

            except Exception as e:
                fail_count += 1
                self.cv_log_msg(f"❌ [异常] {filename}: {str(e)}")

            finally:
                self.current_engine = None

        self.root.after(0, lambda: self._on_batch_finish(success_count, fail_count, total_files))

    def _on_batch_finish(self, success, fail, total):
        self.cv_prog.set(100)
        self.root.update()

        self.is_running = False
        self.btn_start.config(state="normal", text="🚀 开始批量转换")
        self.cv_status.set("批量任务结束")

        # 极简弹窗
        summary = f"批量任务完成\n\n共处理: {total}\n✅ 成功: {success}\n❌ 失败: {fail}"
        self.cv_log_msg("=" * 30)
        self.cv_log_msg(summary.replace("\n", " | "))

        messagebox.showinfo("汇报", summary)

    # === 工具箱 (保持原样) ===
    def _init_merge_tab(self):
        # 此处代码与之前完全一致，为节省篇幅，请保持您原有的工具箱代码
        # 只要确保 PDF 工具箱功能 (统计/拆分/合并) 存在即可
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

    # 工具箱辅助方法 (保持原样)
    def mg_add(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        for f in files: self.mg_files.append(f); self.mg_list.insert("end", os.path.basename(f))

    def mg_del(self):
        for i in reversed(self.mg_list.curselection()): self.mg_list.delete(i); del self.mg_files[i]

    def mg_start(self):
        if not self.mg_files: return messagebox.showwarning("空", "最少2个文件")
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