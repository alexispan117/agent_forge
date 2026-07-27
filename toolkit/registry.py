"""AgentForge — 工具注册中心

所有 Agent 使用的工具统一在此注册，实现跨 Agent 复用。
参考 MokioClaw 的 StructuredTool 注册模式 + 教程 6.2.6 节工具设计法则。
"""

from typing import Any, Callable

_register: dict[str, dict] = {}
_initialized = False


def register(
    name: str,
    description: str,
    fn: Callable,
    parameters: dict | None = None,
    requires_env: list[str] | None = None,
):
    """注册一个工具

    工具设计法则（教程 6.2.6）：
    - 名称清晰：动词+名词格式
    - 描述详尽：写清楚何时用/何时不用
    - 参数有类型：Pydantic Field + 描述
    - 错误要友好：返回描述性信息，不抛异常

    Args:
        name: 工具名称（如 "web_search"、"file_read"）
        description: 工具描述（给 LLM 看的说明书）
        fn: 工具函数
        parameters: JSON Schema 格式的参数定义
        requires_env: 所需的环境变量列表
    """
    _register[name] = {
        "name": name,
        "description": description,
        "fn": fn,
        "parameters": parameters or {},
        "requires_env": requires_env or [],
    }


def get_tool(name: str) -> dict | None:
    """按名称获取工具"""
    return _register.get(name)


def list_tools() -> list[str]:
    """列出所有已注册的工具名称"""
    return list(_register.keys())


def build_tool_schemas() -> list[dict]:
    """返回所有工具的 JSON Schema 列表（供 LLM 调用参考）"""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        }
        for t in _register.values()
    ]


def call_tool(name: str, **kwargs) -> Any:
    """调用已注册的工具

    Args:
        name: 工具名称
        **kwargs: 工具参数

    Returns:
        工具执行结果（字符串）

    Raises:
        ValueError: 工具不存在时
    """
    tool = _register.get(name)
    if not tool:
        return f"错误: 工具 '{name}' 不存在。可用工具: {', '.join(list_tools())}"
    try:
        return tool["fn"](**kwargs)
    except Exception as e:
        return f"工具 '{name}' 执行失败: {e}"


def init_default_tools():
    """注册 AgentForge 内置工具（在启动时调用一次）"""
    global _initialized
    if _initialized:
        return
    _initialized = True


def reset():
    """清空注册表（测试用）"""
    _register.clear()
    global _initialized
    _initialized = False
