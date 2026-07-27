"""PDF 年报 → rag_data/ 知识库文档

从 knowledge_base 提取文本，保存为 .md 到 rag_data/
分块策略：按章节拆分，保留标题层级
"""

import sys, re
from pathlib import Path

KB = Path(r"D:\hermes\work\agentgroup\knowledge_base")
RAG = Path(r"D:\hermes\work\agentgroup\agent_forge\docs")
RAG.mkdir(parents=True, exist_ok=True)

import fitz  # PyMuPDF

pdfs = sorted(KB.glob("*.pdf"))
print(f"📄 发现 {len(pdfs)} 个 PDF 文件\n")

for pdf_path in pdfs:
    print(f"── {pdf_path.name} ({pdf_path.stat().st_size / 1024 / 1024:.1f}MB) ──")
    
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    md_name = pdf_path.stem + ".md"
    md_path = RAG / md_name
    
    lines = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        # 清洗：去掉页眉页脚编号、多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)  # 页码
        # 保留中文段落结构
        text = re.sub(r'(?<=[。！？；])\s*\n', '\n\n', text)
        lines.append(text)
        
        if (i + 1) % 10 == 0:
            print(f"   进度: {i+1}/{total_pages} 页")
    
    # 合并为 Markdown
    content = "\n".join(lines)
    # 清理多余空行
    content = re.sub(r'\n{4,}', '\n\n\n', content)
    
    md_path.write_text(content, encoding="utf-8")
    mb = len(content) / 1024 / 1024
    print(f"   ✅ → {md_path.name} ({mb:.1f}MB, {total_pages} 页)\n")
    doc.close()

print("🎉 全部导入完成！")
