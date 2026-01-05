# core/merger.py
import os
import re
from pypdf import PdfWriter, PdfReader

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