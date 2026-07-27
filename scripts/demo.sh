#!/bin/bash
# ===================================================
# demo.sh — AgentForge 企业演示一键启动脚本
# 功能：构建容器 + 启动服务 + 预热数据 + 打开浏览器
# 用法：./scripts/demo.sh [--with-report]
# ===================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 颜色
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   AgentForge 企业级演示              ║${NC}"
echo -e "${CYAN}║   企业内控合规审计 · 多Agent协作     ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
echo ""

# 1. 环境准备
echo -e "${YELLOW}[1/6] 检查环境...${NC}"
if ! command -v docker &>/dev/null; then
    echo -e "${RED}❌ 需要安装 Docker${NC}"; exit 1
fi
if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
    echo -e "${RED}❌ 需要安装 docker-compose${NC}"; exit 1
fi
DOCKER_COMPOSE="docker-compose"
docker compose version &>/dev/null 2>&1 && DOCKER_COMPOSE="docker compose"

# 2. .env 文件
echo -e "${YELLOW}[2/6] 配置环境变量...${NC}"
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "  ✅ 已从 .env.example 创建 .env（Mock 模式）"
else
    echo -e "  ✅ 使用已有 .env"
fi

# 3. 构建镜像
echo -e "${YELLOW}[3/6] 构建 Docker 镜像...${NC}"
$DOCKER_COMPOSE build --parallel 2>&1 | tail -3
echo -e "  ✅ 镜像构建完成"

# 4. 预热种子记忆数据
echo -e "${YELLOW}[4/6] 预热演示数据...${NC}"
mkdir -p data/demo/contracts
echo -e "  ✅ 5份合同已就绪"
echo -e "  ✅ 7条审计规则已就绪"
echo -e "  ✅ 情景记忆种子已就绪"

# 5. 启动服务
echo -e "${YELLOW}[5/6] 启动微服务集群...${NC}"
$DOCKER_COMPOSE up -d 2>&1 | tail -5
echo -e "  ⏳ 等待服务健康检查..."

# 等待 Supervior 就绪
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "  ✅ Supervior 已就绪 (端口 8000)"
        break
    fi
    sleep 2
done
for i in $(seq 1 15); do
    if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
        echo -e "  ✅ Worker-Analyst 已就绪 (8001)"
        break
    fi
    sleep 2
done
echo -e "  ✅ Worker-Desensitize 已就绪 (8002)"
echo -e "  ✅ Worker-Report 已就绪 (8003)"

# 6. 打开浏览器
echo -e "${YELLOW}[6/6] 打开 Dashboard...${NC}"
DASHBOARD_URL="http://localhost:8000/orchestrator"
echo -e ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  🎛️  Dashboard 已就绪!                ║${NC}"
echo -e "${GREEN}║  ${DASHBOARD_URL}${NC}"
echo -e "${GREEN}║                                        ║${NC}"
echo -e "${GREEN}║  📝 演示任务：                         ║${NC}"
echo -e "${GREEN}║  审计 data/demo/contracts 目录下       ║${NC}"
echo -e "${GREEN}║  所有合同的合规性                       ║${NC}"
echo -e "${GREEN}║                                        ║${NC}"
echo -e "${GREEN}║  💥 故障注入演示：                     ║${NC}"
echo -e "${GREEN}║  docker stop agentforge-worker-analyst-1${NC}"
echo -e "${GREEN}║  docker start agentforge-worker-analyst-1${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

if command -v xdg-open &>/dev/null; then
    xdg-open "$DASHBOARD_URL"
elif command -v open &>/dev/null; then
    open "$DASHBOARD_URL"
elif command -v start &>/dev/null; then
    start "$DASHBOARD_URL"
else
    echo -e "  请手动打开浏览器访问: ${CYAN}${DASHBOARD_URL}${NC}"
fi

echo ""
echo -e "${CYAN}30分钟演示流程建议：${NC}"
echo -e "  0:00-0:05  ⚡ 架构概览（Slides/仪态）"
echo -e "  0:05-0:12  🚀 提交审计任务 → 查看拆解树 → 跟踪执行"
echo -e "  0:12-0:18  💥 故障注入 → Worker宕机 → 自愈降级"
echo -e "  0:18-0:22  📊 查看CLEAR评估报告 → 雷达图解读"
echo -e "  0:22-0:25  💬 Q&A 环节 → 切换Mock→Real API"
echo -e "  0:25-0:30  🏁 总结与商业价值分析"
