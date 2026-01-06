# core/splitter.py
# Version: v3.7.1_Split_Logic_Fix
# Last Updated: 2026-01-06
# Description: [v3.7.1] 修复分割逻辑：将“提取选定章节”改为“以选定章节为切割点切分整书”；确保内容不丢失。

import os
import re
from pypdf import PdfReader, PdfWriter


class PDFSplitterEngine:
    """
    PDF 工具箱引擎：分割、统计
    """

    def __init__(self, callback_manager=None):
        self.cb = callback_manager

    def log(self, msg):
        if self.cb: self.cb.log(msg)

    def get_pdf_info(self, pdf_path):
        """统计 PDF 信息：页数、字数"""
        try:
            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            char_count = 0

            for i, page in enumerate(reader.pages):
                if i % 50 == 0:
                    self.log(f"正在扫描第 {i}/{num_pages} 页...")
                text = page.extract_text()
                if text:
                    char_count += len("".join(text.split()))

            return True, num_pages, char_count
        except Exception as e:
            return False, 0, str(e)

    # =========================================================================
    # [v3.7.0] 按字数分割 (页级对齐)
    # =========================================================================
    def split_by_word_count(self, pdf_path, threshold_words, output_dir):
        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)

            start_page = 0
            current_segment_chars = 0
            file_index = 1
            generated_files = []

            self.log(f"开始按字数分割，阈值: {threshold_words} 字/卷")

            for i in range(total_pages):
                page_text = reader.pages[i].extract_text() or ""
                page_chars = len("".join(page_text.split()))

                current_segment_chars += page_chars

                is_last_page = (i == total_pages - 1)
                if current_segment_chars >= threshold_words or is_last_page:
                    end_page = i + 1  # 切割点（不包含）

                    writer = PdfWriter()
                    for p in range(start_page, end_page):
                        writer.add_page(reader.pages[p])

                    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
                    out_name = f"{file_index:02d}_{base_name}_part{file_index}.pdf"
                    out_path = os.path.join(output_dir, out_name)

                    with open(out_path, "wb") as f:
                        writer.write(f)

                    generated_files.append(out_path)
                    self.log(f"✅ 生成第 {file_index} 卷 (P{start_page + 1}-P{end_page}): 约 {current_segment_chars} 字")

                    start_page = end_page
                    current_segment_chars = 0
                    file_index += 1

            return True, f"成功分割为 {len(generated_files)} 个文件"

        except Exception as e:
            return False, str(e)

    # =========================================================================
    # [v3.7.1 修正] 按目录切割点分割 (Split by Cut Points)
    # 逻辑：收集所有选中章节的页码作为切割点，切分整本书，确保内容不丢失。
    # =========================================================================
    def split_by_toc_indices(self, pdf_path, selected_indices, output_dir):
        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)

            # 1. 获取平铺的目录列表
            flat_toc = []

            def _traverse(nodes):
                for node in nodes:
                    if isinstance(node, list):
                        _traverse(node)
                    else:
                        flat_toc.append(node)

            if reader.outline: _traverse(reader.outline)

            # 2. 收集切割点 (Cut Points)
            # 使用字典映射：{页码: 章节标题}
            cut_points_map = {}

            # 始终包含第 0 页 (防止第一章之前的内容丢失)
            cut_points_map[0] = "前言或起始部分"

            for idx in selected_indices:
                if idx >= len(flat_toc): continue
                node = flat_toc[idx]
                try:
                    p = reader.get_destination_page_number(node)
                    # 如果该页码已存在，优先保留用户选中的标题
                    cut_points_map[p] = node.title
                except:
                    continue

            # 3. 排序切割点
            # 加上总页数作为终点
            sorted_cuts = sorted(list(cut_points_map.keys()))
            if sorted_cuts[-1] != total_pages:
                sorted_cuts.append(total_pages)

            # 4. 执行切割
            generated = []
            for i in range(len(sorted_cuts) - 1):
                start = sorted_cuts[i]
                end = sorted_cuts[i + 1]

                if start >= end: continue  # 防止空切片

                # 确定文件名：使用切割点对应的标题
                title = cut_points_map.get(start, f"Section_P{start}")
                safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
                if len(safe_title) > 50: safe_title = safe_title[:50]

                # 写入文件
                writer = PdfWriter()
                for p in range(start, end):
                    writer.add_page(reader.pages[p])

                out_name = f"{i + 1:02d}_{safe_title}.pdf"
                out_path = os.path.join(output_dir, out_name)

                with open(out_path, "wb") as f:
                    writer.write(f)

                generated.append(out_path)
                self.log(f"✅ 生成分卷: {out_name} (P{start + 1}-P{end})")

            return True, f"全书已切分为 {len(generated)} 个文件"

        except Exception as e:
            return False, str(e)

    def get_toc(self, pdf_path):
        try:
            reader = PdfReader(pdf_path)
            toc = []

            def _visit(nodes):
                for node in nodes:
                    if isinstance(node, list):
                        _visit(node)
                    else:
                        try:
                            p_num = reader.get_destination_page_number(node)
                            toc.append((node.title, p_num))
                        except:
                            pass

            if reader.outline: _visit(reader.outline)
            return toc
        except:
            return []