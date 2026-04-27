#!/bin/bash

# 启动 AEIQ 服务
# 包含 FastAPI HTTP 服务（端口 8000）和 UDP Socket 服务（端口 8888）

cd "$(dirname "$0")/AEIQ" || exit 1

echo "正在启动 AEIQ 服务..."
echo "- FastAPI HTTP 服务: http://0.0.0.0:8000"
echo "- UDP Socket 服务: udp://0.0.0.0:8888"
echo "- API 文档: http://localhost:8000/docs"
echo ""

python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
