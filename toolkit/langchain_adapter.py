"""AgentForge — LangChain 工具适配层

将 tools/registry.py 注册的工具包装为 LangChain StructuredTool，
使 AgentForge 的工具可以被 LangChain Agent 使用。
"""

from typing import Any, Type
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from toolkit.registry import get_tool, list_tools, call_tool


def _create_schema(name: str, description: str, parameters: dict | None = None) -> Type[BaseModel]:
    """动态创建 Pydantic Schema（给 LangChain 用）

    从注册表的 JSON Schema parameters 生成字段，否则 StructuredTool
    无法把 invoke 参数传给底层函数（空 schema → 参数丢失）。
    Pydantic v2 需要 __annotations__ + 类属性 Field 组合。
    """
    annotations: dict[str, Any] = {}
    fields: dict[str, Any] = {}
    props = (parameters or {}).get("properties", {})
    required = set((parameters or {}).get("required", []))
    for pname, pinfo in props.items():
        ptype = pinfo.get("type", "string")
        pytype = {
            "string": str, "integer": int, "number": float,
            "boolean": bool, "array": list, "object": dict,
        }.get(ptype, str)
        annotations[pname] = pytype
        if pname in required:
            fields[pname] = Field(description=pinfo.get("description", ""))
        else:
            fields[pname] = Field(default=None, description=pinfo.get("description", ""))
    if not fields:
        annotations["_unused"] = str
        fields["_unused"] = Field(default="", description="未使用参数")
    return type(
        f"{name}_schema",
        (BaseModel,),
        {"__doc__": description, "__annotations__": annotations, **fields},
    )


def to_langchain_tool(tool_name: str) -> StructuredTool:
    """将 AgentForge 注册的工具转为 LangChain StructuredTool

    Args:
        tool_name: tools/registry.py 中注册的工具名称

    Returns:
        StructuredTool 实例
    """
    t = get_tool(tool_name)
    if not t:
        raise ValueError(f"工具 '{tool_name}' 未注册")

    def _run(**kwargs) -> str:
        return call_tool(tool_name, **kwargs)

    return StructuredTool.from_function(
        name=t["name"],
        description=t["description"],
        func=_run,
        args_schema=_create_schema(t["name"], t["description"], t.get("parameters")),
    )


def build_langchain_tools() -> list[StructuredTool]:
    """将所有注册的工具转为 LangChain 工具列表"""
    return [to_langchain_tool(name) for name in list_tools()]


def to_langchain_agent(tools: list[StructuredTool] | None = None, model=None):
    """创建一个 LangChain AgentExecutor（ReAct 模式）

    Args:
        tools: LangChain 工具列表，不传则自动加载所有注册工具
        model: ChatOpenAI 实例，不传则从环境变量创建

    Returns:
        AgentExecutor 实例
    """
    from langchain.agents import AgentExecutor, create_react_agent
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import PromptTemplate
    import os
    from dotenv import load_dotenv

    load_dotenv()

    if model is None:
        model = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
            openai_api_key=os.getenv("LLM_API_KEY"),
            openai_api_base=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            temperature=0.3,
        )

    if tools is None:
        tools = build_langchain_tools()

    prompt = PromptTemplate.from_template(
        """你是一个 AI 助手，可以使用以下工具。

{tools}

工具名称: {tool_names}

请使用 ReAct 模式工作：
Thought: 分析当前情况，决定下一步
Action: 选择要使用的工具名称
Action Input: 输入参数（JSON 格式）
Observation: 工具返回的结果
... (循环直到任务完成)

用户的输入: {input}

{agent_scratchpad}"""
    )

    agent = create_react_agent(model, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=10,
        verbose=True,
        handle_parsing_errors=True,
    )
