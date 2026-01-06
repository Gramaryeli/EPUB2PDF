# 📖 EPUB2PDF - 专业电子书转 PDF 与工具箱

![Version](https://img.shields.io/badge/version-v3.7.1-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

**EPUB2PDF** 是一款功能强大的本地化电子书处理工具。它不仅能将 EPUB 电子书批量转换为排版精美的 PDF，还内置了专业的 PDF 工具箱，支持智能分割（按章节/按字数）和批量合并功能。

---

## ✨ 核心功能

### 1. 📚 批量 EPUB 转 PDF (核心引擎)
- **批量处理队列**：支持拖拽或批量添加文件/文件夹，自动化队列处理。
- **智能密度检测**：自动分析书籍结构，针对“单体臃肿”的网文或古籍自动切换最优转换策略，防止内存溢出。
- **美学排版**：
  - 自定义纸张大小 (A4/A5/B5)。
  - 可调节字号与页边距。
  - 自动生成页码与页眉。
  - 完美支持中文（宋体/微软雅黑）与图片自适应。
- **容错机制**：批量任务中单个文件失败不影响后续任务。

### 2. 🛠️ PDF 专业工具箱
- **🏭 PDF 合并工厂**：
  - 支持多文件合并为单文件。
  - 提供可视化的列表排序功能（上移/下移）。
- **✂️ 智能无损分割**：
  - **按目录分割 (推荐)**：读取 PDF 目录，根据用户选定的章节作为“切割点”，将**整本书**切分为多个分卷，确保前言、未选中章节等内容**完全不丢失**。
  - **按字数分割**：输入阈值（如每 2 万字），程序基于页面字数累加算法，在最接近的页面末尾进行物理切割，适合长篇小说分卷阅读。
- **📊 统计功能**：精准统计 PDF 的总页数与全文字数。

---

## 🚀 快速开始

### 环境要求
- Python 3.8 或更高版本
- 依赖库：`weasyprint`, `pypdf`, `ebooklib`, `beautifulsoup4`, `psutil`, `Pillow`
- **注意**：`WeasyPrint` 依赖 GTK3 运行时环境，Windows 用户需单独安装 GTK3。

### 源码运行
1. **克隆仓库**
   ```bash
   git clone [https://github.com/YourUsername/EPUB2PDF.git](https://github.com/YourUsername/EPUB2PDF.git)
   cd EPUB2PDF