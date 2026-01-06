# gui/main_window.py
# Version: v3.7.1_Feedback_Fix
# Last Updated: 2026-01-06
# Description: [v3.7.1] 修复分割任务的控制台反馈，确保任务结束有明确提示。

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
        self.root.title(f"EPUB2PDF {APP_VERSION} (Pro)")
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
        self.batch_file_paths = []
        self.is_counting = False  # 统计锁

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
    # Tab 1: EPUB 转 PDF (保持 v3.6.1 代码)
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

        self.btn_start = ttk.Button(frame, text="🚀 开始转换", command=self.on_click_start)
        self.btn_start.pack(pady=10, ipadx=20, ipady=5)

    # --- Tab 1 逻辑 ---
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

            self.root.after(0,
                            lambda s=f"[进度 {current_idx}/{total_files}] 正在处理: {filename}": self.cv_status.set(s))
            self.cv_log_msg(f"\n--------- 处理第 {current_idx} / {total_files} 本: {filename} ---------")

            try:
                is_monolithic, report = ConverterEngine.analyze_structure(src)
                self.cv_log_msg(report.split('\n')[-2])

                final_mode = self.cv_mode.get()
                if is_monolithic and final_mode != 'single':
                    self.cv_log_msg(">>> ⚠️ 自动切换为【强制单文件】模式")
                    final_mode = 'single'

                out = os.path.splitext(src)[0] + ".pdf"
                settings = {'paper': self.cv_paper.get(), 'font_size': self.cv_font.get(),
                            'margin_lr': self.cv_ml.get(), 'margin_tb': self.cv_mt.get(), 'mode': final_mode,
                            'auto_merge': self.cv_auto_merge.get()}

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

        summary = f"批量任务完成\n\n共处理: {total}\n✅ 成功: {success}\n❌ 失败: {fail}"
        self.cv_log_msg("=" * 30)
        self.cv_log_msg(summary.replace("\n", " | "))

        messagebox.showinfo("汇报", summary)

    # =========================================================================
    # Tab 2: PDF 工具箱
    # =========================================================================
    def _init_merge_tab(self):
        self.mg_files = []
        self.tl_file = tk.StringVar()
        self.tl_mode = tk.StringVar(value="toc")
        self.tl_word_limit = tk.DoubleVar(value=2.0)

        frame = self.tab_merge
        pad = {'padx': 10, 'pady': 5}

        # 区块 A: PDF 合并
        group_merge = ttk.LabelFrame(frame, text="🏭 PDF 合并工厂", padding=10)
        group_merge.pack(fill="both", expand=True, **pad)

        list_frame = ttk.Frame(group_merge)
        list_frame.pack(fill="both", expand=True)
        sb_merge = ttk.Scrollbar(list_frame)
        sb_merge.pack(side="right", fill="y")
        self.mg_list = tk.Listbox(list_frame, selectmode="extended", height=8, yscrollcommand=sb_merge.set,
                                  font=("Consolas", 9))
        self.mg_list.pack(side="left", fill="both", expand=True)
        sb_merge.config(command=self.mg_list.yview)

        tb_merge = ttk.Frame(group_merge)
        tb_merge.pack(fill="x", pady=5)
        ttk.Button(tb_merge, text="➕ 添加文件", command=self.mg_add).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(tb_merge, text="➖ 删除选中", command=self.mg_del).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Separator(tb_merge, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Button(tb_merge, text="⬆️ 上移", command=self.mg_up).pack(side="left", padx=2)
        ttk.Button(tb_merge, text="⬇️ 下移", command=self.mg_down).pack(side="left", padx=2)

        ttk.Button(group_merge, text="🔗 开始合并为单文件", command=self.mg_start).pack(fill="x", pady=(5, 0))

        # 区块 B: 智能分割
        group_split = ttk.LabelFrame(frame, text="✂️ 智能分割与统计", padding=10)
        group_split.pack(fill="x", **pad)

        row_src = ttk.Frame(group_split)
        row_src.pack(fill="x", pady=5)
        ttk.Label(row_src, text="源文件:").pack(side="left")
        ttk.Entry(row_src, textvariable=self.tl_file).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row_src, text="📂 浏览",
                   command=lambda: self.tl_file.set(filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")]))).pack(
            side="left")

        row_panel = ttk.Frame(group_split)
        row_panel.pack(fill="x", pady=10)

        f_stat = ttk.Labelframe(row_panel, text="基础信息", padding=5)
        f_stat.pack(side="left", fill="both", expand=True, padx=(0, 5))
        ttk.Button(f_stat, text="📊 统计页数与字数", command=self.tl_count_words).pack(fill="x", pady=5)

        f_strat = ttk.Labelframe(row_panel, text="分割策略", padding=5)
        f_strat.pack(side="right", fill="both", expand=True, padx=(5, 0))

        r_toc = ttk.Radiobutton(f_strat, text="按目录章节分割 (推荐)", variable=self.tl_mode, value="toc",
                                command=self._update_ui_state)
        r_toc.pack(anchor="w", pady=2)

        f_word = ttk.Frame(f_strat)
        f_word.pack(anchor="w", pady=2)
        r_word = ttk.Radiobutton(f_word, text="按字数分割 | 每", variable=self.tl_mode, value="word",
                                 command=self._update_ui_state)
        r_word.pack(side="left")
        self.ent_limit = ttk.Spinbox(f_word, from_=0.1, to=50.0, increment=0.5, textvariable=self.tl_word_limit,
                                     width=5)
        self.ent_limit.pack(side="left", padx=2)
        ttk.Label(f_word, text="万字").pack(side="left")

        ttk.Button(group_split, text="🚀 执行分割", command=self.tl_run_split).pack(fill="x", pady=5)

        self.tl_log = tk.Text(group_split, height=6, font=("Consolas", 8), fg="#333")
        self.tl_log.pack(fill="x", pady=5)

    def _update_ui_state(self):
        if self.tl_mode.get() == "word":
            self.ent_limit.config(state="normal")
        else:
            self.ent_limit.config(state="disabled")

    def tl_log_msg(self, msg):
        self.root.after(0, lambda: self.tl_log.insert("end",
                                                      f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n") or self.tl_log.see(
            "end"))

    # --- Tab 2 逻辑 ---
    def mg_add(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        for f in files: self.mg_files.append(f); self.mg_list.insert("end", os.path.basename(f))

    def mg_del(self):
        sel = list(self.mg_list.curselection());
        sel.sort(reverse=True)
        for i in sel: self.mg_list.delete(i); del self.mg_files[i]

    def mg_up(self):
        sel = self.mg_list.curselection()
        if not sel: return
        for i in sel:
            if i == 0: continue
            text = self.mg_list.get(i);
            file = self.mg_files[i]
            self.mg_list.delete(i);
            self.mg_files.pop(i)
            self.mg_list.insert(i - 1, text);
            self.mg_files.insert(i - 1, file)
            self.mg_list.selection_set(i - 1)

    def mg_down(self):
        sel = list(self.mg_list.curselection());
        sel.sort(reverse=True)
        if not sel: return
        for i in sel:
            if i == len(self.mg_files) - 1: continue
            text = self.mg_list.get(i);
            file = self.mg_files[i]
            self.mg_list.delete(i);
            self.mg_files.pop(i)
            self.mg_list.insert(i + 1, text);
            self.mg_files.insert(i + 1, file)
            self.mg_list.selection_set(i + 1)

    def mg_start(self):
        if len(self.mg_files) < 2: return messagebox.showwarning("提示", "请至少添加 2 个文件")
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if out:
            self.tl_log_msg("正在合并...")
            threading.Thread(target=self.mg_run, args=(out,)).start()

    def mg_run(self, out):
        eng = PDFMergerEngine()
        ok, path = eng.merge(self.mg_files, out, lambda c, t, m: self.tl_log_msg(f"合并: {m}"))
        self.tl_log_msg(f"✅ 合并完成: {os.path.basename(path)}" if ok else "❌ 失败")

    def tl_count_words(self):
        if self.is_counting: return  # 防双击
        src = self.tl_file.get()
        if not src: return messagebox.showwarning("提示", "请选择源文件")

        self.is_counting = True
        self.tl_log_msg("正在分析全文字数...")

        def run():
            try:
                cb = CallbackManager(None, None, self.tl_log_msg)
                ok, p, c = PDFSplitterEngine(cb).get_pdf_info(src)
                if ok:
                    self.tl_log_msg(f"📊 统计报告: 共 {p} 页 | 约 {c} 字符")
                else:
                    self.tl_log_msg(f"❌ 统计失败: {c}")
            finally:
                self.is_counting = False

        threading.Thread(target=run).start()

    def tl_run_split(self):
        src = self.tl_file.get()
        if not src: return messagebox.showwarning("提示", "请选择源文件")

        mode = self.tl_mode.get()

        if mode == "toc":
            toc = PDFSplitterEngine().get_toc(src)
            if not toc: return messagebox.showinfo("无目录", "该 PDF 没有目录信息。")

            top = tk.Toplevel(self.root);
            top.title("选择导出章节")
            top.geometry("400x500")

            lb = tk.Listbox(top, selectmode="multiple", font=("Consolas", 9))
            lb.pack(fill="both", expand=True, padx=5, pady=5)
            for t, p in toc: lb.insert("end", f"P{p} | {t}")

            def confirm():
                sel = lb.curselection();
                top.destroy()
                if not sel: return
                tgt = os.path.join(os.path.dirname(src), os.path.splitext(os.path.basename(src))[0] + "_章节拆分")
                os.makedirs(tgt, exist_ok=True)

                self.tl_log_msg(f"正在准备按选定切割点分卷...")
                # 使用线程包装器来处理结束反馈
                threading.Thread(target=lambda: self._run_split_toc(src, sel, tgt)).start()

            ttk.Button(top, text="确认分割点", command=confirm).pack(pady=10)

        elif mode == "word":
            try:
                limit_w = float(self.tl_word_limit.get())
                if limit_w <= 0: raise ValueError
            except:
                return messagebox.showerror("错误", "请输入有效的字数阈值")

            threshold = int(limit_w * 10000)
            tgt = os.path.join(os.path.dirname(src),
                               os.path.splitext(os.path.basename(src))[0] + f"_字数拆分_{limit_w}w")
            os.makedirs(tgt, exist_ok=True)

            self.tl_log_msg(f"正在执行字数分割 (阈值: {threshold}字)...")
            threading.Thread(target=lambda: self._run_split_word(src, threshold, tgt)).start()

    # [v3.7.1] 新增的线程包装函数，用于输出结束日志
    def _run_split_toc(self, src, sel, tgt):
        cb = CallbackManager(None, None, self.tl_log_msg)
        ok, msg = PDFSplitterEngine(cb).split_by_toc_indices(src, sel, tgt)
        self.tl_log_msg(f">>> {msg}")  # 输出总结

    def _run_split_word(self, src, threshold, tgt):
        cb = CallbackManager(None, None, self.tl_log_msg)
        ok, msg = PDFSplitterEngine(cb).split_by_word_count(src, threshold, tgt)
        self.tl_log_msg(f">>> {msg}")  # 输出总结