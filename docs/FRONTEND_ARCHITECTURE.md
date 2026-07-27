# AgentForge 前端架构设计文档

> 版本：v1（2026-07-18）｜实现位置：`interfaces/web/`（源码）→ `interfaces/static/spa/`（产物）
> 状态：已建成并验证（tsc 0 错误 / vite build 通过 / 真实后端联调 completed）

---

## 一、技术选型结论

**结论：引入 React 18 + Vite + TypeScript 独立前端工程，构建为纯静态产物后交 FastAPI 托管；Jinja2 模板保留服务旧页面，二者长期共存、渐进替换。**

判断依据：本项目要交付给「企业前端团队维护」，Jinja2 + 原生 JS 的组织方式没有组件边界、没有类型系统、没有状态管理，任务 DAG、SSE 实时流、抽屉交互这类有状态 UI 在模板里会迅速腐化为不可维护的 DOM 拼接——这正是 React 组件模型 + TS 契约 + 集中式状态解决的核心痛点。选型上排除了 Next.js（SSR 对内部监控工具无收益，反增部署复杂度）与 Vue（团队招聘面与生态均势，但 React 与 TS 的工具链对企业交付更稳）。Vite 负责构建与开发代理，产物为纯静态文件——**构建期联网一次，运行期零外网依赖**，离线演示硬约束通过「echarts/字体/框架全部 npm 本地化」满足，同时顺手关闭了 ECharts CDN 的 P2 遗留项。后端零接口改动：SPA 只是 `/api/*` 与 `/stream` 的又一个客户端。

## 二、页面布局方案

```
┌──────────────────────────────────────────────────────────────────────┐
│ ▸ AgentForge    总控台  历史  服务  配置              ● 后端正常  ⚡SSE │
│  (Sidebar 固定左侧，含 Logo/导航/底部健康灯 + SSE 连接状态)             │
├──────────────────────────────────────────────────────────────────────┤
│ 【总控台 / —— 三栏工作区】                                            │
│ ┌───────────────┬─────────────────────────────┬────────────────────┐ │
│ │ 📝 新建任务    │  🌊 任务执行流               │  📊 CLEAR 评估      │ │
│ │  [textarea]   │  ┌──┐                        │   ╭───────╮        │ │
│ │  [开始执行]    │  │T1│──┐                     │   │ 雷达图  │        │ │
│ │ ───────────  │  └──┘  │  ┌──┐  ┌──┐         │   ╰───────╯        │ │
│ │  wf: a3ee…  │  ┌──┐  ├─▶│T3│─▶│T5│         │  成本 延迟 效能      │ │
│ │  [⚡故障注入] │  │T2│──┘  └──┘  └──┘         │  保证 可靠性        │ │
│ │ ───────────  │  └──┘  状态色:               │ ────────────────  │ │
│ │ 🌐 服务拓扑    │  ⚪待执行 🔵运行(脉冲)        │  ▣ 任务 6  ▣ 成功 5 │ │
│ │  ● analyst   │  🟢完成  🔴失败  🟡降级        │  ▣ 降级 1  ▣ 失败 0 │ │
│ │  ● desensit. │ ─────────────────────────  │ ────────────────  │ │
│ │  ○ report    │  点击节点 → 右侧滑出详情抽屉   │  📜 实时日志        │ │
│ │  (绿灯在线/   │  (result/error/耗时/重试)    │  ▎14:32:01 工作流创建│ │
│ │   灰灯离线)   │                             │  ▎14:32:02 T1 开始  │ │
│ │  (骨架屏加载) │                             │  ▎14:32:05 T1 完成  │ │
│ └───────────────┴─────────────────────────────┴────────────────────┘ │
│ 【/history 历史】 localStorage 记录 wf_id → 列表（状态徽章/效能分/时间） │
│ 【/services 服务】 AgentCard 完整卡片：能力徽章 + 工具 input_schema 展开 │
│ 【/settings 配置】 SSE 开关 / 日志上限 / 轮询间隔（localStorage 持久化）  │
```

## 三、交互逻辑

| 场景 | 行为 |
|:----|:----|
| **点击 DAG 节点** | 右侧滑出详情抽屉：任务全名、agent 类型、状态徽章、完整 result（等宽字体）、error 全文（红）、开始/完成时间、耗时、重试次数；Esc 或点遮罩关闭 |
| **任务出错** | 节点红色高亮 + 边框加粗；日志流追加红色边条错误行；若导致下游死锁，被连坐任务显示「依赖无法满足」；CLEAR 的 assurance/reliability 如实扣分 |
| **降级执行** | 节点黄色「降级」徽章——Worker 宕机但 Supervisor 本地兜底，演示「故障自愈」叙事 |
| **加载状态** | 提交后按钮 loading 禁用；运行中状态条脉冲动画；服务拓扑骨架屏；历史列表逐条加载占位 |
| **SSE 断线** | EventSource onerror → 3s 自动重连，Sidebar 连接灯黄→绿；非终态工作流同时有轮询兜底（间隔可在配置页调） |
| **API 错误** | 统一 ApiError，兼容后端 `error`/`detail`/`message` 三种错误键；Toast 提示，轮询失败静默不轰炸 |
| **React 崩溃** | ErrorBoundary 捕获 → 中文错误页 + 重试按钮，不白屏 |

## 四、前端工程目录结构

```
interfaces/web/                     # 前端工程根（npm 项目）
├── package.json                    # scripts: dev / build / preview
├── vite.config.ts                  # base=/static/spa/，outDir=../static/spa，
│                                   # dev proxy: /api /stream /health /static/fonts → :8000
├── tsconfig.json                   # strict + noUnusedLocals/Parameters
├── .gitignore                      # node_modules（static/spa 产物保留入库）
└── src/
    ├── main.tsx                    # 入口，BrowserRouter basename 跟随 BASE_URL
    ├── App.tsx                     # 路由表 + ErrorBoundary 包裹
    ├── index.css                   # Design Tokens（#6366f1 主色等）+ @font-face 本地字体
    ├── api/
    │   ├── types.ts                # TaskNode / Workflow / ClearScores / AgentCard 全量契约
    │   └── client.ts               # fetch 封装 + ApiError（三错误键兼容）
    ├── store/
    │   ├── workflowStore.ts        # zustand：wf_id/task_tree/clear_scores/日志/SSE 生命周期/轮询
    │   └── settingsStore.ts        # zustand persist → localStorage
    ├── utils/
    │   ├── format.ts               # 状态中文映射 / 时间格式化
    │   └── history.ts              # 历史记录 localStorage 持久化
    ├── components/
    │   ├── Layout.tsx / Sidebar.tsx          # 布局 + 导航 + 健康/SSE 状态灯
    │   ├── ErrorBoundary.tsx                 # 类组件错误边界
    │   ├── Toaster.tsx / StatusBadge.tsx     # 反馈原语
    │   ├── NewTaskPanel.tsx                  # 新建任务 + 故障注入
    │   ├── ServiceTopology.tsx               # Worker 在线状态（骨架屏）
    │   ├── TaskFlowView.tsx                  # DAG 层级布局 + SVG 贝塞尔连线（含环保护）
    │   ├── TaskNodeCard.tsx                  # 节点卡片（5 态着色/运行脉冲）
    │   ├── TaskDetailDrawer.tsx              # 节点详情抽屉
    │   ├── ClearRadar.tsx                    # echarts radar（按需引入，本地打包）
    │   ├── MetricCards.tsx                   # 任务统计 4 卡
    │   └── LogStream.tsx                     # SSE 日志流（200 条上限/自动滚底/事件着色）
    └── pages/
        ├── DashboardPage.tsx                 # 三栏总控台
        ├── HistoryPage.tsx                   # 工作流历史
        ├── ServicesPage.tsx                  # AgentCard 全景
        └── SettingsPage.tsx                  # 本地偏好

interfaces/static/spa/              # 构建产物（FastAPI 已有 /static 挂载直接覆盖，零后端改动）
├── index.html                      # 526 B
└── assets/index-*.js / *.css       # 626 KB（gzip 209 KB，含 echarts）/ 21 KB
```

## 五、npm 依赖与选型理由

| 依赖 | 版本 | 理由 |
|:----|:----|:----|
| react / react-dom | 18.3.1 | 组件模型 + 生态，企业交付最稳选择 |
| react-router-dom | 6.30.4 | 四页面路由，basename 与静态托管路径对齐 |
| zustand | 4.5.7 | 轻量状态管理（Redux 对单 Dashboard 过重）；persist 中间件白送 localStorage |
| echarts | 5.6.0 | 雷达图事实标准；**按需引入 RadarChart**，npm 打包彻底告别 CDN |
| vite + @vitejs/plugin-react | 5.4.x / 4.7.x | 秒级 HMR + Rollup 生产构建，proxy 解决开发联调 |
| typescript + @types/* | 5.9.x | strict 模式，后端契约即类型 |

刻意不引入：UI 组件库（AntD/MUI 与白底定制风格冲突且体积翻倍）、Redux、CSS 框架（Design Tokens + 原生 CSS Grid 足够）。

## 六、构建与部署说明

### 开发联调（改前端代码时）
```bash
# 终端 1：后端
.venv/Scripts/python.exe services/supervisor/main.py      # :8000
# 终端 2：前端 HMR（proxy 已指向 :8000）
cd interfaces/web && npm run dev                           # http://localhost:5173/static/spa/
```

### 生产/演示（离线可用）
```bash
cd interfaces/web && npm install && npm run build          # 仅需联网这一次
# 产物落到 interfaces/static/spa/，随代码卷挂载进容器
docker-compose up -d                                       # 或本地 uvicorn
# 访问 http://localhost:8000/static/spa/index.html
```

### 从旧方案切换的路径
1. **现在**：SPA 与 Jinja2 页面并存。总控台用 SPA（`/static/spa/index.html`），登录/问答/搜索等旧页照常
2. **下一步**：把 SPA 入口链接加进 `base.html` 导航（一行 `<a>`），或在 app.py 加一条 `/console` 重定向
3. **长期**：chat/workflow 等页面逐个迁移为 SPA 路由，Jinja2 收敛为仅登录页（或全量替换后删除模板）

### 与后端的边界
- 后端零接口改动：SPA 只消费既有 `/api/workflows`、`/api/agents/cards`、`/stream`、`/health`
- FastAPI 既有 `app.mount("/static", ...)` 自动覆盖新产物，无需新增挂载
- `docker-compose.yml` 代码卷挂载已覆盖 `interfaces/`，容器内即时生效
