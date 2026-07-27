"""
scripts/rename_to_enterprise.py — 一键企业级重命名脚本

功能：
1. 按 rename_map.json 移动/重命名目录和文件
2. 更新所有 .py 文件中的 import 语句
3. 更新类名引用
4. 更新 HTML {% include %} 路径
5. 更新 Dockerfile/docker-compose.yml 中的路径
6. --dry-run 预览模式，安全第一

用法：
    python scripts/rename_to_enterprise.py          # 执行重命名
    python scripts/rename_to_enterprise.py --dry-run  # 预览（不实际修改）
"""
import os, sys, json, shutil, re
from pathlib import Path

PROJECT = Path(__file__).parent.parent
MAP_PATH = PROJECT / "scripts" / "rename_map.json"
DRY_RUN = "--dry-run" in sys.argv

def log(msg, dry="  → "):
    print(f"{'🔍' if DRY_RUN else '✅'} {msg}")
    if DRY_RUN:
        print(f"    {dry}")

def load_map() -> dict:
    with open(MAP_PATH, encoding="utf-8") as f:
        return json.load(f)

def move_file(src: Path, dst: Path):
    if DRY_RUN:
        log(f"移动: {src.relative_to(PROJECT)} → {dst.relative_to(PROJECT)}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

def update_file_content(filepath: Path, replacements: dict[str, str]) -> bool:
    """替换文件内容中的字符串，返回是否修改"""
    if not filepath.exists():
        return False
    content = filepath.read_text(encoding="utf-8")
    new_content = content
    for old, new in replacements.items():
        new_content = new_content.replace(old, new)
    if new_content != content:
        if DRY_RUN:
            log(f"修改内容: {filepath.relative_to(PROJECT)}")
        else:
            filepath.write_text(new_content, encoding="utf-8")
        return True
    return False

def main():
    print(f"\n{'='*60}")
    print(f"{'🔍 [预览模式] ' if DRY_RUN else '✅ '}AgentForge 企业级重命名")
    print(f"{'='*60}\n")

    data = load_map()
    dir_map = data["directory_mappings"]
    file_renames = data["file_renames"]
    class_renames = data["class_renames"]

    # ── Phase 1: 创建新目录结构 ──
    print(f"{'─'*40}")
    print("Phase 1/5: 创建新目录结构")
    print(f"{'─'*40}")

    new_dirs = set()
    for old_dir, new_dir in dir_map.items():
        old_path = PROJECT / old_dir
        if old_path.exists():
            new_dirs.add(new_dir)
    
    # Add subdirectories from file_renames
    for new_path in file_renames.values():
        parent = str(Path(new_path).parent)
        if parent:
            new_dirs.add(parent)

    for nd in sorted(new_dirs):
        path = PROJECT / nd
        if not path.exists():
            if DRY_RUN:
                log(f"创建目录: {nd}")
            else:
                path.mkdir(parents=True, exist_ok=True)
                print(f"  ✅ 创建目录: {nd}")

    # ── Phase 2: 移动目录内容 ──
    print(f"\n{'─'*40}")
    print("Phase 2/5: 移动目录内容")
    print(f"{'─'*40}")

    for old_dir, new_dir in dir_map.items():
        src = PROJECT / old_dir
        dst = PROJECT / new_dir
        if not src.exists():
            continue
        
        # Move all files recursively
        for f in src.rglob("*"):
            if f.is_file() and "__pycache__" not in str(f):
                # Compute relative path from src to f
                rel = f.relative_to(src)
                dest = dst / rel
                move_file(f, dest)
        
        # Remove empty source dir
        if not DRY_RUN and src.exists():
            remaining = list(src.rglob("*"))
            if not remaining or all("__pycache__" in str(x) for x in remaining):
                shutil.rmtree(src)
                print(f"  🗑️ 删除空目录: {old_dir}")

    # ── Phase 3: 重命名文件（在新目录中执行）──
    print(f"\n{'─'*40}")
    print("Phase 3/5: 重命名文件")
    print(f"{'─'*40}")

    # Build src→dst mapping: both old and new paths use new directory structure
    for old_rel, new_rel in file_renames.items():
        # Try old path first (original), then new path (after Phase 2 move)
        old_candidates = [
            PROJECT / old_rel,
        ]
        old_path = None
        for oc in old_candidates:
            if oc.exists():
                old_path = oc
                break
        
        new_path = PROJECT / new_rel
        if old_path and old_path != new_path:
            if DRY_RUN:
                log(f"重命名: {old_rel} → {new_rel}")
            else:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
                print(f"  📝 重命名: {old_rel} → {new_rel}")

    # ── Phase 4: 更新所有 .py 文件中的引用 ──
    print(f"\n{'─'*40}")
    print("Phase 4/5: 更新代码引用")
    print(f"{'─'*40}")

    # Build replacement dict
    replacements = {}

    # Directory path replacements for imports
    path_import_map = {
        "from runtimes.": "from runtimes.",
        "from orchestration.": "from orchestration.",
        "from memory.": "from memory.",
        "from toolkit.": "from toolkit.",
        "from infrastructure.": "from infrastructure.",
        "from orchestration.assessors.": "from orchestration.assessors.",
        "from infrastructure.persistence.": "from infrastructure.persistence.",
        "from memory.prompts.": "from memory.prompts.",
        "from interfaces.": "from interfaces.",
    }
    replacements.update(path_import_map)

    # Class renames
    replacements.update(class_renames)

    # File import renames (for specific module imports)
    replacements["from runtimes.searcher"] = "from runtimes.searcher"
    replacements["from runtimes.knowledge_bot"] = "from runtimes.knowledge_bot"
    replacements["from runtimes.orchestrator_runtime"] = "from runtimes.orchestrator_runtime"
    replacements["from orchestration.react_engine"] = "from orchestration.react_engine"
    replacements["from orchestration.supervisor"] = "from orchestration.supervisor"
    replacements["from orchestration.state_models"] = "from orchestration.state_models"
    replacements["from orchestration.tool_schema"] = "from orchestration.tool_schema"
    replacements["from memory.short_term"] = "from memory.short_term"
    replacements["from memory.episodic"] = "from memory.episodic"
    replacements["from memory.context_compressor"] = "from memory.context_compressor"
    replacements["from orchestration.assessors.metrics"] = "from orchestration.assessors.clear_scorer"
    replacements["from memory.embedding_config"] = "from memory.embedding_config"
    replacements["from memory.reranker"] = "from memory.rerankerer"
    replacements["from memory.prompts.knowledge_prompt"] = "from memory.prompts.knowledge_prompt"
    replacements["from infrastructure.persistence.orm_models"] = "from infrastructure.persistence.orm_models"

    # Scan all .py files
    modified_count = 0
    for f in PROJECT.rglob("*.py"):
        if any(p in str(f) for p in ["__pycache__", ".venv", "rename_map"]):
            continue
        if update_file_content(f, replacements):
            modified_count += 1
    
    print(f"  📝 修改了 {modified_count} 个 Python 文件")

    # ── Phase 5: 更新非 Python 文件 ──
    print(f"\n{'─'*40}")
    print("Phase 5/5: 更新非 Python 文件")
    print(f"{'─'*40}")

    # Dockerfile
    df = PROJECT / "Dockerfile"
    if df.exists():
        update_file_content(df, {"agents/": "runtimes/", "workflow/": "orchestration/",
                                  "context/": "memory/", "tools/": "toolkit/", "web/": "interfaces/"})

    # docker-compose.yml
    dc = PROJECT / "docker-compose.yml"
    if dc.exists():
        update_file_content(dc, {"services/supervisor": "services/supervisor",
                                  "services/worker_analyst": "services/worker_analyst"})

    # HTML templates
    for f in PROJECT.rglob("*.html"):
        if "orchestrator.html" in str(f):
            continue
        update_file_content(f, {"agents/": "runtimes/", "workflow/": "orchestration/",
                                "tools/": "toolkit/", "web/": "interfaces/"})

    # .env.example
    env = PROJECT / ".env.example"
    if env.exists():
        update_file_content(env, {})

    # ── 完成 ──
    print(f"\n{'='*60}")
    if DRY_RUN:
        print("🔍 预览完成。移除 --dry-run 执行实际重命名。")
    else:
        print("✅ 重命名完成！新目录结构：")
        for d in sorted([p for p in PROJECT.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))]):
            py_count = len(list(d.rglob("*.py")))
            if py_count > 0:
                print(f"  📂 {d.name}/ ({py_count} .py 文件)")
    print(f"{'='*60}\n")

    # ── 输出类名对照表 ──
    print("📋 类名对照表（供PPT更新参考）：")
    print(f"  {'旧类名':<25} → {'新类名':<25}")
    print(f"  {'─'*25}   {'─'*25}")
    for old, new in sorted(data["class_renames"].items()):
        print(f"  {old:<25} → {new:<25}")

if __name__ == "__main__":
    main()
