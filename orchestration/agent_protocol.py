"""
orchestration/agent_protocol.py — Agent 互联协议层（MCP + A2A 双协议）

职责：
1. A2A 发现：GET /.well-known/agent.json 暴露 AgentCard（能力/工具清单/端点）
2. MCP 工具：POST /mcp 处理 JSON-RPC 2.0 的 tools/list 与 tools/call
3. WorkerClient：Supervisor 侧异步协议客户端（发现 → 调用 → 退避重试）

用法（Worker 侧）：
    card = AgentCard(name="worker-desensitize", ..., tools=[ToolSpec(...)])
    app.include_router(build_protocol_router(card=card, tools={"desensitize_text": desensitize_text}))

用法（Supervisor 侧）：
    async with WorkerClient("http://worker-desensitize:8002") as wc:
        card = await wc.discover()
        result = await wc.call_tool("desensitize_text", {"text": "..."})

自测：python -m orchestration.agent_protocol（内存 ASGI 往返，无需起真实服务）
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import random
import uuid
from typing import Any, Awaitable, Callable, Optional, Union

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("agent_protocol")

ToolFn = Union[Callable[..., Any], Callable[..., Awaitable[Any]]]

# ═══════════════════════════════════════════════
# 协议模型
# ═══════════════════════════════════════════════

class ToolSpec(BaseModel):
    """MCP 工具描述（对齐 MCP tools/list 返回结构）。"""
    name: str
    description: str = ""
    input_schema: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})


class AgentCard(BaseModel):
    """A2A Agent 卡片：服务发现的最小契约。"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    endpoint: str = ""
    capabilities: list[str] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    method: str
    params: dict = Field(default_factory=dict)


def _rpc_ok(req_id: str, result: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})


def _rpc_err(req_id: str, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


# ═══════════════════════════════════════════════
# Worker 侧：协议路由工厂
# ═══════════════════════════════════════════════

def build_protocol_router(*, card: AgentCard, tools: dict[str, ToolFn]) -> APIRouter:
    """生成协议路由，挂到任一 Worker 的 FastAPI app 上。

    暴露三个端点：
    - GET  /.well-known/agent.json   A2A 服务发现
    - POST /mcp                      MCP JSON-RPC（tools/list、tools/call）
    - GET  /health                   健康检查（compose healthcheck 复用）
    """
    router = APIRouter()

    @router.get("/.well-known/agent.json")
    async def agent_card() -> dict:
        return card.model_dump()

    @router.get("/health")
    async def health() -> dict:
        return {"status": "ok", "agent": card.name, "version": card.version}

    @router.post("/mcp")
    async def mcp_endpoint(req: JsonRpcRequest) -> JSONResponse:
        if req.method == "tools/list":
            return _rpc_ok(req.id, {"tools": [t.model_dump() for t in card.tools]})

        if req.method == "tools/call":
            name = req.params.get("name", "")
            arguments = req.params.get("arguments", {})
            fn = tools.get(name)
            if fn is None:
                return _rpc_err(req.id, -32602, f"未知工具: {name}（可用: {sorted(tools)}）")
            try:
                if inspect.iscoroutinefunction(fn):
                    out = await fn(**arguments)
                else:
                    # 同步工具放线程池执行，避免阻塞事件循环
                    from fastapi.concurrency import run_in_threadpool
                    out = await run_in_threadpool(fn, **arguments)
                return _rpc_ok(req.id, {
                    "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                    "isError": False,
                })
            except TypeError as e:  # 参数不匹配
                return _rpc_err(req.id, -32602, f"工具参数错误: {e}")
            except Exception as e:
                logger.exception(f"[{card.name}] 工具 {name} 执行失败")
                return _rpc_ok(req.id, {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True,
                })

        return _rpc_err(req.id, -32601, f"Method not found: {req.method}")

    return router


# ═══════════════════════════════════════════════
# Supervisor 侧：异步协议客户端
# ═══════════════════════════════════════════════

class WorkerClient:
    """Supervisor → Worker 的异步协议客户端（A2A 发现 + MCP 调用 + 退避重试）。"""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 15.0,
        max_retries: int = 2,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._client = client
        self._owns_client = client is None
        self._card: Optional[AgentCard] = None

    async def __aenter__(self) -> "WorkerClient":
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_s)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def discover(self) -> AgentCard:
        """A2A 发现：拉取并缓存 AgentCard。"""
        assert self._client is not None, "请先 async with 或手动赋值 client"
        resp = await self._client.get("/.well-known/agent.json")
        resp.raise_for_status()
        self._card = AgentCard(**resp.json())
        logger.info(f"[A2A] 发现 Agent: {self._card.name} v{self._card.version}，工具数={len(self._card.tools)}")
        return self._card

    async def list_tools(self) -> list[ToolSpec]:
        if self._card is None:
            await self.discover()
        assert self._card is not None
        return self._card.tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """MCP tools/call：带指数退避重试（仅网络类错误），RPC 层错误立即抛出。"""
        assert self._client is not None, "请先 async with 或手动赋值 client"
        payload = JsonRpcRequest(method="tools/call", params={"name": name, "arguments": arguments})
        last_exc: Optional[Exception] = None

        body: dict = {}
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._client.post("/mcp", json=payload.model_dump())
                resp.raise_for_status()
                body = resp.json()
                break
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt < self.max_retries:
                    delay = 0.5 * (2 ** attempt) + random.uniform(0, 0.3)
                    logger.warning(f"[MCP] {self.base_url} 调用失败（第 {attempt + 1} 次），{delay:.1f}s 后重试")
                    await asyncio.sleep(delay)
        else:
            raise RuntimeError(f"Worker {self.base_url} 在 {self.max_retries + 1} 次尝试后不可达: {last_exc}")

        if "error" in body:
            raise RuntimeError(f"MCP RPC 错误 {body['error'].get('code')}: {body['error'].get('message')}")

        result = body.get("result", {})
        if result.get("isError"):
            raise RuntimeError(f"工具 {name} 执行失败: {result.get('content')}")

        texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        if not texts:
            return {}
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return {"text": texts[0]}


# ═══════════════════════════════════════════════
# 内存自测：python -m orchestration.agent_protocol
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    from fastapi import FastAPI

    def demo_desensitize(text: str) -> dict:
        return {"masked_text": text[:3] + "***", "total_masked": 1}

    card = AgentCard(
        name="worker-desensitize",
        description="脱敏 Worker（MCP/A2A 双协议）",
        endpoint="http://worker-desensitize:8002",
        capabilities=["desensitize", "validate"],
        tools=[
            ToolSpec(
                name="desensitize_text",
                description="对文本执行五类敏感字段脱敏",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )
        ],
    )

    app = FastAPI(title="protocol-selftest")
    app.include_router(build_protocol_router(card=card, tools={"desensitize_text": demo_desensitize}))

    async def _selftest() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as raw:
            async with WorkerClient("http://test", client=raw) as wc:
                discovered = await wc.discover()
                print(f"[A2A] AgentCard: {discovered.name}，能力={discovered.capabilities}")
                tools = await wc.list_tools()
                print(f"[MCP] tools/list: {[t.name for t in tools]}")
                result = await wc.call_tool("desensitize_text", {"text": "身份证号 110101199003077758"})
                print(f"[MCP] tools/call 结果: {result}")
                try:
                    await wc.call_tool("nonexistent", {})
                except RuntimeError as e:
                    print(f"[MCP] 错误路径验证通过: {e}")

    asyncio.run(_selftest())
