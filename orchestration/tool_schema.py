"""OrchestratorRuntime — 工具 Schema 约束

函数注册 + Schema → LLM 只选不造。
"""

from dataclasses import dataclass, field


@dataclass
class ToolSchema:
    name: str
    description: str
    params: dict  # {"param_name": "type description"}
    examples: list[str] = field(default_factory=list)


TOOL_SCHEMAS = [
    ToolSchema("list_dir", "列出目录下的文件", {"path": "str - 目录路径（默认 .）"}),
    ToolSchema("read_file", "读取文件内容", {"path": "str - 文件路径"}),
    ToolSchema("write_file", "写入文件内容到 output/ 目录", {"path": "str - 相对路径", "content": "str - 文件内容"}),
    ToolSchema("run_python", "执行 Python 代码", {"code": "str - Python 代码", "timeout": "int - 超时秒数（可选）"}),
    ToolSchema("run_shell", "执行 Shell 命令（白名单限制）", {"cmd": "str - 命令", "timeout": "int - 超时秒数（可选）"}),
    ToolSchema("wait", "等待一段时间", {"seconds": "int - 秒数"}),
]


def schema_to_prompt() -> str:
    """生成供 LLM 使用的工具列表"""
    lines = ["可用工具（工具名不可修改）:"]
    for s in TOOL_SCHEMAS:
        params = ", ".join(f"{k}: {v}" for k, v in s.params.items())
        lines.append(f"  {s.name}({params})  —  {s.description}")
        if s.examples:
            for ex in s.examples:
                lines.append(f"    例: {ex}")
    return "\n".join(lines)


VALID_TOOL_NAMES = {s.name for s in TOOL_SCHEMAS}


def validate_plan(plan: list[dict]) -> list[dict]:
    """校验计划中的工具名，剔除不合法的"""
    return [s for s in plan if s.get("action") in VALID_TOOL_NAMES]
