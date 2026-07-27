# WorkflowAgent v2 — 企业工作流自动化 Agent

在 SearchAgent（搜索）和 RAGAgent（知识库问答）之后，
第三个 Agent 专注于 **多步骤任务自动化**，实现 ReAct 循环。

---

## 一、核心能力矩阵

| 维度 | SearchAgent | RAGAgent | WorkflowAgent (新) |
|------|-------------|----------|-------------------|
| 交互模式 | 一次性问答 | 多轮对话 | **任务循环** |
| 核心技术 | 搜索API | 向量检索+RAG | **ReAct循环** |
| 工具调用 | 1 个工具(搜索) | 0 个工具 | **N 个工具编排** |
| 状态管理 | 无 | 对话历史 | **持久化状态机** |
| 执行方式 | 同步 | 同步 | **异步 + 超时控制** |
| 人工介入 | 无 | 无 | **审批节点** |
| 安全隔离 | 无 | 无 | **沙箱执行** |
| 断点恢复 | 无 | 无 | **Checkpoint 恢复** |

---

## 二、ReAct 循环实现（带动态重规划）

```
用户: "帮我整理销售报告，分析Q4数据，生成图表并发送邮件"

Agent 循环:
┌─────────────────────────────────────────────────┐
│  1. 思考 (Think): 制定初始计划                   │
│     输出: [step1, step2, step3, ...]             │
├─────────────────────────────────────────────────┤
│  2. 执行 (Act): step1 → read_file("sales.csv")  │
│  3. 观察 (Observe): 获取 500 行数据               │
│  4. 评估 (Evaluate): step1 成功，step2 可行？    │
│     ├─ ✅ 可行 → 继续执行 step2                  │
│     └─ ❌ 不可行 → 回 PLANNING 重新规划           │
├─────────────────────────────────────────────────┤
│  5. 执行 (Act): step2 → run_python(分析脚本)     │
│  6. 观察 (Observe): 报表生成成功                   │
│  7. 请求审批 (Approval): "是否发送邮件？"         │
│     ├─ ✅ 批准 → 继续                            │
│     └─ ❌ 拒绝 → 任务终止                        │
├─────────────────────────────────────────────────┤
│  8. 执行 (Act): step3 → send_email(...)          │
│  9. 完成 ✅                                      │
└─────────────────────────────────────────────────┘
```

**关键改进（v2）：**
- 每次 Act 后都 Evaluate，失败时**动态重规划**，而非按死板计划执行
- Evaluate 结果写入任务上下文，作为下一轮 Planning 的输入

---

## 三、状态机（网状结构，支持并行/条件/循环）

```
                    ┌──────────────────┐
                    │     PENDING      │ ← 任务创建，待开始
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
              ┌────│ 💡 PLANNING       │ ← LLM 生成计划（多个步骤）
              │    └────────┬─────────┘
              │             │
              │    ┌────────▼─────────┐
              │    │  AWAITING_APPROVAL│ ← 需要人工审批
              │    └────────┬─────────┘
              │             │ ✅ 批准 / ❌ 拒绝 → FAILED
              │             │
              │    ┌────────▼─────────┐
              │    │  ▶️ EXECUTING    │ ← 执行当前步骤
              │    └────────┬─────────┘
              │             │
              │    ┌────────▼─────────┐
              │    │  🔍 OBSERVING    │ ← 收集执行结果
              │    └────────┬─────────┘
              │             │
              │    ┌────────▼─────────┐
              │    │  📐 EVALUATING   │ ← 判断结果 + 是否可继续
              │    └────┬──────┬─────┘
              │     成功 ↓      ↓ 失败
              │         │    ╔══════════════╗
              │         │    ║  DYNAMIC     ║
              │         │    ║  REPLANNING  ║ ← 重新规划
              │         │    ╚══════╤═══════╝
              │         │          │
              │    还有步骤↓  ══════╝
              │         │
              └─────────┘
                        ↓
              ┌──────────────────┐
              │     ✅ DONE      │ ← 任务完成
              └──────────────────┘

新增状态：
├── AWAITING_APPROVAL  — 等待人工审批
├── DYNAMIC_REPLANNING — 执行失败后重新规划
├── CANCELLED          — 用户手动取消
├── TIMEOUT            — 超过时间限制
└── FAILED             — 不可恢复的错误
```

**支持的工作流模式：**

```
顺序链式:  step1 → step2 → step3        ✅ 基础模式
条件分支:  if A then stepB else stepC   ✅ Evaluate 实现
循环:      for each item → do X         ✅ 子任务循环
并行:      step2a ∥ step2b → merge     ✅ 子工作流
嵌套:      主任务 → 子工作流 → 合并     ✅ 递归子任务
```

---

## 四、安全沙箱设计

```
┌─ Sandbox ─────────────────────────────────────┐
│                                                │
│  WorkflowAgent 运行环境                         │
│  ┌────────────────────────────────────────┐    │
│  │  工作区: /tmp/agent_workspace/<task_id>/ │    │
│  │  ├── input/      ← 只读输入文件          │    │
│  │  ├── output/     ← 可写输出目录          │    │
│  │  └── temp/       ← 临时文件（自动清理）   │    │
│  └────────────────────────────────────────┘    │
│                                                │
│  安全规则:                                      │
│  ├── run_python(): 在 subprocess 中执行        │
│  │   ├── 限制 CPU 时间（默认 30s）              │
│  │   ├── 限制内存（默认 512MB）                 │
│  │   ├── 无网络访问（默认）                     │
│  │   └── 仅能读写工作区目录                     │
│  ├── run_shell(): 同上 + 命令白名单             │
│  │   └── 白名单: ls, cat, cp, mv, grep, find   │
│  ├── read_file(): 仅限工作区 + 项目目录          │
│  └── write_file(): 仅限工作区                   │
│                                                │
└────────────────────────────────────────────────┘

隔离级别（配置可选）:
├── LEVEL_0: 无隔离（开发调试用）
├── LEVEL_1: 目录隔离（默认 → 限制文件操作范围）
└── LEVEL_2: 进程隔离（subprocess + 资源限制）
```

---

## 五、任务持久化与恢复

### 存储结构

```python
TaskRecord {
    id: str                    # UUID
    user_id: str               # 归属用户
    prompt: str                # 原始任务描述
    status: str                # 状态机当前状态
    plan: list[Step]           # 执行计划
    current_step: int          # 当前步骤索引
    history: ChatHistory       # 完整 Think-Act-Observe 日志
    result: dict               # 最终结果
    created_at: datetime
    updated_at: datetime
    timeout_at: datetime       # 超时时间
}

Step {
    index: int
    action: str                # 工具名称
    params: dict               # 工具参数
    expected: str              # 预期结果描述
    status: str                # pending/running/done/failed
    result: str                # 执行结果
    approval_required: bool    # 是否需要审批
}
```

### 存储位置

| 数据 | 位置 | 说明 |
|------|------|------|
| TaskRecord | SQLite `data/workflow_tasks.db` | 任务元数据 + 状态 |
| 工作区文件 | `data/workflows/<task_id>/` | 输入输出文件 |
| Checkpoint | `data/workflows/checkpoints/` | 断点恢复用 |
| 审批记录 | SQLite `workflow_tasks.db` | 审批日志 |

### 恢复流程

```
Agent 重启 → 扫描 PENDING/EXECUTING 状态的任务
           → 检查是否超时（TIMEOUT）
           → 未超时 → 从 Checkpoint 恢复
           → 恢复执行 → 通知用户任务已恢复
```

---

## 六、超时与取消机制

```
┌─ 超时控制 ─────────────────────────────────────┐
│                                                  │
│  任务级别超时:  configurable (默认 5 分钟)        │
│  步骤级别超时:  每个 Act 最多 30 秒               │
│  LLM 调用超时:  每次 Planning 最多 15 秒          │
│  审批等待超时:  用户 24 小时未审批 → 自动取消      │
│                                                  │
└──────────────────────────────────────────────────┘

┌─ 取消机制 ──────────────────────────────────────┐
│                                                  │
│  用户取消途径:                                      │
│  ├── Web UI 的 "取消任务" 按钮                     │
│  ├── API: POST /workflow/<id>/cancel              │
│  └── CLI: workflow cancel <id>                   │
│                                                  │
│  取消后行为:                                        │
│  ├── 终止当前执行的步骤                             │
│  ├── 清理临时文件                                  │
│  ├── 状态标记为 CANCELLED                          │
│  └── 通知用户任务已取消                             │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

## 七、工具集设计（安全版）

```
WorkflowAgent 工具库:
├── 📂 文件操作（安全受限）
│   ├── read_file(path)          → 仅限工作区+项目目录
│   ├── write_file(path, text)   → 仅限工作区 output/
│   ├── edit_file(path, old,new) → 仅限工作区
│   └── list_dir(path)           → 仅限工作区+项目目录
├── ⚙️  代码执行（沙箱隔离）
│   ├── run_python(code, timeout=30) → subprocess + 资源限制
│   └── run_shell(cmd, timeout=15)   → 命令白名单
├── 🌐 网络工具（复用 SearchAgent）
│   ├── web_search(query)         → 搜索
│   └── web_fetch(url)            → 抓取网页
├── 📊 数据分析
│   └── analyze_data(description) → 用 LLM 分析数据
├── 🔒 审批节点
│   └── request_approval(reason)  → 等待用户确认
└── ⏰ 任务控制
    ├── wait(seconds)             → 等待
    └── cancel(reason)            → 终止任务
```

---

## 八、与现有基础设施的集成

| 现有模块 | WorkflowAgent 中的应用 |
|---------|----------------------|
| `ChatHistory` | 保存完整 ReAct 日志 |
| `CircuitBreaker` | 保护工具调用（连续失败→熔断） |
| `CostTracker` | 追踪 LLM 调用成本 |
| `TraceRecorder` | Think-Act-Observe 全链路追踪 |
| `ApprovalHandler` | 审批节点逻辑 |
| `Notepad/Todo` | 记录任务进度 |
| `ContextCompressor` | 长任务时压缩 ReAct 历史 |
| `MetricsTracker` | 任务成功率/耗时/取消率 |
| `PromptBuilder` | 动态组装 ReAct 提示词 |
| `Checkpoint` | **任务断点持久化与恢复** |

---

## 九、开发计划

| 阶段 | 内容 | 文件 | 代码量 |
|:----:|------|------|:------:|
| 1 | 数据结构 + 状态机 | `workflow/models.py` | ~80 行 |
| 2 | 沙箱执行器 | `workflow/sandbox.py` | ~120 行 |
| 3 | ReAct 引擎 | `workflow/engine.py` | ~250 行 |
| 4 | 工具集 | `workflow/tools.py` | ~180 行 |
| 5 | WorkflowAgent 主类 | `agents/workflow_agent.py` | ~200 行 |
| 6 | Web UI + 审批页面 | `web/templates/workflow.html` | ~150 行 |
| 7 | 集成测试 | `tests_workflow.py` | ~100 行 |
| **总计** | | | **~1080 行** |

---

## 十、对比：v1 vs v2 改进

| 维度 | v1 问题 | v2 改进 |
|------|---------|---------|
| 规划 | 一次性生成计划，无调整 | **动态重规划** — 步骤失败→回 PLANNING |
| 状态机 | 线性顺序 | **网状结构** — 支持并行/条件/循环/嵌套子任务 |
| 安全 | 无环境隔离 | **三级沙箱** — 目录隔离+进程隔离+资源限制 |
| 持久化 | 未说明 | **SQLite + Checkpoint** — 断点恢复+重启恢复 |
| 超时/取消 | 缺失 | **任务/步骤/审批 三级超时 + 取消 API** |
