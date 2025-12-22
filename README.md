# 📚 EPUB2PDF 转换器 (v3.4.0)

一个基于 Python 开发的高效电子书转换工具，专为处理大型古籍（如《二十四史》）及复杂排版设计。

## ✨ 核心亮点

* **智能分卷**：自动识别大文件 (>20MB) 进行拆分转换，避免内存溢出。
* **工作流闭环**：拆分 -> 转换 -> 自动合并 -> 清理，一键完成。
* **排版完美还原**：
    * 将正文内的“注”字图片自动转换为右上角微型角标。
    * 建立全局图片索引，修复复杂路径下的图片丢失问题。
* **目录重构**：合并时自动重建层级目录（书名作为一级目录）。

## 🛠️ 安装与运行

1. 克隆项目：
   ```bash
   git clone [https://github.com/您的用户名/EPUB2PDF.git](https://github.com/您的用户名/EPUB2PDF.git)
   ```
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 运行：
   ```bash
   python APP.py
   ```

## 📦 下载使用

普通用户无需配置 Python 环境，请直接前往 [Releases 页面](这里稍后填您的GitHub链接/releases) 下载最新 Windows 可执行文件 (.exe)。