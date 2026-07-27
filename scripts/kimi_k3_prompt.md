# Kimi K3 终极优化提示词（更新版 — 基于当前真实项目状态）

> 使用前：将 PROJECT_CONTEXT_FOR_AI_OPTIMIZATION.md 的内容粘贴到下方「### 项目现状文件」位置

---

**【角色设定】**
你现在是全球顶尖的 AI Agent 系统架构师，精通 Harness Engineering、多智能体协作（MCP/A2A）、上下文工程与 CLEAR 评估体系。你曾主导过多个从 0 到 1 的企业级 Agent 平台落地。

**【核心任务】**
我将为你提供一份名为 `PROJECT_CONTEXT_FOR_AI_OPTIMIZATION.md` 的项目现状说明书。**请注意：该项目已经完成了大量的前期改造（目录重构、Supervisor 编排、@with_fallback、MockLLM、Docker-Compose 多容器、CLEAR 评估、白底仪表盘）。** 你的任务是：
1. **严格审查已做工作**，指出每一处可以优化的细节
2. **聚焦尚未完成的 P0/P1 差距**（见第 5 章），给出具体改造方案
3. **输出可落地的代码修改要点**，而非泛泛的概念论述

**【改造铁律】**
在你的分析和代码输出中，请遵循以下原则：
1. **Harness 工程**：当前 @with_fallback 是否足够？是否需要更完整的生命周期 Hook？
2. **异步化**：当前所有 I/O 仍是同步 blocking（SQLAlchemy sync session、LLM 调用），分析影响并给出改造路径
3. **MCP/A2A 协议**：当前 Worker 间通过 HTTP REST 硬编码通信，设计标准化协议接口层
4. **分层记忆贯通**：ShortTermMemory/EpisodicMemory 类已就位，但写入链路未串通——给出完整链路方案
5. **测试覆盖**：只有 30 个测试用例，给出测试策略和关键测试用例
6. **所有代码路径必须严格基于 PROJECT_CONTEXT_FOR_AI_OPTIMIZATION.md 中的目录树，严禁编造不存在的文件路径**

**【输出要求】**
请按以下结构分步输出：

### 第一步（诊断）
基于「第 5 章 待优化差距」和你的专业判断，指出：
- 当前代码中 **最严重的架构问题** 及其影响范围
- 已做工作中 **可以进一步优化的细节**（如 @with_fallback 的降级策略是否完备、Supervisor 的容错边界等）

### 第二步（全量文件修改清单）
输出一个表格，列出 **每个需要修改的文件** 及其修改要点：

| 文件路径 | 修改类型 | 修改要点 |
|:---------|:--------|:---------|
| interfaces/app.py | 增强 | 添加 ... |
| orchestration/react_engine.py | 重构 | 将 ... 改为 ... |
| ... | ... | ... |

每行给出 1-2 句具体修改说明，不要空白。

### 第三步（核心代码示例）
选取 **2 个最关键的文件**，给出可直接运行的完整代码：
1. 一个涉及异步化改造的关键文件
2. 一个涉及 MCP/A2A 协议接口的文件

代码中必须包含完整的 import 链、类型注解、错误处理。

### 第四步（实施路线图）
按以下优先级给出改造时间线：
- **P0（路演前必须完成）**：影响演示核心亮点的修复
- **P1（建议完成）**：提升工程完整性
- **P2（可延后）**：提升产品质感

每项标注预计工时（人天）。

---

### 项目现状文件

将 PROJECT_CONTEXT_FOR_AI_OPTIMIZATION.md 的内容粘贴在这里
# AgentForge — 项目上下文说明书（供 AI 优化使用）

> 生成日期: 2026-07-18
> 用途: 为 Kimi K3 提供精确的项目状态地图，作为企业级重构的诊断依据

---

## 1. 项目终极目标

打造面向金融/制造/政务企业的商业化 AI Agent 演示产品，通过 30 分钟深度路演向企业 CTO 证明：
1. 产品具备生产级工程能力（非玩具Demo）
2. 个人具备全栈架构设计能力
3. 可量化商业价值（成本/效率/安全）

## 2. 当前目录树与职责（已重构后的真实状态）

```
agent_forge/
│
├── core/                          # 内核层：共享库，不独立运行
│   ├── llm_factory.py             # 统一 LLM 工厂（MockLLM + RealLLM 切换）
│   ├── with_fallback.py           # @with_fallback 故障自愈装饰器 + 降级策略池
│   └── mock_responses/            # 6 个 Mock 响应模板（decompose/anomaly/desensitize/report/memory/general）
│
├── runtimes/                      # 运行时业务逻辑（原 agents/）
│   ├── base_runtime.py            # BaseRuntime 基类（原 BaseAgent）
│   ├── searcher.py                # Searcher 搜索服务（原 SearchAgent）
│   ├── knowledge_bot.py           # KnowledgeBot 知识问答（原 RAGAgent）
│   └── orchestrator_runtime.py    # OrchestratorRuntime 工作流（原 WorkflowAgent）
│
├── orchestration/                 # 编排层（原 workflow/ + evaluation/）
│   ├── react_engine.py            # ReAct 引擎（状态机 + DAG 并行 + 自动重试）
│   ├── supervisor.py              # Supervisor 编排器（LangGraph 驱动）
│   ├── state_models.py            # SQLite 状态模型
│   ├── sandbox.py                 # 子进程沙箱隔离
│   ├── tool_schema.py             # 工具 Schema 约束
│   ├── tools.py                   # 工具实现（list_dir/read_file/run_python...）
│   └── assessors/
│       └── clear_scorer.py        # CLEAR 五维评分器（原 MetricsTracker）
│
├── memory/                        # 记忆层（原 context/ + prompts/）
│   ├── short_term.py              # 短期记忆（原 ChatHistory）
│   ├── episodic.py                # 情景记忆（原 LongTermMemory）
│   ├── context_compressor.py      # 上下文压缩
│   ├── prompt_builder.py          # Prompt 构建器
│   ├── embedding_config.py        # Embedding 配置
│   ├── reranker.py                # 重排序器
│   ├── workspace.py               # 工作区管理
│   └── prompts/
│       ├── knowledge_prompt.py    # 知识问答 Prompt（原 rag_prompt.py）
│       └── search_prompt.py       # 搜索 Prompt
│
├── toolkit/                       # 工具包（原 tools/）
│   ├── registry.py                # 工具注册中心
│   ├── vector_store.py            # ChromaDB 向量存储
│   ├── embeddings.py              # Embedding API 封装
│   ├── browser_tool.py            # 浏览器工具
│   ├── cache.py                   # 搜索缓存
│   └── langchain_adapter.py       # LangChain 适配器
│
├── infrastructure/                # 基础设施（原 infra/ + db/）
│   ├── circuit_breaker.py         # 熔断器
│   ├── approval.py                # 审批处理器
│   ├── cost_tracker.py            # 成本追踪
│   ├── logging.py                 # 日志
│   └── persistence/               # 数据持久化（原 db/）
│       ├── database.py            # SQLite/MySQL 连接
│       ├── orm_models.py          # ORM 模型
│       └── crud.py                # CRUD 操作
│
├── interfaces/                    # 接口层（原 web/）
│   ├── app.py                     # FastAPI 主应用（含 SSE 端点 /stream）
│   ├── auth.py                    # 认证模块
│   ├── feedback.py                # 用户反馈
│   ├── templates.py               # Jinja2 模板引擎
│   ├── routes/agent.py            # Agent 路由
│   ├── static/
│   │   ├── css/dashboard.css      # 白底 SaaS Design Tokens + 三栏 Grid
│   │   ├── js/dashboard.js        # decodeText 动效 + CLEAR 雷达图
│   │   └── fonts/                 # Inter + JetBrains Mono（本地加载）
│   └── templates/
│       ├── base.html              # 基础布局（含 head_extra block）
│       ├── orchestrator.html      # 总控台（三栏 + SSE + ECharts）
│       ├── workflow.html          # 工作流子页
│       ├── chat.html              # 智能问答子页
│       └── ... (index, login, register, dashboard, result, agent_info, auth_base, error)
│
├── services/                      # 微服务入口（可独立启动的进程）
│   ├── supervisor/main.py         # Supervior 总控节点（端口 8000）
│   ├── worker_analyst/main.py     # 分析 Worker（端口 8001）
│   ├── worker_desensitize/main.py # 脱敏 Worker（端口 8002，含 5 条内置脱敏规则）
│   └── worker_report/main.py     # 报告 Worker（端口 8003，含 CLEAR 评分）
│
├── data/
│   ├── demo/
│   │   ├── contracts/             # 5 份脱敏演示合同
│   │   ├── audit_rules.json       # 7 条审计规则
│   │   └── seed_memory.json       # 情景记忆种子
│   ├── app.db                     # 用户/会话
│   ├── workflow.db                # 工作流 SQLite
│   └── workflow_outputs/          # 沙箱输出持久化
│
├── docs/                          # 知识库文档（8 份上市公司年报）
│
├── scripts/
│   ├── demo.sh                    # 一键启动脚本
│   ├── rename_map.json            # 重命名映射表
│   └── rename_to_enterprise.py    # 企业级重命名脚本
│
├── config.yaml                    # 全局配置
├── Dockerfile                     # 通用镜像（多服务共用）
├── docker-compose.yml             # 5 容器编排（supervisor + 3 workers + redis）
├── requirements.txt               # 依赖（含 langgraph, redis, sse-starlette）
├── .env.example                   # 环境变量模板（LLM_MOCK_MODE 默认 true）
└── main.py                        # 入口脚本

## 3. 核心技术栈

| 类别 | 技术 | 版本/备注 |
|:----|:----|:---------|
| 语言 | Python 3.11 | |
| Web 框架 | FastAPI | SSE 流式推送 |
| 模板引擎 | Jinja2 | 白底 SaaS 风格 |
| 编排框架 | LangGraph | Supervisor 节点 |
| 数据库 | SQLite | WAL 模式支持并发 |
| 向量数据库 | ChromaDB | 知识库检索 |
| LLM API | DeepSeek / OpenAI 兼容 | MockLLM 模式默认 |
| Embedding | 阿里百炼 DashScope | text-embedding-v3 |
| 图表 | ECharts 5 (CDN) | 雷达图 + 树图 |
| 容器化 | Docker / Docker-Compose | 5 容器 |
| 消息 | Redis | 事件总线 |
| ORM | SQLAlchemy (sync) | **⚠️ 同步，未异步化** |

## 4. 现有功能模块（已具备 ✅）

### 4.1 三个运行时
- **Searcher**（搜索服务）：百度/DDG 双引擎 + 缓存 + AI 摘要
- **KnowledgeBot**（知识问答）：ChromaDB + 混合检索 + RRF + 熔断器 + 优雅降级
- **OrchestratorRuntime**（工作流编排）：ReAct 循环 + DAG 并行 + 子进程沙箱 + 自动重试

### 4.2 编排与评估
- **Supervisor**（监督者）：LangGraph 驱动的任务拆解 + Worker 调度 + 故障注入
- **CLEAR Scorer**：五维评分（成本/延迟/效能/保证/可靠性），ECharts 雷达图展示
- **@with_fallback**：装饰器 + 降级策略池 + 注册表

### 4.3 部署与演示
- **Docker-Compose 多容器**：Supervisor + 3 Workers + Redis，24 小时健康检查
- **离线 Mock 模式**：LLM_MOCK_MODE=true，7 个 JSON 响应模板
- **demo.sh 一键启动**：构建 → 预热 → 健康检查 → 打开浏览器
- **5 份演示合同 + 7 条审计规则 + 情景记忆种子**

### 4.4 接口层
- **SSE 实时推送**：/stream 端点 + EventSource 客户端
- **Orchestrator Dashboard**：三栏 Grid + Inter 字体 + 浅色日志左边条 + 解码动效
- **响应式布局**：3 级断点（1400/1024/900px）

### 4.5 已完成的企业级重命名
- `agents/` → `runtimes/`，`SearchAgent` → `Searcher`，`RAGAgent` → `KnowledgeBot`
- `workflow/` → `orchestration/`，`web/` → `interfaces/`，`db/` → `infrastructure/persistence/`
- 类名全部更新（8 个类映射），import 链全部同步

## 5. 与行业顶级标准的差距（待优化 ❌）

### P0 — 架构缺陷（必须修复）

| 问题 | 现状 | 影响 |
|:----|:----|:----|
| **同步 I/O 阻塞** | 所有数据库操作（SQLAlchemy sync session）、LLM 调用、文件操作均为同步 blocking | FastAPI 异步框架优势未发挥，高并发下阻塞事件循环 |
| **MCP/A2A 协议缺失** | Worker 间通过 HTTP REST 硬编码通信，无标准化协议层 | 无法对接外部 Agent 生态，演示中无法展示"开放互联" |
| **测试覆盖不足** | 只有 `tests.py`（约 30 个测试用例），无单元测试/集成测试/CI | 无法证明工程可靠性，企业客户会质疑质量 |

### P1 — 功能完整性（演示亮点）

| 问题 | 现状 | 影响 |
|:----|:----|:----|
| **记忆写入链路未贯通** | ShortTermMemory/EpisodicMemory 类已重命名，但 Supervisor 执行过程中的记忆读取/写入没有完整串通 | 演示中无法展示"Agent 记忆"亮点 |
| **无 Config 中心化** | config.yaml 混合了 LLM/DB/Embedding 配置，无环境变量模板抽取，无加密密钥管理 | 部署到客户环境时配置管理混乱 |
| **无指标采集管道** | 只有内存中的 MetricsTracker，无 Prometheus 暴露端点，无时序数据持久化 | 无法展示长期运行趋势图 |

### P2 — 锦上添花

| 问题 | 现状 | 影响 |
|:----|:----|:----|
| **前端无国际化** | 所有 UI 文本硬编码中文 | 海外客户演示受限 |
| **无 API 版本化** | 路由无 `/v1/` 前缀 | 无法向后兼容 |
| **无 Rate Limiter** | 单个用户可以无限调用 | 演示中无法展示"企业安全控制" |

## 6. 已确定的改造约束（硬性条件）

1. **UI 风格**：白底/SaaS 浅色主题（禁止毛玻璃和黑底）
   - 日志区使用浅灰底 + 彩色左边条区分级别
   - 主色 `#6366f1` Indigo，成功 `#10b981`，危险 `#ef4444`
   - Inter 字体（正文）+ JetBrains Mono（日志），本地加载离线可用

2. **部署方式**：Docker-Compose 微服务化
   - 5 个容器：`supervisor` + `worker-analyst` + `worker-desensitize` + `worker-report` + `redis`
   - 同一镜像，`SERVICE_TYPE` 环境变量区分角色
   - 代码卷挂载，修改后 `docker-compose restart` 生效

3. **离线 Mock 模式**：默认开启（`LLM_MOCK_MODE=true`）
   - 覆盖所有 LLM 调用场景：拆解/异常/脱敏/报告/记忆/通用
   - 零网络请求，毫秒级响应

4. **目录结构**：已重构为 8 个顶层目录
   - `core/` `runtimes/` `orchestration/` `memory/` `toolkit/` `infrastructure/` `interfaces/` `services/`

5. **前端技术栈**：FastAPI + Jinja2 + SSE + ECharts（无 React/Vue）

## 7. requirements.txt 关键依赖

| 包名 | 用途 | 是否需要升级 |
|:----|:----|:-----------|
| fastapi | Web 框架 | 当前同步路由 |
| uvicorn | ASGI 服务器 | 已配置 |
| sqlalchemy | ORM | **⚠️ 同步，需 async** |
| pymysql | MySQL 驱动 | 兼容用 |
| chromadb | 向量数据库 | 使用中 |
| openai | LLM API 客户端 | DeepSeek 兼容 |
| langgraph | 编排框架 | 已集成 |
| langchain-core | LangChain 核心 | 适配器层 |
| sse-starlette | SSE 推送 | 已集成 |
| redis | 消息队列 | 已配置 |
| pyyaml | 配置解析 | 使用中 |
| jinja2 | 模板引擎 | 使用中 |
| python-docx | 文档生成 | 工具脚本用 |
| pillow | 图片处理 | 工具脚本用 |
| httpx | HTTP 客户端 | **可替代 requests 实现异步** |

---

**【追加约束】**
- 所有输出的文件路径必须与 `PROJECT_CONTEXT_FOR_AI_OPTIMIZATION.md` 中的目录树完全一致
- 不要建议已经完成的命名工作（如目录重命名）重新做
- 如果某项已做工作有优化空间，请明确指出具体改进点
