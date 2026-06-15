# Laniakea Radio 后端 Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY . .

# 创建数据目录（SQLite 持久化）
RUN mkdir -p /app/data

EXPOSE 8000

# 设置数据目录环境变量（与 docker-compose volume 挂载一致）
ENV DATA_DIR=/app/data
ENV POI_KNOWLEDGE_DB=/app/data/poi_knowledge.db

# 启动 uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
