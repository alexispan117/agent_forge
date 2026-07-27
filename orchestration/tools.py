"""OrchestratorRuntime — 工具集

供 ReAct 引擎调用的工具函数，每个工具返回 (success: bool, result: str)。
"""

from orchestration.sandbox import Sandbox


class ToolRegistry:
    """工具注册与执行"""

    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox
        self._tools = {}
        self._register_all()

    def _register(self, name: str, fn):
        self._tools[name] = fn

    def _register_all(self):
        s = self._sandbox

        self._register("read_file", lambda path: _wrap(s.read_file(path)))
        self._register("write_file", lambda path, content: _wrap(s.write_file(path, content)))
        self._register("list_dir", lambda path=".": _wrap(s.list_dir(path)))
        self._register("run_python", lambda code, timeout=30: _wrap(s.run_python(code, timeout)))
        self._register("run_shell", lambda cmd, timeout=15: _wrap(s.run_shell(cmd, timeout)))
        self._register("wait", lambda seconds=1: (True, f"⏱️ 等待 {seconds} 秒"))
        self._register("think", lambda thought: (True, f"💡 记录思考: {thought[:200]}"))

    def get(self, name: str):
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())


def _wrap(result_or_exception):
    if isinstance(result_or_exception, Exception):
        return (False, str(result_or_exception))
    if isinstance(result_or_exception, tuple) and len(result_or_exception) == 2:
        return result_or_exception
    return (True, str(result_or_exception))
