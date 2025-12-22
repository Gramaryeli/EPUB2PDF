"""
EPUB2PDF Converter Tool
-----------------------
一个基于 Python 的高效 EPUB 转 PDF 工具。
特点：
1. 智能分卷：支持大文件自动拆分与合并。
2. 完美排版：保留原书样式，智能处理注释角标。
3. 目录重构：合并时自动重建层级目录。
4. 图片修复：基于 Manifest 索引解决复杂路径图片丢失问题。

Author: [Gramaryeli]
Version: v3.4.0 (Final Release)
License: MIT
"""

# === 标准库导入 ===
import os
import re
import time
import tempfile
import threading
import datetime
import shutil
import gc

# === 图形界面库 ===
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# === 第三方库 ===
import psutil
from pypdf import PdfWriter, PdfReader
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

# === 全局常量 ===
LARGE_FILE_THRESHOLD_MB = 20
APP_VERSION = "v3.4.0"


# ==========================================
#   核心引擎：EPUB 转 PDF
# ==========================================
class ConverterEngine:
    """
    负责处理 EPUB 解析、HTML清洗、PDF 渲染及分卷逻辑的核心引擎。
    """

    def __init__(self, epub_path, output_path, settings, callback_manager):
        self.epub_path = os.path.abspath(epub_path)
        self.output_path = os.path.abspath(output_path)
        self.settings = settings
        self.cb = callback_manager
        self.stop_flag = False
        self.image_manifest = {}  # 全局图片索引 {filename: abs_path}

    def sanitize_filename(self, name):
        """清洗文件名，移除非法字符"""
        name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
        return name[:50]

    def _get_file_size_mb(self):
        try:
            return os.path.getsize(self.epub_path) / (1024 * 1024)
        except:
            return 0

    def run(self):
        """主执行流程"""
        start_time = time.time()

        file_size = self._get_file_size_mb()
        mode = self.settings.get('mode', 'auto')
        auto_merge = self.settings.get('auto_merge', True)

        # 判定是否为大文件模式
        is_large = False
        if mode == 'split':
            is_large = True
        elif mode == 'single':
            is_large = False
        else:
            is_large = (file_size >= LARGE_FILE_THRESHOLD_MB)

        self.cb.log(f"版本: {APP_VERSION}")
        self.cb.log(f"文件大小: {file_size:.2f} MB")

        result_msg = ""
        success = False
        final_target_path = ""
        cleanup_target = None

        if is_large:
            self.cb.log(f"策略: 智能分卷模式 (>{LARGE_FILE_THRESHOLD_MB}MB)")
            success, split_files, folder_path = self.convert_split_mode()

            # 自动合并逻辑
            if success and auto_merge and split_files:
                self.cb.log("正在执行自动合并...")

                target_dir = os.path.dirname(self.epub_path)
                base_name = os.path.splitext(os.path.basename(self.epub_path))[0]
                merge_output = os.path.join(target_dir, f"{base_name}_全本.pdf")

                merger = PDFMergerEngine()
                merge_success, merge_path = merger.merge(
                    split_files,
                    merge_output,
                    lambda idx, total, msg: self.cb.update_progress(90 + int(idx / total * 10), msg)
                )

                if merge_success:
                    result_msg = f"全本生成成功"
                    cleanup_target = folder_path
                    final_target_path = merge_path
                else:
                    result_msg = f"分卷成功但合并失败: {merge_path}"
                    final_target_path = folder_path
            else:
                result_msg = f"分卷已保存"
                final_target_path = folder_path
                cleanup_target = None
        else:
            self.cb.log("策略: 单文件模式")
            if not self.output_path.lower().endswith('.pdf'):
                self.output_path += ".pdf"

            success, msg = self.convert_single_mode()
            result_msg = msg
            final_target_path = self.output_path

        # 计算耗时
        end_time = time.time()
        duration = end_time - start_time
        m, s = divmod(duration, 60)
        time_str = f"{int(m)}分{int(s)}秒"

        return success, result_msg, time_str, final_target_path, cleanup_target

    def _clean_and_fix_html(self, item, temp_dir):
        """
        HTML 清洗与修正核心：
        1. 修复锚点链接。
        2. 识别并标记注释角标 (class='note-icon')。
        3. 基于 Manifest 修复图片路径。
        4. 移除无效 alt 占位符。
        """
        soup = BeautifulSoup(item.get_content(), 'html.parser')

        # 处理链接与角标
        for a_tag in soup.find_all('a'):
            href = a_tag.get('href')
            if href and '#' in href:
                anchor_id = href.split('#')[-1]
                a_tag['href'] = f"#{anchor_id}"
                # 标记注释图标
                for child_img in a_tag.find_all('img'):
                    classes = child_img.get('class', [])
                    if 'note-icon' not in classes:
                        classes.append('note-icon')
                        child_img['class'] = classes

        # 处理图片与路径
        for img in soup.find_all('img'):
            # 清理 alt
            current_alt = img.get('alt', '')
            if current_alt and current_alt.strip().lower() == 'alt':
                img['alt'] = ""

            # 路径修复
            src = img.get('src')
            if src:
                img_filename = os.path.basename(src)
                # 优先使用 Manifest 索引
                if img_filename in self.image_manifest:
                    abs_path = self.image_manifest[img_filename]
                    img['src'] = f"file:///{abs_path.replace(os.sep, '/')}"
                else:
                    # 兜底查找
                    abs_path = os.path.join(temp_dir, src)
                    if not os.path.exists(abs_path):
                        abs_path = os.path.join(temp_dir, os.path.basename(src))
                    if os.path.exists(abs_path):
                        img['src'] = f"file:///{abs_path.replace(os.sep, '/')}"

        # 移除干扰标签
        for tag in soup.find_all(['script', 'style']):
            tag.decompose()

        body = soup.find('body')
        return body.decode_contents() if body else None

    def _extract_images_and_build_manifest(self, book, temp_dir):
        """解压所有图片并建立 {文件名: 绝对路径} 索引"""
        self.image_manifest = {}
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                img_path = os.path.join(temp_dir, item.get_name())
                os.makedirs(os.path.dirname(img_path), exist_ok=True)
                with open(img_path, 'wb') as f:
                    f.write(item.get_content())
                filename = os.path.basename(item.get_name())
                self.image_manifest[filename] = img_path

    def _get_cover_html(self, book, temp_dir):
        """尝试获取并生成封面 HTML"""
        cover_item = None
        try:
            cover_id = book.get_metadata('OPF', 'cover')
            if cover_id:
                cover_item = book.get_item_with_id(cover_id[0][1])
        except:
            pass

        # 策略1: 查找名为 cover 的图片
        if not cover_item:
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_IMAGE and 'cover' in item.get_name().lower():
                    filename = os.path.basename(item.get_name())
                    if filename in self.image_manifest:
                        src = f"file:///{self.image_manifest[filename].replace(os.sep, '/')}"
                        return f'<div style="text-align:center; page-break-after:always;"><img src="{src}" style="max-height:100%; max-width:100%;" /></div>'

        # 策略2: 使用 metadata 指定的图片
        if cover_item:
            filename = os.path.basename(cover_item.get_name())
            if filename in self.image_manifest:
                src = f"file:///{self.image_manifest[filename].replace(os.sep, '/')}"
                return f'<div style="text-align:center; page-break-after:always;"><img src="{src}" style="max-height:100%; max-width:100%;" /></div>'

        return ""

    def convert_single_mode(self):
        """单文件转换模式"""
        try:
            save_path = self.output_path
            self.cb.update_progress(10, "读取 EPUB...")
            book = epub.read_epub(self.epub_path)

            with tempfile.TemporaryDirectory() as temp_dir:
                self.cb.update_progress(20, "解压资源...")
                self._extract_images_and_build_manifest(book, temp_dir)
                full_html = []
                cover_html = self._get_cover_html(book, temp_dir)
                if cover_html:
                    self.cb.log("已添加封面")
                    full_html.append(cover_html)

                self.cb.update_progress(40, "解析章节...")
                for item_id in book.spine:
                    item = book.get_item_with_id(item_id[0])
                    if item:
                        content = self._clean_and_fix_html(item, temp_dir)
                        if content: full_html.append(content)

                final_html = f"<html><body>{''.join(full_html)}</body></html>"
                font_config = FontConfiguration()
                css = CSS(string=self._generate_css(), font_config=font_config)

                self.cb.update_progress(70, "渲染 PDF...")
                html = HTML(string=final_html, base_url=temp_dir)
                html.write_pdf(save_path, stylesheets=[css], font_config=font_config)

                self.cb.update_progress(100, "完成")
                return True, f"转换成功: {save_path}"

        except Exception as e:
            return False, str(e)

    def convert_split_mode(self):
        """分卷转换模式"""
        try:
            epub_dir = os.path.dirname(self.epub_path)
            folder_name = os.path.splitext(os.path.basename(self.epub_path))[0] + "_分卷"
            target_dir = os.path.join(epub_dir, folder_name)
            if not os.path.exists(target_dir): os.makedirs(target_dir)

            book = epub.read_epub(self.epub_path)
            if not book.toc: return False, [], "无目录，无法分卷"

            generated_files = []

            with tempfile.TemporaryDirectory() as temp_dir:
                self.cb.log("正在解压资源...")
                self._extract_images_and_build_manifest(book, temp_dir)
                font_config = FontConfiguration()
                css = CSS(string=self._generate_css(), font_config=font_config)

                cover_html = self._get_cover_html(book, temp_dir)
                if cover_html:
                    cover_path = os.path.join(target_dir, "00_封面.pdf")
                    c_html = HTML(string=f"<html><body>{cover_html}</body></html>", base_url=temp_dir)
                    c_html.write_pdf(cover_path, stylesheets=[css], font_config=font_config)
                    generated_files.append(cover_path)

                total = len(book.toc)
                start_time = time.time()

                for idx, node in enumerate(book.toc):
                    p = int((idx / total) * 90)
                    elapsed = time.time() - start_time
                    avg = elapsed / (idx + 1) if idx > 0 else 0
                    rem = avg * (total - idx)
                    eta = str(datetime.timedelta(seconds=int(rem)))

                    title = node[0].title if isinstance(node, tuple) else node.title
                    safe_title = self.sanitize_filename(title) or f"分册_{idx + 1}"

                    self.cb.update_progress(p, f"处理: {safe_title} | 剩: {eta}")

                    hrefs = self._find_all_hrefs(node)
                    book_html = []
                    seen = set()

                    for href in hrefs:
                        fname = href.split('#')[0]
                        if fname in seen: continue
                        seen.add(fname)

                        item = book.get_item_with_href(fname)
                        if item:
                            c = self._clean_and_fix_html(item, temp_dir)
                            if c:
                                book_html.append(f'<div style="page-break-before: always;"></div>')
                                book_html.append(c)

                    if book_html:
                        final_html = f"<html><body>{''.join(book_html)}</body></html>"
                        out_name = os.path.join(target_dir, f"{idx + 1:02d}_{safe_title}.pdf")
                        h = HTML(string=final_html, base_url=temp_dir)
                        h.write_pdf(out_name, stylesheets=[css], font_config=font_config)
                        generated_files.append(out_name)
                        del h, final_html, book_html
                        gc.collect()

            self.cb.update_progress(100, "分卷完成")
            return True, generated_files, target_dir

        except Exception as e:
            return False, [], str(e)

    def _find_all_hrefs(self, node):
        hrefs = []
        if isinstance(node, tuple):
            sec, children = node
            if hasattr(sec, 'href'): hrefs.append(sec.href)
            for c in children: hrefs.extend(self._find_all_hrefs(c))
        elif hasattr(node, 'href'):
            hrefs.append(node.href)
        return hrefs

    def _generate_css(self):
        s = self.settings
        return f"""
            @page {{
                size: {s['paper']};
                margin: {s['margin_tb']}mm {s['margin_lr']}mm;
                @bottom-center {{ content: counter(page); font-family: serif; font-size: 10pt; }}
            }}
            body {{
                font-family: "SimSun", "Microsoft YaHei", serif;
                font-size: {s['font_size']}pt;
                line-height: 1.6; text-align: justify;
            }}
            h1, h2, h3 {{ font-family: "Microsoft YaHei", sans-serif; font-weight: bold; page-break-after: avoid; }}
            h1 {{ font-size: 1.6em; text-align: center; margin: 1.5em 0 1em 0; }}
            img {{ max-width: 100%; height: auto; display: block; margin: 1em auto; }}
            img.note-icon {{
                max-width: 1em; max-height: 1em; display: inline;
                vertical-align: super; margin: 0 1px; border: none;
            }}
            a {{ text-decoration: none; color: inherit; }}
        """


# ==========================================
#   工具：PDF 合并引擎
# ==========================================
class PDFMergerEngine:
    """
    负责 PDF 文件合并，并支持一级目录（文件名）重构。
    """

    def merge(self, file_list, output_path, update_callback):
        try:
            writer = PdfWriter()
            total_files = len(file_list)

            for idx, pdf_path in enumerate(file_list):
                file_name = os.path.basename(pdf_path)
                book_title = os.path.splitext(file_name)[0]
                # 去除自动分卷产生的 "01_" 序号，使目录更干净
                clean_title = re.sub(r'^\d+_', '', book_title)

                if update_callback:
                    update_callback(idx, total_files, f"合并中: {clean_title}")

                reader = PdfReader(pdf_path)
                page_offset = len(writer.pages)
                writer.append_pages_from_reader(reader)

                # 添加父级目录
                parent_bookmark = writer.add_outline_item(title=clean_title, page_number=page_offset)
                # 递归复制子目录
                self._copy_outlines(writer, reader.outline, parent_bookmark, reader, page_offset)

            if update_callback:
                update_callback(total_files, total_files, "保存合并文件...")

            output_path = os.path.abspath(output_path)
            writer.write(output_path)
            writer.close()
            return True, output_path

        except Exception as e:
            return False, str(e)

    def _copy_outlines(self, writer, outlines, parent, reader, page_offset):
        """递归复制目录结构"""
        if not outlines: return
        last_added_item = None
        for item in outlines:
            if isinstance(item, list):
                if last_added_item:
                    self._copy_outlines(writer, item, last_added_item, reader, page_offset)
            else:
                try:
                    page_index = reader.get_destination_page_number(item)
                    if page_index is not None:
                        last_added_item = writer.add_outline_item(
                            title=item.title,
                            page_number=page_index + page_offset,
                            parent=parent
                        )
                except:
                    continue


# ==========================================
#   辅助：回调管理器
# ==========================================
class CallbackManager:
    def __init__(self, p_var, s_var, l_func):
        self.p = p_var
        self.s = s_var
        self.l = l_func

    def update_progress(self, val, msg):
        self.p.set(val)
        self.s.set(msg)

    def log(self, msg): self.l(msg)


# ==========================================
#   GUI 主界面
# ==========================================
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