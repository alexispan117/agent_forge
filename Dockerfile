# Dockerfile — 多服务通用镜像
# 所有容器使用同一镜像，通过 SERVICE_TYPE 环境变量区分角色
FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl procps netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# healthcheck 脚本
RUN printf '#!/bin/bash\ncurl -sf http://localhost:$PORT/health > /dev/null 2>&1\nexit $?\n' > /healthcheck.sh && \
    chmod +x /healthcheck.sh

# 默认入口（由 docker-compose.yml 的 command 覆盖）
CMD ["python", "-c", "print('使用 docker-compose.yml 的 command 参数指定服务类型')"]
