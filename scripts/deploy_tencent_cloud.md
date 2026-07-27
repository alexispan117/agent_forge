# AgentForge 腾讯云部署指南

> 目标服务器: 腾讯云轻量应用服务器 2核2GB · 宝塔Linux面板
> 部署方式: Docker-Compose 4 节点微服务（资源优化版）

---

## 一、服务器环境准备

### 1.1 查看当前配置
登录宝塔面板 → 打开「终端」，执行：

```bash
uname -a        # 查看系统版本
free -h         # 查看内存
df -h           # 查看磁盘
```

### 1.2 安装 Docker（两种方式任选）

**方式A（推荐）**：宝塔面板 → 软件商店 → 搜索 "Docker" → 一键安装

**方式B（命令行）**：
```bash
curl -fsSL https://get.docker.com | bash
systemctl enable docker && systemctl start docker
```

### 1.3 安装 Docker-Compose

```bash
# 下载最新稳定版
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# 赋予执行权限
chmod +x /usr/local/bin/docker-compose

# 验证
docker-compose --version
```

---

## 二、上传项目代码

### 2.1 在服务器创建项目目录

```bash
mkdir -p /opt/agent_forge
cd /opt/agent_forge
```

### 2.2 上传代码（四选一）

**方式A — 宝塔面板上传**：
1. 宝塔面板 → 文件 → 进入 `/opt/agent_forge/`
2. 将你本地 `D:\hermes\work\agentgroup\agent_forge\` 下的**所有文件和目录**打包成 `agent_forge.zip`
3. 宝塔面板上传 zip → 解压

**方式B — SCP（本地终端）**：
```bash
# 在你的 Windows 终端执行（需先 cd 到项目目录）
scp -r D:\hermes\work\agentgroup\agent_forge\* root@你的服务器IP:/opt/agent_forge/
```

**方式C — rsync（推荐，支持断点续传）**：
```bash
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude 'chroma_db' \
  D:/hermes/work/agentgroup/agent_forge/ root@你的服务器IP:/opt/agent_forge/
```

**方式D — Git**：
```bash
# 如果项目已纳入 Git
cd /opt/agent_forge
git clone https://github.com/你的账号/agent_forge.git .
```

---

## 三、配置环境变量

### 3.1 创建 .env 文件

在 `/opt/agent_forge/` 下创建 `.env` 文件：

```bash
cd /opt/agent_forge
cat > .env << 'EOF'
# LLM 模式：true=离线Mock(默认) false=真实API
LLM_MOCK_MODE=true

# 真实 API 配置（LLM_MOCK_MODE=false 时生效）
LLM_API_KEY=sk-your-deepseek-key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash

# 百度搜索 API（可选）
BAIDU_API_KEY=your-baidu-key

# 阿里 DashScope Embedding（可选）
DASHSCOPE_API_KEY=your-dashscope-key

# 数据库 URL
DATABASE_URL=sqlite:///data/app.db

# Worker 服务地址
WORKER_ANALYST_URL=http://worker-analyst:8001
WORKER_DESENSITIZE_URL=http://worker-desensitize:8002
WORKER_REPORT_URL=http://worker-report:8003

# Supervisor 密钥（自定义）
SECRET_KEY=change-this-to-random-string
EOF
```

---

## 四、资源优化版 docker-compose（2核2GB 专用）

把以下内容覆盖到 `/opt/agent_forge/docker-compose.yml`：

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: af-redis
    restart: unless-stopped
    command: redis-server --save "" --maxmemory 64mb --maxmemory-policy allkeys-lru
    mem_limit: 128m
    mem_reservation: 64m
    networks:
      - agentforge

  supervisor:
    build: .
    container_name: af-supervisor
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - SERVICE_TYPE=supervisor
      - PORT=8000
      - LLM_MOCK_MODE=${LLM_MOCK_MODE:-true}
      - REDIS_URL=redis://redis:6379
    env_file:
      - .env
    depends_on:
      - redis
    volumes:
      - ./data:/app/data
    command: python services/supervisor/main.py
    mem_limit: 400m
    mem_reservation: 200m
    networks:
      - agentforge

  worker-analyst:
    build: .
    container_name: af-analyst
    restart: unless-stopped
    ports:
      - "8001:8001"
    environment:
      - SERVICE_TYPE=analyst
      - PORT=8001
      - LLM_MOCK_MODE=${LLM_MOCK_MODE:-true}
    depends_on:
      - supervisor
    volumes:
      - ./data:/app/data
    command: python services/worker_analyst/main.py
    mem_limit: 350m
    mem_reservation: 200m
    networks:
      - agentforge

  worker-desensitize:
    build: .
    container_name: af-desensitize
    restart: unless-stopped
    ports:
      - "8002:8002"
    environment:
      - SERVICE_TYPE=desensitize
      - PORT=8002
      - LLM_MOCK_MODE=${LLM_MOCK_MODE:-true}
    depends_on:
      - supervisor
    volumes:
      - ./data:/app/data
    command: python services/worker_desensitize/main.py
    mem_limit: 350m
    mem_reservation: 200m
    networks:
      - agentforge

  worker-report:
    build: .
    container_name: af-report
    restart: unless-stopped
    ports:
      - "8003:8003"
    environment:
      - SERVICE_TYPE=report
      - PORT=8003
      - LLM_MOCK_MODE=${LLM_MOCK_MODE:-true}
    depends_on:
      - supervisor
    volumes:
      - ./data:/app/data
    command: python services/worker_report/main.py
    mem_limit: 350m
    mem_reservation: 200m
    networks:
      - agentforge

networks:
  agentforge:
    driver: bridge
```

> **内存预算**: Redis 128MB + Supervisor 400MB + 3 Workers × 350MB = 1,578MB，剩余 ~450MB 给系统。

---

## 五、启动与验证

### 5.1 构建镜像（首次约 3-5 分钟）

```bash
cd /opt/agent_forge
docker-compose build
```

### 5.2 启动全部服务

```bash
docker-compose up -d
```

### 5.3 查看运行状态

```bash
# 容器状态
docker-compose ps

# 实时日志
docker-compose logs -f

# 只查看 supervisor 日志
docker-compose logs -f supervisor

# 资源使用
docker stats --no-stream
```

### 5.4 验证服务

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 首页
curl -I http://localhost:8000/

# 3. 客诉工单
curl -I http://localhost:8000/complaints

# 4. API 测试
curl -X POST -d "ticket_id=TK-2026-001" http://localhost:8000/api/complaints/run
```

### 5.5 如果 Worker 全部离线（内存不足导致）

2核2GB 可能无法同时启动全部 4 个 Python 容器。如果出现 Worker 持续重启，先只启动 Supervisor：

```bash
# 最小部署模式
docker-compose up -d supervisor redis
# 然后一个一个加
docker-compose up -d worker-analyst
docker-compose up -d worker-desensitize
docker-compose up -d worker-report
```

---

## 六、宝塔面板配置

### 6.1 开放端口

宝塔面板 → 安全 → 添加端口规则：
- 8000（Supervisor + Web 界面）
- 8001-8003（Worker 内部通信，可选）

### 6.2 腾讯云安全组

腾讯云控制台 → 轻量应用服务器 → 防火墙 → 添加规则：
- 协议: TCP，端口: 8000，来源: 0.0.0.0/0

### 6.3 访问你的项目

浏览器打开: `http://你的服务器IP:8000/`

---

## 七、常用运维命令

```bash
# 停止所有容器
docker-compose down

# 重启某个服务
docker-compose restart supervisor

# 查看磁盘空间
docker system df

# 清理未使用的镜像和容器（释放空间）
docker system prune -a

# 更新代码后重新构建
git pull                    # 如果用 Git
docker-compose build        # 重新构建
docker-compose up -d        # 重启
```

---

## 八、快速诊断清单

如果访问不了，依次检查：

| 步骤 | 命令 | 预计结果 |
|:----|:-----|:--------|
| 容器在运行？ | `docker-compose ps` | 全部 Up |
| 端口在监听？ | `netstat -tlnp \| grep 8000` | 有 LISTEN |
| 防火墙开了？ | 宝塔面板 → 安全 → 检查 8000 | 已添加 |
| 腾讯云安全组？ | 控制台 → 防火墙 → 检查 8000 | 已添加 |
| 服务正常？ | `curl localhost:8000/health` | `{"status":"ok"}` |
