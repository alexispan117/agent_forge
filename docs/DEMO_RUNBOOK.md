# AgentForge 路演操作手册（30 分钟版）

> 适用对象：演示主讲人 ｜ 版本：2026-07-18（经三轮真实彩排校准）
> 彩排验证环境：Windows 本地四进程 / Docker Compose 四容器，两种均适用

---

## 0. 演示前检查单（开场前 10 分钟）

| # | 检查项 | 命令 / 操作 | 通过标准 |
|---|--------|------------|---------|
| 1 | 四服务健康 | `curl localhost:8000/health`（8001/8002/8003 同） | 全部返回 `{"status":"ok"}` |
| 2 | 新总控台 | 浏览器打开 `http://localhost:8000/console` | 三栏 Dashboard 渲染，左侧导航健康灯绿 |
| 3 | 旧总控台 | 浏览器开新标签 `http://localhost:8000/orchestrator` | 页面 200（备用对照） |
| 4 | 服务拓扑 | 新总控台左栏「服务拓扑」 | 三个 Worker 全绿灯 |
| 5 | SSE 连接 | 新总控台侧边栏底部 | 「⚡SSE」灯亮 |
| 6 | Mock 模式 | `echo $LLM_MOCK_MODE` 或 .env | `true`（断网演示的关键） |

**启动方式（二选一）：**
```bash
# Docker（推荐，最接近客户环境）
docker-compose up -d        # 或 ./scripts/demo.sh 一键完成
# 本地四进程（无 Docker 的应急方案）
export LLM_MOCK_MODE=true
.venv/Scripts/python.exe services/worker_analyst/main.py &     # :8001
.venv/Scripts/python.exe services/worker_desensitize/main.py & # :8002
.venv/Scripts/python.exe services/worker_report/main.py &      # :8003
.venv/Scripts/python.exe services/supervisor/main.py &         # :8000
```

---

## 1. 时间轴总览

| 时间 | 环节 | 观众看到的 | 你要说的 |
|------|------|-----------|---------|
| 0:00–0:05 | 架构概览 | docker-compose 拓扑 / 设计文档 | 四节点微服务、MCP/A2A 开放协议 |
| 0:05–0:12 | **建任务 → 拆解 → 并行执行** | DAG 逐节点点亮 | 异步编排、真并行、记忆唤醒 |
| 0:12–0:18 | **故障注入 → 自愈降级** | 节点变黄、日志红色告警 | 熔断降级不是崩溃，CLEAR 如实扣分 |
| 0:18–0:22 | **CLEAR 评分解读** | 雷达图 + 指标卡变化 | 五维量化、每一分都有数据来源 |
| 0:22–0:25 | 服务发现 + Q&A | /services 页 AgentCard | 开放互联，可嵌套进更大编排体系 |
| 0:25–0:30 | 商业价值总结 | 恢复后满分对照 | 成本/效率/安全可量化 |

---

## 2. 环节一：建任务 → 拆解 → 执行（0:05–0:12）

### 操作
1. 新总控台左栏「新建任务」输入框粘贴：
   ```
   审计 data/demo/contracts 目录下所有供应商合同的合规性
   ```
2. 点「开始执行」→ 中栏出现 DAG 任务树（5–6 个节点）

### 观众看到的（彩排实测）
- 任务按依赖层级展开：T1 无依赖先跑，T2/T3 链路依次点亮，**同层节点同时变蓝**（真并行的视觉证据）
- 节点依次 蓝（运行，脉冲动画）→ 绿（完成）
- 右栏日志流逐条滚动：`工作流创建 → T1 开始 → T1 完成 → ...`
- 若历史演示过，会先出现一条 `memory_recall` 日志——**记忆唤醒**（上次经验注入本次拆解）

### 讲解要点
- "拆解由 LLM 完成，输出 DAG 而非线性列表——同层任务 asyncio.gather 真并行"
- "每个任务通过 MCP 协议远程调用对应 Worker，不是本地函数调用"
- （点开任意绿节点抽屉）"每个节点的 result、耗时、重试次数全留痕"

### 彩排数据（健康跑）
```
CLEAR: cost=52~60, latency=73, efficacy=100, assurance=100, reliability=100
任务:  5~6 个全部 done（analyst/desensitize/report 远程，supervisor 本地编排）
```

---

## 3. 环节二：故障注入 → 自愈降级（0:12–0:18）★ 高潮环节

### 方式 A：杀 Worker（推荐，视觉冲击最强）

**操作**（先再提交一次相同任务，任务运行中执行）：
```bash
docker stop agentforge-worker-analyst-1      # Docker 方式
# 本地进程方式：taskkill //PID <8001端口PID> //F
```

**观众看到的（彩排实测）**：
- 新总控台左栏服务拓扑：analyst 灯 **绿→灰（离线）**
- analyst 类型任务节点 **蓝→黄（降级）**，不是红色失败
- 日志流出现橙色告警：`Worker analyst 远程调用失败，降级本地执行`
- 工作流**依然跑完**，CLEAR reliability 从 100 如实掉到 **20**（4/5 任务降级）

**讲解要点**：
- "远程调用失败经过 指数退避重试 → 熔断 → 本地降级 三级防线，业务不中断"
- "降级不是掩盖故障——雷达图 reliability 如实扣分，这就是可观测性的意义"

### 方式 B：页面内故障注入按钮（演示单任务级故障）

**操作**：任务运行中点「⚡故障注入」→ 一个 pending/running 任务被标记失败（红色）

**观众看到的**：该节点变红、下游依赖它的节点显示「依赖无法满足」（死锁检测）、assurance 维度扣分

**注意**：此按钮演示的是**任务级**故障与死锁检测；方式 A 演示的是**服务级**故障与降级自愈。建议两个都演示，先 A 后 B。

### 恢复（必做，收尾对比）
```bash
docker start agentforge-worker-analyst-1
```
再提交一次任务 → **reliability 回到 100**（彩排实测恢复后 CLEAR 满分复原）

**台词**："从宕机到恢复，系统不需要重启、不需要人工干预任务流——这就是生产级韧性。"

---

## 4. 环节三：CLEAR 评分解读（0:18–0:22）

对着雷达图逐维度讲（用健康跑 vs 故障跑的真实对照数据）：

| 维度 | 健康跑 | analyst 宕机 | 业务含义 |
|------|--------|-------------|---------|
| **C**ost 成本 | 52–60 | 60 | 任务越多 LLM 调用成本越高 |
| **L**atency 延迟 | 73 | **33** | 宕机后重试+降级显著拖慢 |
| **E**fficacy 效能 | 100 | 100 | 降级算完成，业务目标达成率 |
| **A**ssurance 保证 | 100 | 100 | 无彻底失败任务 |
| **R**eliability 可靠性 | 100 | **20** | 无故障完成率——最敏感的指标 |

**台词**："注意 efficacy 和 reliability 的区别——业务做完了（100），但 80% 的任务是靠降级兜底做完的（20）。前者回答'能不能用'，后者回答'健不健康'。"

---

## 5. 环节四：服务发现与开放协议（0:22–0:25）

**操作**：点侧边栏「服务」页

**观众看到的**：三张 AgentCard——名称、端点、能力徽章、工具清单（可展开 input_schema）

**讲解要点**：
- "每个 Agent 通过 `/.well-known/agent.json` 自我描述（A2A），通过 `/mcp` JSON-RPC 提供工具（MCP）——Supervisor 零硬编码发现并调用它们"
- "Supervisor 自己也发布 AgentCard，意味着它可以作为 Worker 嵌套进更大的编排体系"
- （如观众有技术背景）现场 `curl localhost:8001/.well-known/agent.json` 展示原始 JSON

---

## 6. 应急预案（演示出问题时）

| 症状 | 原因 | 处置 |
|------|------|------|
| 新总控台白屏 | SPA 产物缺失 | 改用旧总控台 `/orchestrator` 继续演示；事后 `cd interfaces/web && npm run build` |
| 任务一直 running 不完 | Worker 全部离线且降级超时 | 等待 ≤60s（重试耗尽会自动降级完成）；或直接讲降级机制 |
| 服务拓扑全灰 | Worker 没起来 | 转为「降级模式演示」："大家看，即使三个 Worker 全挂了，系统依然能交付" |
| SSE 断连（侧边栏黄灯） | 网络抖动 | 3 秒内自动重连；页面有轮询兜底，数据不丢 |
| 端口被占用 | 上次演示进程未关 | `netstat -ano \| grep :8000` 找 PID 后 taskkill |
| 完全断网 | 场地网络故障 | **不受影响**——Mock 模式零网络请求，这正是设计目的，可直接说"我们现在就是离线运行" |

---

## 7. 演示后收尾

```bash
docker-compose down          # 或本地：taskkill 四个端口进程
```

确认端口释放：8000/8001/8002/8003 均无 LISTENING。

---

## 附：彩排原始记录（2026-07-18，三次真实运行）

```
[健康跑]   CLEAR {cost:52, latency:73, efficacy:100, assurance:100, reliability:100}
           6 任务全部 done，无降级日志
[故障跑]   analyst 杀死后 CLEAR {cost:60, latency:33, efficacy:100, assurance:100, reliability:20}
           T1–T4 analyst 全 degraded（黄），T5 report done，工作流仍 completed
[恢复跑]   analyst 重启后 CLEAR reliability 回到 100
[按钮注入] 提交后 0.3s 注入 → T1 failed「[故障注入] 模拟 Worker 宕机」，
           下游死锁检测生效，assurance 扣分
```

> 彩排中修复的问题：Mock 拆解模板中 `agent: "supervisor"` 的审批任务此前被误判为
> 「未配置 Worker → 降级」，导致健康跑 reliability 最高只有 83。已改为本地编排任务
> 正常执行（属设计内行为，不算降级），健康跑现在稳定满分。
