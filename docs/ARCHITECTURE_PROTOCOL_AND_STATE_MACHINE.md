# AgentForge — MCP/A2A 协议接口层 & Supervisor 状态机设计文档

> 版本：v2（企业级重构后）｜实现位置：`orchestration/agent_protocol.py`、`orchestration/supervisor.py`

---

## 第一部分：MCP/A2A 双协议接口层设计

### 1.1 为什么需要协议层

重构前，Supervisor 与 Worker 之间**没有真正的通信**——`supervisor.py` 直接 `import` Worker 的函数本地调用，docker-compose 里编排的 4 个容器只是 4 个互不通信的空壳。协议层的目标是让 Supervisor 与 Worker 之间通过**标准、可发现、可容错**的 HTTP 协议通信，使「多进程/多容器部署」与「单机降级演示」共用同一套代码路径。

选型上同时实现两个互补的开放协议：

| 协议 | 解决的问题 | 在本项目中的形态 |
|---|---|---|
| **A2A（Agent-to-Agent）** | 服务发现：「你是谁？你会什么？」 | `GET /.well-known/agent.json` 发布 AgentCard |
| **MCP（Model Context Protocol）** | 工具调用：「请用你声明的能力执行这件事」 | `POST /mcp` JSON-RPC 2.0（tools/list、tools/call） |

A2A 负责「认识」，MCP 负责「干活」。二者叠加即可让一个 Agent 在**零硬编码**的情况下发现并调用另一个 Agent——Supervisor 的 `WORKER_URLS` 只需一个地址，工具名、参数模式全部运行时拉取。

### 1.2 协议模型（pydantic，三重身份共用）

```
ToolSpec      { name, description, input_schema }        # 一个可调用的工具
AgentCard     { name, version, description, endpoint,    # 一个 Agent 的名片
                capabilities[], tools[ToolSpec] }
JsonRpcRequest{ jsonrpc:"2.0", id, method, params }      # MCP 传输信封
```

同一份模型被三方复用：Worker 用它**发布**、Supervisor 用它**消费**、测试用它**断言**——协议即契约，杜绝「文档与实现两张皮」。

### 1.3 Worker 侧：三行代码接入协议

```python
card = AgentCard(name="worker-desensitize", ..., tools=[ToolSpec(name="desensitize_text", ...)])
app.include_router(build_protocol_router(card=card, tools={"desensitize_text": desensitize_text}))
```

`build_protocol_router` 生成三个端点：

| 端点 | 协议 | 语义 |
|---|---|---|
| `GET /.well-known/agent.json` | A2A | 返回 AgentCard（含工具清单与 input_schema） |
| `GET /health` | 运维 | 健康检查（compose healthcheck 复用同一端点） |
| `POST /mcp` | MCP | JSON-RPC 路由：`tools/list` 返回工具清单；`tools/call` 执行工具 |

`tools/call` 的执行语义有两个关键设计：

1. **同步工具自动上线程池**（`run_in_threadpool`）：业务工具多为同步函数（如脱敏规则引擎），直接在事件循环里跑会阻塞整个 Worker；且 LLM 同步门面内部用 `asyncio.run`，在事件循环线程里会直接 raise。协议层统一兜底，业务方无感。
2. **错误分两级**：参数不匹配 → JSON-RPC `-32602` 错误（调用方的锅）；工具内部异常 → `isError: true` 的正常 RPC 响应（执行失败但协议完好）。Supervisor 据此区分「重试无意义」与「可降级」。

### 1.4 Supervisor 侧：WorkerClient（发现 → 调用 → 退避重试）

```python
async with WorkerClient("http://worker-analyst:8001") as wc:
    card   = await wc.discover()              # A2A：拉取并缓存 AgentCard
    tools  = await wc.list_tools()            # MCP：tools/list
    result = await wc.call_tool("analyze_contract", {"contract_text": "..."})
```

容错策略严格分层：

- **传输层**（`httpx.ConnectError` / `TimeoutException`）：指数退避重试 `0.5s → 1s → 2s` + 0~0.3s 随机抖动（防多任务同时重试的惊群效应）；耗尽后抛 `RuntimeError`。
- **RPC 层**（`error` 字段 / `isError`）：**不重试**，立即抛出——这是确定性错误，重试只会放大故障。
- **编排层**（Supervisor `_call_worker`）：捕获后走 `with_fallback` 降级策略池，最终兜底为「本地 LLM 模拟该 Worker」——这就是单机演示模式与 Worker 宕机自愈共用的同一条路径。

### 1.5 与 docker-compose 拓扑的对应

```
                 ┌────────────────────────────────────┐
                 │  supervisor :8000                  │
                 │  ├─ 自身也发布 AgentCard（可被上级发现）│
                 │  └─ WorkerClient ×3                │
                 └───────┬────────┬────────┬──────────┘
              A2A+MCP/HTTP│        │        │
                 ┌───────▼─┐ ┌────▼─────┐ ┌▼──────────┐
                 │analyst  │ │desensitize│ │report     │
                 │:8001    │ │:8002      │ │:8003      │
                 └─────────┘ └───────────┘ └───────────┘
   每个节点三端点：/.well-known/agent.json · /mcp · /health
```

Supervisor 本身也挂载了协议路由（工具：`create_workflow` / `get_workflow`），意味着它可以作为**更大编排体系中的一个 Worker** 被上级 Supervisor 发现和调用——编排能力可分层嵌套，这是 A2A 发现的真正价值。

### 1.6 验证方式（全部离线可复现）

- 单元级：`pytest tests.py::test_protocol_roundtrip`（内存 ASGI 往返，含未知工具错误路径）
- 自测：`python -m orchestration.agent_protocol`
- 联调级：`GET /api/agents/cards` 并行发现三个 Worker（在线返回完整卡片，离线标记 `offline` 不拖垮接口）

---

## 第二部分：Supervisor 状态机完整解读

### 2.1 先澄清：状态机不是 LangGraph 驱动的

**这是必须纠正的认知偏差**：项目声明过「LangGraph 已集成」，但重构后的 Supervisor 状态机是**纯 Python 手写的事件驱动循环**（`asyncio.gather` 调度 DAG 就绪任务），`langgraph` 包在代码中**零 import**。当时的判断是：核心调度逻辑仅约 80 行，引入 LangGraph 的图抽象、checkpointer、状态模式会带来远超收益的学习与维护成本；mock 演示场景下也无法展示其价值。（langgraph 的清理决策见 P2 部分。）

### 2.2 双层级状态机

Supervisor 的状态机分两层：**工作流状态**与**任务状态**，通过事件总线外发每一次跃迁。

```
【工作流层】 wf["status"]

  create_workflow()
       │
       ▼
   pending ──decompose()──▶ decomposing ──解析成功──▶ ready ──execute()──▶ running ──▶ completed
                                 │
                                 └─LLM 输出非 JSON─▶ 兜底模板 ─▶ ready（不失败）
```

| 状态 | 进入条件 | 外发事件 |
|---|---|---|
| `pending` | `create_workflow()` 注册 | `workflow_created` |
| `decomposing` | `decompose()` 开始 | `workflow_status` |
| `ready` | DAG 构建完成（含兜底模板路径） | `task_tree_updated` |
| `running` | `execute()` 开始 | `workflow_status` |
| `completed` | 所有任务达终态 | `workflow_status`（携带 `clear_scores` + `final_state`） |

```
【任务层】 node.status（每个 TaskNode 独立推进）

   pending ──依赖全部 done/degraded──▶ running ──┬─ 成功 ──────────────▶ done
        │                                      ├─ 远程失败+降级生效 ────▶ degraded
        │                                      └─ 异常/真 error ───────▶ failed
        │
        └─ 依赖出现 failed（调度死锁检测）────────▶ failed（error="依赖无法满足"）
```

关键跃迁规则（都在 `execute()` 的调度循环里）：

1. **就绪判定**：`depends_on` 中每个依赖的状态 ∈ `{done, degraded}` 才可调度——**降级不阻塞下游**（v2 修复点：此前降级结果因自带 `error` 说明字段被误判 `failed`，导致下游全部死锁）。
2. **真并行**：每轮迭代把所有就绪任务用 `asyncio.gather(*, return_exceptions=True)` 一批发出，单任务异常不拖垮同批其他任务。
3. **死锁检测**：存在 `pending` 但本轮无就绪任务 → 依赖链断裂（上游 failed），剩余任务统一标记 `failed` 并终止循环，**杜绝无限等待**。
4. **故障注入**：`inject_failure()` 可在任意时刻把 running/pending 任务强制置 `failed`，立即通过 `task_status` 事件外发——演示「故障 → 死锁检测 → 或降级继续」的完整自愈叙事。

### 2.3 记忆链路在状态机中的挂点

```
decompose() 开始 ──▶ EpisodicMemory.query(request)      # 记忆唤醒
                        │命中
                        ▼
              历史经验注入拆解 Prompt + 外发 memory_recall 事件
                        │
execute() 完成 ──▶ EpisodicMemory.remember(f"workflow:{id}", 结论摘要)
                   EpisodicMemory.add_history(请求, 摘要, success)
```

记忆是**横切关注点**：不占用状态机的状态位，但在「拆解前」和「完成后」两个挂点读写，形成跨会话的经验闭环（第二次审计相似合同时，`memory_recall` 事件会把上次结论推送到总控台）。

### 2.4 CLEAR 评分的计算时机

`completed` 跃迁时从**真实执行数据**计算（替代了重构前前端的 `Math.random()`）：

| 维度 | 数据来源 | 公式要点 |
|---|---|---|
| **C**ost | 任务总数 | 任务越多 LLM 调用越多，`100 - 8×n` |
| **L**atency | `completed_at - started_at` | 越快分越高 |
| **E**fficacy | done+degraded / total | 完成率（降级算完成） |
| **A**ssurance | failed 计数 | 零失败满分，每个 failed 扣 25 |
| **R**eliability | done / total | 无故障完成率（降级会拉低） |

评分随 `workflow_status(completed)` 事件经 SSE 推到总控台，前端雷达图直接消费 `clear_scores`——联调时 6 任务全远程成功得到 `reliability: 100`，故障注入后得到 `reliability: 83`，评分与真实发生的事件严格一致。

### 2.5 事件总线（为什么不需要 Redis）

```
Supervisor._push_event(type, data)
        │
        ▼  register_event_handler() 注册的回调（lifespan 里接线）
interfaces.app.sse_push ──▶ asyncio.Queue 广播 ──▶ GET /stream（SSE）
                                                          │
                                                  总控台 orchestrator.html
```

进程内回调 + `asyncio.Queue` 扇出，零外部依赖。这套设计成立的边界是「单 Supervisor 进程」——当前架构恰好如此（Worker 不订阅事件）。Redis 只有在做**多 Supervisor 副本水平扩展**时才是必需品，这也是 P2 决策的依据。

---

## 附录 A：两套编排引擎的定位（P2 决策记录）

项目存在两套编排实现，**各有明确边界，不建议合并**：

| 维度 | 自研 Supervisor 状态机 | LangGraph 客诉系统 |
|:-----|:----------------------|:------------------|
| 代码 | `orchestration/supervisor.py`（397 行） | `orchestration/complaint_agent.py`（509 行） |
| 驱动 | 纯 Python 事件循环 + DAG 就绪调度 | LangGraph StateGraph + checkpoint 持久化 |
| 适用 | 通用任务编排（审计/搜索/报告多步骤任务） | 单一业务流（客诉 8 节点，需中断/恢复） |
| HITL | 无原生暂停/恢复 | `interrupt()` + `Command(resume)` 原生支持 |
| 持久化 | 内存 + workflow.db 状态轮询 | MemorySaver 线程级 checkpoint |
| 何时用 | 新任务类型接入总控台 | 需要人工审批节点的业务流水线 |

**决策**：保留双引擎。Supervisor 面向「任意任务的通用调度」，LangGraph 面向「固定流程 + 人工审批」。若未来客诉系统需要接入总控台统一视图，可加一层薄适配（把 complaint_graph 的 checkpoint 轮询暴露为 workflow 接口），不做引擎替换。
