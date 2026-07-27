"""OrchestratorRuntime — 沙箱（纯子进程隔离）

彻底移除 exec()，改用 subprocess 执行 Python 代码。
"""

import os, sys, subprocess, shutil, json
from pathlib import Path

SANDBOX_ROOT = Path(__file__).parent.parent / "data" / "sandbox"
PROJECT_DIR = Path(__file__).parent.parent

SHELL_WHITELIST = {"ls", "cat", "cp", "mv", "grep", "find", "head", "tail",
                   "wc", "sort", "uniq", "echo", "pwd", "date", "mkdir", "rm", "type"}


class Sandbox:
    def __init__(self, task_id: str):
        self.workspace = SANDBOX_ROOT / task_id
        self._persist_dir: Path | None = None

    def set_persist(self, d: str | Path):
        self._persist_dir = Path(d)
        self._persist_dir.mkdir(parents=True, exist_ok=True)

    def setup(self):
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "input").mkdir(exist_ok=True)
        (self.workspace / "output").mkdir(exist_ok=True)
        (self.workspace / "temp").mkdir(exist_ok=True)

    def teardown(self):
        # 持久化 output/
        if self._persist_dir and (self.workspace / "output").exists():
            for f in (self.workspace / "output").iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(self._persist_dir / f.name))
        if self.workspace.exists():
            shutil.rmtree(str(self.workspace), ignore_errors=True)

    # ── 文件工具（受限范围）──

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            # 子路径映射：docs/xxx → project/docs/xxx
            parts = p.parts
            if parts and parts[0] in ("docs", "data"):
                proj_map = {"docs": PROJECT_DIR / "docs", "data": PROJECT_DIR / "data"}
                base = proj_map[parts[0]]
                rest = Path(*parts[1:]) if len(parts) > 1 else Path()
                target = base / rest
                target.parent.mkdir(parents=True, exist_ok=True)
                return target.resolve()
            # 精确路径名映射
            name_map = {"docs": PROJECT_DIR / "docs", "data": PROJECT_DIR / "data",
                        "output": self.workspace / "output"}
            if str(p) in name_map:
                target = name_map[str(p)]
                target.mkdir(parents=True, exist_ok=True)
                return target.resolve()
            # 通用相对路径 → 沙箱内
            return (self.workspace / p).resolve()
        p = p.resolve()
        ws = self.workspace.resolve()
        if str(p).startswith(str(ws)):
            return p
        # 允许项目 docs/ data/ 目录
        for allowed in [PROJECT_DIR / "docs", PROJECT_DIR / "data", PROJECT_DIR]:
            if str(p).startswith(str(allowed.resolve())):
                return p
        raise PermissionError(f"路径 {path} 超出沙箱范围")

    def read_file(self, path: str) -> str:
        return self._resolve(path).read_text("utf-8")

    def write_file(self, path: str, content: str):
        fp = self._resolve(path)
        out_dir = self.workspace / "output"
        if not str(fp.resolve()).startswith(str(out_dir.resolve())) and \
           not str(fp.resolve()).startswith(str(PROJECT_DIR.resolve())):
            raise PermissionError("写入仅限 output/ 或项目目录")
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

    def list_dir(self, path: str = ".") -> list[str]:
        dp = self._resolve(path)
        return [str(p.relative_to(dp)) for p in sorted(dp.iterdir())]

    # ── 代码执行（纯子进程隔离）──

    def run_python(self, code: str, timeout: int = 30) -> str:
        script = self.workspace / "temp" / "_script.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(code, encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8:replace"
        env["SANDBOX_DIR"] = str(self.workspace)
        try:
            r = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, timeout=timeout,
                cwd=str(self.workspace), env=env,
            )
            out = (r.stdout or b"").decode("utf-8", errors="replace").strip()
            err = (r.stderr or b"").decode("utf-8", errors="replace").strip()
            return (out or err or "(无输出)")[:3000]
        except subprocess.TimeoutExpired:
            return f"⚠️ 执行超时 ({timeout}s)"
        except Exception as e:
            return f"⚠️ 执行异常: {e}"

    def run_shell(self, cmd: str, timeout: int = 15) -> str:
        parts = cmd.strip().split()
        if parts and parts[0] not in SHELL_WHITELIST:
            return f"⚠️ 命令 '{parts[0]}' 不在白名单"
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, timeout=timeout,
                cwd=str(self.workspace),
            )
            out = (r.stdout or b"").decode("utf-8", errors="replace").strip()
            err = (r.stderr or b"").decode("utf-8", errors="replace").strip()
            return (out or err or "(无输出)")[:2000]
        except subprocess.TimeoutExpired:
            return f"⚠️ 命令超时 ({timeout}s)"
        except Exception as e:
            return f"⚠️ 命令异常: {e}"
