# AgentForge — 项目上下文说明书（重构后状态）

> 更新日期: 2026-07-18（企业级重构完成后同步）
> 用途: 精确描述当前项目真实状态。P0 全部完成，高价值 P1 已完成，遗留项见第 5 节

---

## 1. 项目终极目标

打造面向金融/制造/政务企业的商业化 AI Agent 演示产品，通过 30 分钟深度路演向企业 CTO 证明：
1. 产品具备生产级工程能力（非玩具Demo）
2. 个人具备全栈架构设计能力
3. 可量化商业价值（成本/效率/安全）

## 2. 当前目录树与职责（重构后真实状态）

```
agent_forge/
│
├── core/                          # 内核层：共享库，不独立运行
│   ├── llm_factory.py             # 统一 LLM 工厂 v2（全异步 achat/aembed，Mock/Real 双轨，
│   │                              #   指数退避重试，确定性 embedding，LLMFacade 同步兼容门面）
│   ├── config.py                  # 统一配置加载器（config.yaml + ${ENV_VAR} 展开 + .env）
│   ├── with_fallback.py           # @with_fallback v2（同步/异步双分支、真超时、
│   │                              #   指数退避+抖动、retry_on 白名单、指标钩子）
│   └── mock_responses/            # 7 个 Mock 响应模板（decompose/anomaly/desensitize/
│                                  #   report/memory/general/fallback）
│
├── runtimes/                      # 运行时业务逻辑（原 agents/）
│   ├── base_runtime.py            # BaseRuntime 基类
│   ├── searcher.py                # Searcher 搜索服务（requests 已换 httpx）
│   ├── knowledge_bot.py           # KnowledgeBot 知识问答（ChromaDB + 混合检索 + RRF）
│   └── orchestrator_runtime.py    # OrchestratorRuntime 工作流（ReAct + DAG + 沙箱）
│
├── orchestration/                 # 编排层
│   ├── supervisor.py              # Supervisor v2（全异步、工作流级任务隔离、asyncio.gather
│   │                              #   真并行、MCP 远程调用 + 本地降级、记忆链路、真实 CLEAR）
│   ├── agent_protocol.py          # ★ MCP/A2A 协议层（AgentCard/ToolSpec/JSON-RPC、
│   │                              #   build_protocol_router、WorkerClient 退避重试）
│   ├── react_engine.py            # ReAct 引擎
│   ├── state_models.py            # SQLite 状态模型（raw sqlite3 + WAL，独立体系）
│   ├── sandbox.py                 # 子进程沙箱隔离
│   ├── tool_schema.py             # 工具 Schema 约束
│   ├── tools.py                   # 工具实现（list_dir/read_file/run_python...）
│   └── assessors/
│       └── clear_scorer.py        # CLEAR 五维评分器
│
├── memory/                        # 记忆层
│   ├── short_term.py              # 短期记忆
│   ├── episodic.py                # 情景记忆 v2（query() 关键词检索、load_seed() 种子加载、
│   │                              #   存储迁至 data/memory/、全 utf-8）
│   ├── context_compressor.py      # 上下文压缩
│   ├── prompt_builder.py          # Prompt 构建器
│   ├── embedding_config.py        # Embedding 配置
│   ├── reranker.py                # 重排序器
│   ├── workspace.py               # 工作区管理
│   └── prompts/
│       ├── knowledge_prompt.py    # 知识问答 Prompt
│       └── search_prompt.py       # 搜索 Prompt
│
├── toolkit/                       # 工具包
│   ├── registry.py                # 工具注册中心
│   ├── vector_store.py            # ChromaDB 向量存储
│   ├── embeddings.py              # Embedding API 封装
│   ├── browser_tool.py            # 浏览器工具
│   ├── cache.py                   # 搜索缓存
│   └── langchain_adapter.py       # LangChain 适配器
│
├── infrastructure/                # 基础设施
│   ├── circuit_breaker.py         # 熔断器
│   ├── approval.py                # 审批处理器
│   ├── cost_tracker.py            # 成本追踪
│   ├── logging.py                 # 日志
│   └── persistence/               # 数据持久化（★ 全异步 v2）
│       ├── database.py            # 同步 Engine + WAL + AsyncSession 异步外观
│       │                          #   （asyncio.to_thread，零新依赖）
│       ├── orm_models.py          # ORM 模型（_utcnow 替代弃用的 utcnow）
│       └── crud.py                # 全异步 CRUD（bcrypt 哈希兼容旧 salt:sha256 校验、
│                                  #   get_recent_messages/add_feedback/get_feedback_stats）
│
├── interfaces/                    # 接口层
│   ├── app.py                     # FastAPI 主应用 v2（/health、lifespan 异步建表 +
│   │                              #   Supervisor 事件→SSE 接线、配置统一走 core.config）
│   ├── auth.py                    # 认证模块（全异步、get_user_by_session 返回 dict）
│   ├── feedback.py                # 用户反馈（落库持久化）
│   ├── templates.py               # Jinja2 模板引擎
│   ├── routes/
│   │   ├── agent.py               # Agent 路由（agent.execute/init 经 run_in_threadpool）
│   │   └── workflows.py           # ★ 工作流 API（POST/GET /api/workflows、
│   │                              #   inject-failure、/api/agents/cards 服务发现聚合）
│   ├── static/
│   │   ├── css/dashboard.css      # 白底 SaaS Design Tokens + 三栏 Grid
│   │   ├── js/dashboard.js        # decodeText 动效 + CLEAR 雷达图
│   │   └── fonts/                 # Inter + JetBrains Mono（本地加载）
│   └── templates/
│       ├── base.html              # 基础布局
│       ├── orchestrator.html      # 总控台 v2（对接 /api/workflows 真实 API、
│       │                          #   服务发现面板、CLEAR 用后端真实评分）
│       ├── workflow.html          # 工作流子页（路由名已修正 /agent/workflow/run）
│       └── ... (index, login, register, dashboard, chat, result, agent_info, auth_base, error)
│
├── services/                      # 微服务入口（可独立启动的进程，全部挂载 MCP/A2A 协议路由）
│   ├── supervisor/main.py         # Supervisor 总控节点（:8000，自身也发布 AgentCard）
│   ├── worker_analyst/main.py     # 分析 Worker（:8001，工具 analyze_contract/cross_validate）
│   ├── worker_desensitize/main.py # 脱敏 Worker（:8002，工具 desensitize_text/validate_desensitization）
│   └── worker_report/main.py      # 报告 Worker（:8003，工具 generate_report/score_clear）
│
├── data/
│   ├── demo/
│   │   ├── contracts/             # 5 份脱敏演示合同
│   │   ├── audit_rules.json       # 7 条审计规则
│   │   └── seed_memory.json       # 情景记忆种子（sessions 结构）
│   ├── memory/                    # 情景记忆持久化（EpisodicMemory JSON）
│   ├── app.db                     # 用户/会话/反馈（SQLAlchemy）
│   ├── workflow.db                # 工作流 SQLite（state_models 体系）
│   └── workflow_outputs/          # 沙箱输出持久化
│
├── docs/
│   ├── ARCHITECTURE_PROTOCOL_AND_STATE_MACHINE.md  # ★ 协议层 + 状态机设计文档
│   └── ... (知识库文档)
│
├── scripts/
│   ├── demo.sh                    # 一键启动脚本
│   └── kimi_k3_prompt.md          # 重构任务提示词（历史存档）
│
├── .github/workflows/test.yml     # CI（compileall 8 包语法检查 + pytest）
├── config.yaml                    # 全局配置（密钥全部 ${ENV_VAR} 占位，不落库）
├── pytest.ini                     # pytest 配置（asyncio_mode=auto）
├── Dockerfile                     # 通用镜像（多服务共用）
├── docker-compose.yml             # 4 容器编排（supervisor + 3 workers，Redis 已移除）
├── requirements.txt               # 依赖（与实际 import 对齐，含 sqlalchemy/bcrypt/httpx）
├── requirements-test.txt          # 测试依赖（pytest/pytest-asyncio/httpx）
├── .env.example                   # 环境变量模板（含 3 个密钥位 + 3 个 WORKER_*_URL）
├── tests.py                       # ★ pytest 套件（21 用例，全绿）
└── main.py                        # CLI 入口
```

## 3. 核心技术栈

| 类别 | 技术 | 版本/备注 |
|:----|:----|:---------|
| 语言 | Python 3.11 | |
| Web 框架 | FastAPI | 全异步路由 + SSE 流式推送 |
| 模板引擎 | Jinja2 | 白底 SaaS 风格（前端框架升级评估中，见第 5 节 P2） |
| 编排 | 纯 Python 异步事件循环 | asyncio.gather DAG 调度（**非 LangGraph**，见设计文档 2.1 节） |
| Agent 互联 | MCP + A2A 双协议 | A2A 服务发现 + MCP JSON-RPC 工具调用 |
| 数据库 | SQLite (WAL) | 同步 Engine + asyncio.to_thread 异步外观 |
| ORM | SQLAlchemy 2.0 | **已异步化**（AsyncSession 外观模式） |
| 向量数据库 | ChromaDB | 知识库检索 |
| LLM API | DeepSeek / OpenAI 兼容 | MockLLM 模式默认（全异步、确定性 embedding） |
| Embedding | 阿里百炼 DashScope | text-embedding-v3 |
| 密码哈希 | bcrypt | 兼容旧 salt:sha256 格式校验 |
| 图表 | ECharts 5 (CDN) | 雷达图 + 树图（本地化列入 P2） |
| 容器化 | Docker / Docker-Compose | 4 容器（Redis 已移除：进程内事件回调替代） |
| 测试 | pytest + pytest-asyncio | 21 用例，CI 集成 |

## 4. 现有功能模块（已具备 ✅）

### 4.1 三个运行时
- **Searcher**（搜索服务）：百度/DDG 双引擎 + 缓存 + AI 摘要（HTTP 客户端已换 httpx）
- **KnowledgeBot**（知识问答）：ChromaDB + 混合检索 + RRF + 熔断器 + 优雅降级
- **OrchestratorRuntime**（工作流编排）：ReAct 循环 + DAG 并行 + 子进程沙箱 + 自动重试

### 4.2 编排与评估
- **Supervisor v2**：全异步任务拆解 + DAG 真并行调度 + 工作流级状态隔离 + 故障注入；远程 Worker 调用走 MCP 协议，不可达时自动降级本地 LLM 模拟（单机演示/宕机自愈同一路径）
- **MCP/A2A 协议层**：AgentCard 服务发现（`/.well-known/agent.json`）+ JSON-RPC 工具调用（`/mcp`）+ 健康检查三端点；WorkerClient 指数退避重试
- **CLEAR Scorer**：五维评分（成本/延迟/效能/保证/可靠性），由真实执行数据计算并随 SSE 推送
- **@with_fallback v2**：同步/异步双分支 + 真超时 + 退避抖动 + 异常白名单 + 指标钩子

### 4.3 记忆链路（已贯通 ✅）
- 拆解前 `EpisodicMemory.query()` 唤醒历史经验注入 Prompt，推送 `memory_recall` 事件
- 完成后 `remember()` + `add_history()` 写回结论，形成跨会话经验闭环
- 首启自动加载 `data/demo/seed_memory.json` 种子

### 4.4 部署与演示
- **Docker-Compose 4 容器**：supervisor + 3 workers，互联已实测（远程调用全部 done，无降级）
- **离线 Mock 模式**：LLM_MOCK_MODE=true，7 个 JSON 响应模板，零网络请求
- **密钥外移**：config.yaml 全部 `${ENV_VAR}` 占位，core/config.py 统一展开
- **5 份演示合同 + 7 条审计规则 + 情景记忆种子**

### 4.5 接口层
- **SSE 实时推送**：/stream 端点，Supervisor 事件总线已接线（此前 register_event_handler 全项目零调用）
- **工作流 API**：`POST/GET /api/workflows`、`/inject-failure`、`/api/agents/cards`
- **Orchestrator Dashboard**：三栏 Grid + 服务发现面板 + 后端真实 CLEAR 评分（替代 Math.random）
- **健康检查**：所有服务 `/health` 端点（compose healthcheck 复用）

### 4.6 测试体系（新建 ✅）
- 21 个 pytest 用例：全包 import 冒烟（断链回归）、LLM 异步/并发/确定性、with_fallback 双分支降级、情景记忆、协议 ASGI 往返、Supervisor E2E + 隔离 + 故障注入、异步 CRUD、HTTP 端到端
- CI：compileall 语法检查 8 包 + pytest，GitHub Actions

## 5. 遗留事项（当前真实差距）

### P1 — 功能完整性

| 问题 | 现状 | 影响 |
|:----|:----|:----|
| **无指标采集管道** | CLEAR 评分实时计算但未持久化时序数据，无 Prometheus 端点 | 无法展示长期运行趋势图 |
| **真实 LLM 未联调** | Mock 模式全覆盖，RealLLM 路径有单测但未做真实 API 冒烟 | 演示切真实模式前需验证 |

### P2 — 锦上添花

| 问题 | 现状 | 影响 |
|:----|:----|:----|
| **ECharts 走 CDN** | 离线内网演示需下载到 interfaces/static/js/ 本地引用 | 断网演示图表不渲染（已确认延后到演示准备阶段） |
| **前端为 Jinja2 服务端渲染** | 无组件化/类型系统，企业前端团队维护成本高 | 前端框架升级方案设计中 |
| **无 API 版本化** | 路由无 `/v1/` 前缀 | 无法向后兼容 |
| **无 Rate Limiter / 国际化** | 单用户无限调用；UI 文本硬编码中文 | 企业安全控制与海外演示受限 |

### 已关闭的历史问题（原 P0，全部完成 ✅）

- ~~同步 I/O 阻塞~~ → 持久层/LLM/路由全异步化
- ~~MCP/A2A 协议缺失~~ → orchestration/agent_protocol.py 落地，四容器联调验证
- ~~测试覆盖不足~~ → 21 pytest 用例 + CI
- ~~记忆写入链路未贯通~~ → Supervisor 拆解前查询 + 完成后写回
- ~~无 Config 中心化~~ → core/config.py 统一加载 + 密钥外移
- ~~断链 import~~ → orchestration/runtimes/main 全链路修复，import 冒烟测试防复发
- ~~密钥硬编码~~ → config.yaml 全占位符（注：原泄露密钥需在平台侧吊销）

## 6. 已确定的改造约束（硬性条件）

1. **UI 风格**：白底/SaaS 浅色主题（禁止毛玻璃和黑底）
   - 日志区使用浅灰底 + 彩色左边条区分级别
   - 主色 `#6366f1` Indigo，成功 `#10b981`，危险 `#ef4444`
   - Inter 字体（正文）+ JetBrains Mono（日志），本地加载离线可用

2. **部署方式**：Docker-Compose 微服务化
   - 4 个容器：`supervisor` + `worker-analyst` + `worker-desensitize` + `worker-report`
   - 同一镜像，`SERVICE_TYPE` 环境变量区分角色
   - 代码卷挂载，修改后 `docker-compose restart` 生效

3. **离线 Mock 模式**：默认开启（`LLM_MOCK_MODE=true`）
   - 覆盖所有 LLM 调用场景：拆解/异常/脱敏/报告/记忆/通用
   - 零网络请求，毫秒级响应

4. **目录结构**：8 个顶层目录（core/runtimes/orchestration/memory/toolkit/infrastructure/interfaces/services），新增代码只允许落入既有目录 + 根级配置文件

5. **前端**：静态资源全部本地加载（离线演示硬约束）；后端 API 保持稳定，前端升级不得要求后端改接口
