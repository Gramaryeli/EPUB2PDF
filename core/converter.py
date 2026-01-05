# core/converter.py
import os
import time
import tempfile
import datetime
import gc
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

# 导入配置和工具
from config import LARGE_FILE_THRESHOLD_MB, APP_VERSION
from utils.helpers import sanitize_filename
from core.merger import PDFMergerEngine

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
        HTML 清洗与修正核心
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
                    # 注意：这里调用了独立的 sanitize_filename 函数
                    safe_title = sanitize_filename(title) or f"分册_{idx + 1}"

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