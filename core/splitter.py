# core/splitter.py
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
        """[新增] 统计 PDF 信息：页数、字数"""
        try:
            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            char_count = 0

            # 简单的进度反馈
            for i, page in enumerate(reader.pages):
                if i % 50 == 0:
                    self.log(f"正在扫描第 {i}/{num_pages} 页...")
                text = page.extract_text()
                if text:
                    char_count += len("".join(text.split()))

            return True, num_pages, char_count
        except Exception as e:
            return False, 0, str(e)

    def split_by_toc_indices(self, pdf_path, selected_indices, output_dir):
        # ... (保持原有的按目录分割逻辑) ...
        try:
            reader = PdfReader(pdf_path)
            flat_toc = []

            def _traverse(nodes):
                for node in nodes:
                    if isinstance(node, list):
                        _traverse(node)
                    else:
                        flat_toc.append(node)

            if reader.outline: _traverse(reader.outline)

            segments = []
            for idx in selected_indices:
                if idx >= len(flat_toc): continue
                node = flat_toc[idx]
                start = reader.get_destination_page_number(node)
                end = len(reader.pages)
                if idx + 1 < len(flat_toc):
                    try:
                        end = reader.get_destination_page_number(flat_toc[idx + 1])
                    except:
                        pass
                segments.append({"title": node.title, "start": start, "end": end})

            generated = []
            for i, seg in enumerate(segments):
                writer = PdfWriter()
                for p in range(seg['start'], seg['end']): writer.add_page(reader.pages[p])
                safe = re.sub(r'[\\/*?:"<>|]', "", seg['title']).strip()
                out = os.path.join(output_dir, f"{i + 1:02d}_{safe}.pdf")
                with open(out, "wb") as f:
                    writer.write(f)
                generated.append(out)
                self.log(f"✅ 导出: {safe}")

            return True, f"成功导出 {len(generated)} 个文件"
        except Exception as e:
            return False, str(e)

    def split_by_word_count(self, pdf_path, target_chars, output_dir):
        # ... (保持原有的按字数分割逻辑) ...
        # 为节省篇幅，此处省略，请保留您之前文件中的代码
        # 如果需要，我可以再次提供
        pass

    def get_toc(self, pdf_path):
        try:
            reader = PdfReader(pdf_path)
            toc = []

            def _visit(nodes):
                for node in nodes:
                    if isinstance(node, list):
                        _visit(node)
                    else:
                        toc.append((node.title, reader.get_destination_page_number(node)))

            if reader.outline: _visit(reader.outline)
            return toc
        except:
            return []