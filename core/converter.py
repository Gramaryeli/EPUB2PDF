# core/converter.py
# Version: v3.6.1_Final_Lite
# Last Updated: 2026-01-06
# Description: 移除所有冗余的ETA时间计算代码；保留密度检测；仅专注于转换核心逻辑。

import os
import time
import tempfile
import shutil
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

from config import LARGE_FILE_THRESHOLD_MB, APP_VERSION
from utils.helpers import sanitize_filename
from core.merger import PDFMergerEngine


class ConverterEngine:
    def __init__(self, epub_path, output_path, settings, callback_manager):
        self.epub_path = os.path.abspath(epub_path)
        self.output_path = os.path.abspath(output_path)
        self.settings = settings
        self.cb = callback_manager
        self.image_manifest = {}
        self.stop_flag = False

    # =========================================================================
    # [v3.5.1] 密度检测算法 (保留)
    # 核心逻辑：计算“平均每个物理文件包含多少个章节”。
    # =========================================================================
    @staticmethod
    def analyze_structure(epub_path):
        try:
            book = epub.read_epub(epub_path, options={'ignore_ncx': False})
            toc_count = len(book.toc)

            unique_files = set()
            for node in book.toc:
                href = ""
                if isinstance(node, tuple):
                    if hasattr(node[0], 'href'): href = node[0].href
                elif hasattr(node, 'href'):
                    href = node.href
                if href: unique_files.add(href.split('#')[0])

            file_count = len(unique_files)
            if file_count == 0: file_count = 1

            density = toc_count / file_count
            is_monolithic = (density > 5.0) or (toc_count > 50 and file_count < 5)

            report = (
                f"📊 结构深度分析:\n"
                f"• 逻辑章节: {toc_count} | 物理文件: {file_count}\n"
                f"• 内容密度: {density:.2f} (阈值: 5.0)\n"
                f"• 判定结果: {'⚠️ 结构臃肿/单体' if is_monolithic else '✅ 结构规范/散列'}"
            )
            return is_monolithic, report
        except Exception as e:
            return False, f"分析失败: {str(e)}"

    def stop(self):
        self.stop_flag = True
        self.cb.log("🛑 正在响应停止指令...")

    def _check_stop(self):
        if self.stop_flag: raise InterruptedError("用户手动中止")

    def run(self):
        # start_time 仅用于最终日志的简要耗时记录，不参与逻辑控制
        start_time = time.time()
        self.stop_flag = False
        try:
            file_size = os.path.getsize(self.epub_path) / (1024 * 1024)
            mode = self.settings.get('mode', 'auto')

            self.cb.log(f"开始任务: {os.path.basename(self.epub_path)}")
            self._check_stop()

            is_split_mode = False
            if mode == 'split':
                is_split_mode = True
            elif mode == 'single':
                is_split_mode = False
            else:
                is_split_mode = (file_size >= LARGE_FILE_THRESHOLD_MB)

            success = False
            result_msg = ""
            final_path = ""
            cleanup_path = None

            if is_split_mode:
                self.cb.log(">>> 执行标准分卷逻辑...")
                success, files, folder = self.convert_split_mode()

                if success and self.settings.get('auto_merge', True):
                    self._check_stop()
                    self.cb.log("正在执行合并...")
                    merger = PDFMergerEngine()
                    merge_out = os.path.join(os.path.dirname(self.epub_path),
                                             f"{os.path.splitext(os.path.basename(self.epub_path))[0]}_全本.pdf")
                    # 合并进度条
                    ok, path = merger.merge(files, merge_out,
                                            lambda c, t, m: self.cb.update_progress(90 + int(c / t * 10), m))
                    if ok:
                        result_msg = "分卷及合并完成"
                        final_path = path
                        cleanup_path = folder
                    else:
                        result_msg = "分卷完成，合并失败"
                        final_path = folder
                else:
                    result_msg = "分卷已生成"
                    final_path = folder
            else:
                self.cb.log(">>> 执行单文件逻辑...")
                success, msg = self.convert_single_mode()
                result_msg = msg
                final_path = self.output_path

            duration = int(time.time() - start_time)
            m, s = divmod(duration, 60)
            return success, result_msg, f"{m}分{s}秒", final_path, cleanup_path

        except InterruptedError:
            return False, "任务中止", "0分0秒", "", None
        except Exception as e:
            return False, str(e), "0分0秒", "", None

    # === 单文件模式 ===
    def convert_single_mode(self):
        try:
            # 这里的 start_t 仅用于控制台微观日志，不影响核心
            start_t = time.time()
            self.cb.update_progress(10, "读取 EPUB...")
            book = epub.read_epub(self.epub_path)
            self._check_stop()

            with tempfile.TemporaryDirectory() as temp_dir:
                self.cb.update_progress(20, "解压资源...")
                self._extract_images_and_build_manifest(book, temp_dir)

                full_html = []
                cover_html = self._get_cover_html(book, temp_dir)
                if cover_html: full_html.append(cover_html)

                self.cb.update_progress(30, "解析章节...")
                total = len(book.spine)
                for i, item_id in enumerate(book.spine):
                    self._check_stop()
                    item = book.get_item_with_id(item_id[0])
                    if item:
                        c = self._clean_and_fix_html(item, temp_dir)
                        if c: full_html.append(c)
                    if i % 10 == 0:
                        elapsed = int(time.time() - start_t)
                        self.cb.update_progress(30 + int(i / total * 30), f"解析中 {i}/{total}")

                self.cb.log("生成排版 (CSS)...")
                final_html = f"<html><body>{''.join(full_html)}</body></html>"
                font_config = FontConfiguration()
                css = CSS(string=self._generate_css(), font_config=font_config)

                self.cb.update_progress(70, "渲染 PDF (WeasyPrint)...")
                html = HTML(string=final_html, base_url=temp_dir)

                self._check_stop()
                self.cb.log("写入磁盘 (IO)...")
                html.write_pdf(self.output_path, stylesheets=[css], font_config=font_config)

            return True, f"转换成功"
        except Exception as e:
            raise e

    # === 分卷模式 (v3.6.1 极致精简版) ===
    # 删除了所有 ETA 计算代码，进度条只显示处理对象
    def convert_split_mode(self):
        try:
            epub_dir = os.path.dirname(self.epub_path)
            folder_name = os.path.splitext(os.path.basename(self.epub_path))[0] + "_分卷"
            target_dir = os.path.join(epub_dir, folder_name)
            if not os.path.exists(target_dir): os.makedirs(target_dir)

            book = epub.read_epub(self.epub_path)
            if not book.toc: return False, [], None

            generated = []

            with tempfile.TemporaryDirectory() as temp_dir:
                self._extract_images_and_build_manifest(book, temp_dir)
                font_config = FontConfiguration()
                css = CSS(string=self._generate_css(), font_config=font_config)

                total = len(book.toc)
                for idx, node in enumerate(book.toc):
                    self._check_stop()

                    # [精简] 移除所有时间计算，只保留进度百分比和标题
                    title = node.title if hasattr(node, 'title') else node[0].title
                    safe_title = sanitize_filename(title)
                    self.cb.update_progress(int((idx / total) * 90), f"处理: {safe_title}")

                    hrefs = self._find_all_hrefs(node)
                    chapter_html = []
                    seen = set()
                    for href in hrefs:
                        parts = href.split('#');
                        fname = parts[0];
                        anchor = parts[1] if len(parts) > 1 else None
                        if fname in seen and not anchor: continue
                        seen.add(fname)
                        item = book.get_item_with_href(fname)
                        if item:
                            c = self._clean_and_fix_html(item, temp_dir, anchor_id=anchor)
                            if c: chapter_html.append(c)

                    if chapter_html:
                        out = os.path.join(target_dir, f"{idx + 1:02d}_{safe_title}.pdf")
                        HTML(string=f"<html><body>{''.join(chapter_html)}</body></html>", base_url=temp_dir).write_pdf(
                            out, stylesheets=[css], font_config=font_config)
                        generated.append(out)

            return True, generated, target_dir
        except Exception as e:
            raise e

    # === 辅助工具 ===
    def _extract_images_and_build_manifest(self, b, t):
        self.image_manifest = {}
        for i in b.get_items():
            self._check_stop()
            if i.get_type() == ebooklib.ITEM_IMAGE:
                path = os.path.join(t, i.get_name())
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as f: f.write(i.get_content())
                self.image_manifest[os.path.basename(i.get_name())] = path

    def _clean_and_fix_html(self, item, temp_dir, anchor_id=None):
        if not item: return None
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        for img in soup.find_all('img'):
            src = img.get('src')
            if src:
                fname = os.path.basename(src)
                if fname in self.image_manifest: img[
                    'src'] = f"file:///{self.image_manifest[fname].replace(os.sep, '/')}"
        return soup.find('body').decode_contents() if soup.find('body') else None

    def _find_all_hrefs(self, node):
        hrefs = []
        if isinstance(node, tuple):
            sec, children = node
            if hasattr(sec, 'href'): hrefs.append(sec.href)
            for c in children: hrefs.extend(self._find_all_hrefs(c))
        elif hasattr(node, 'href'):
            hrefs.append(node.href)
        return hrefs

    def _get_cover_html(self, b, t):
        return ""

    def _generate_css(self):
        s = self.settings
        return f"""@page {{ size: {s['paper']}; margin: {s['margin_tb']}mm {s['margin_lr']}mm; @bottom-center {{ content: counter(page); font-family: serif; font-size: 10pt; }} }} body {{ font-family: "SimSun", "Microsoft YaHei"; font-size: {s['font_size']}pt; line-height: 1.6; text-align: justify; }} img {{ max-width: 100%; }}"""