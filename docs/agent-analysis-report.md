# 现有 Agent 设计分析报告

基于 WorkflowAgent v2 的设计框架，回顾分析 SearchAgent 和 RAGAgent。

---

## 一、SearchAgent — 搜索网页并整理信息

### 1. 架构总览

```
SearchAgent
├── 接口: init(config) + execute(query, **kwargs) → dict
├── 引擎: Baidu AI 搜索 / DuckDuckGo（降级）
├── 缓存: 文件系统 JSON（tools/cache.py）
├── LLM: DeepSeek（用于 AI 摘要生成）
└── 追踪: TraceRecorder（记录搜索链路）
```

### 2. 设计评分

| 维度 | 评分 | 说明 |
|------|:----:|------|
| **ReAct 循环** | ❌ 无 | 一次搜索即结束，无 Think→Act→Observe 循环 |
| **状态机** | ❌ 无 | 无状态，每次调用独立 |
| **工具集** | ⭐ 1 个 | 仅 search（百度/DDG），无多样化工具 |
| **安全性** | ⚠️ 低 | 无沙箱，但搜索 API 本身风险低，可接受 |
| **持久化** | ⭐ 缓存 | 搜索结果文件缓存（5 分钟 TTL） |
| **超时控制** | ✅ 有 | requests.post(timeout=20) |
| **熔断降级** | ✅ 有 | Baidu 失败 → 自动降级 DuckDuckGo |
| **审批机制** | ❌ 无 | 搜索场景下可以接受 |
| **可观测性** | ⭐⭐ 基础 | TraceRecorder + logging |
| **成本追踪** | ⭐ | CostTracker 已集成 |
| **上下文工程** | ❌ 无 | 一次性查询，无需上下文 |

### 3. 适用场景

```
✅ 适合: 一次性信息检索、快速事实查询、AI 摘要生成
❌ 不适合: 多步骤任务、需要操作文件、需要跨页面综合分析
```

### 4. 与 WorkflowAgent 的协作方式

```
WorkflowAgent 执行 web_search() 时 → 调用 SearchAgent
SearchAgent 返回结构化结果 → WorkflowAgent 继续处理
```

---

## 二、RAGAgent — 智能问答客服

### 1. 架构总览

```
RAGAgent
├── 接口: init(config) + execute(query, **kwargs) → dict
├── 知识库: ChromaDB 向量库 + 关键词检索 (docs/)
├── 检索: 向量检索 / 混合检索(RRF) / 纯关键词(降级)
├── 重排序: rerank_by_hybrid() — 位置加权
├── 对话记忆: ChatHistory 类 (context/chat_history.py)
├── 长期记忆: LongTermMemory (SQLite 持久化)
├── 上下文工程: PromptBuilder + ContextCompressor + Notepad/Todo
├── 基础设施: CircuitBreaker + CostTracker + TraceRecorder + Checkpoint
├── 人工审批: ApprovalHandler
└── 评估: MetricsTracker
```

### 2. 设计评分

| 维度 | 评分 | 说明 |
|------|:----:|------|
| **ReAct 循环** | ❌ 无 | 检索→生成，无 Think→Observe 循环 |
| **状态机** | ❌ 无 | 仅有对话历史，无任务状态管理 |
| **工具集** | ⭐⭐ 内部丰富 | 向量库+关键词+重排序+LLM 等内部工具集合，但对外仅 execute() |
| **安全性** | ✅ 良好 | 知识库只读，LLM 输出有 System Prompt 约束 |
| **持久化** | ⭐⭐⭐ 全面 | 对话历史 DB 持久化 + Checkpoint 断点 + 长期记忆 |
| **超时控制** | ✅ 有 | LLM 调用超时 + 熔断器超时 |
| **熔断降级** | ✅ 完整 | API 失败→自动降级关键词检索 |
| **审批机制** | ✅ 已有 | ApprovalHandler 已集成，但当前未启用 |
| **可观测性** | ⭐⭐⭐ 完善 | TraceRecorder + logging + MetricsTracker |
| **成本追踪** | ✅ 完整 | CostTracker 记录每次 LLM 调用 |
| **上下文工程** | ⭐⭐⭐ 完善 | PromptBuilder + Compressor + ChatHistory + Notepad/Todo + LongTermMemory |

### 3. 深度模块分析

```
RAGAgent: 2 个公开方法 vs 15+ 内部子系统
┌──────────────────────────────────────┐
│  init(config)                         │  ← 2 方法
│  execute(query) → dict                │
├──────────────────────────────────────┤
│  ┌──────────┐  ┌────────────────┐     │
│  │ VectorStore │  │ ChatHistory    │     │  ← 深
│  │ (ChromaDB)  │  │ (类封装)       │     │
│  ├──────────┤  ├────────────────┤     │    模块
│  │ PromptBuilder│  │ ContextCompress│     │
│  ├──────────┤  ├────────────────┤     │
│  │ CircuitBreaker│  │ CostTracker    │     │
│  ├──────────┤  ├────────────────┤     │
│  │ LongTermMem  │  │ MetricsTracker │     │
│  ├──────────┤  ├────────────────┤     │
│  │ Approval     │  │ Checkpoint     │     │
│  └──────────┘  └────────────────┘     │
└──────────────────────────────────────┘
        深度评估: ⭐⭐⭐ 优秀
```

### 4. 适用场景

```
✅ 适合: 基于知识库的问答、多轮对话、投资咨询、客户服务
✅ 适合: 需要长期记忆和上下文压缩的复杂对话
✅ 适合: 需要评估指标和成本追踪的生产环境
❌ 不适合: 需要操作文件、执行代码、多步骤自动化
```

### 5. 与 WorkflowAgent 的协作方式

```
WorkflowAgent 执行知识问答时 → 调用 RAGAgent
RAGAgent 返回分析结果 → WorkflowAgent 整合到工作流
```

---

## 三、三个 Agent 的横向对比

| 维度 | SearchAgent | RAGAgent | WorkflowAgent (新) |
|------|:----------:|:--------:|:-----------------:|
| **交互模式** | 一次性查询 | 多轮对话 | **任务循环** |
| **工具数量** | 1 | 0（内部 5+） | **10+** |
| **ReAct 循环** | ❌ | ❌ | **✅ Think→Act→Observe** |
| **状态机** | ❌ | ❌ | **✅ 6 状态网状** |
| **上下文工程** | ❌ | ⭐⭐⭐ | **⭐⭐⭐** |
| **安全性** | ⚠️ | ✅ | **✅ 沙箱隔离** |
| **持久化** | ⭐ 缓存 | ⭐⭐⭐ | **⭐⭐⭐** |
| **熔断降级** | ✅ | ✅ | **✅** |
| **审批机制** | ❌ | ✅ 已有 | **✅ 核心** |
| **可观测性** | ⭐ | ⭐⭐⭐ | **⭐⭐⭐** |
| **代码量** | ~200 行 | ~420 行 | **~1080 行** |
| **复杂度** | 低 | 中 | **高** |

---

## 四、发现的可改进点

### SearchAgent 可改进

| 改进项 | 优先级 | 说明 |
|--------|:-----:|------|
| 搜索结果去重 | ⭐⭐ | 多个来源的结果可能有重复 |
| 搜索结果结构化 | ⭐⭐ | 支持分页、筛选、排序 |
| 搜索历史管理 | ⭐ | 保存搜索记录到 DB |
| 多引擎并行搜索 | ⭐ | Baidu + DDG 同时搜后合并 |

### RAGAgent 可改进

| 改进项 | 优先级 | 说明 |
|--------|:-----:|------|
| 启用 ApprovalHandler | ⭐⭐ | 敏感问题（如投资推荐）先审后答 |
| 多文档对话切换 | ⭐⭐ | 用户可以选择不同知识库范围 |
| 引用精确到段落 | ⭐ | 当前标注【文档 X】，可精确到章节 |
| 主动追问机制 | ⭐ | 信息不足时反问用户补充 |

---

## 五、总结

```
三个 Agent 覆盖了 AI Agent 三阶段能力:

SearchAgent  → "帮我查一下"     → 信息检索层
RAGAgent     → "帮我分析一下"   → 知识处理层
WorkflowAgent → "帮我去做"     → 任务执行层 ← 新

三者可组合使用:
┌──────────────────────────────────────────┐
│  WorkflowAgent (任务编排)                  │
│  ├── 调用 SearchAgent → 获取信息          │
│  ├── 调用 RAGAgent    → 分析信息          │
│  ├── 沙箱工具         → 处理文件/代码      │
│  └── 审批节点         → 等待用户确认       │
└──────────────────────────────────────────┘
```
