# ---- 基础镜像 ----
# 官方 Python 镜像。slim 是精简版，体积小且够用
FROM python:3.13-slim

# ---- 工作目录 ----
# 容器内部的"当前目录"，后面所有相对路径都基于它
WORKDIR /app

# ---- 安装依赖 ----
# 关键技巧：先只复制依赖清单，装完依赖再复制代码。
# Docker 镜像是分层缓存的，只要 requirements.txt 没变，
# 以后每次改代码重新构建时这一层直接复用，省掉几分钟的下载时间。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
        -i https://pypi.tuna.tsinghua.edu.cn/simple

# ---- 复制源码 ----
# 放在依赖之后：代码改动频繁，让它别影响上面那层缓存
COPY app/ ./app/
COPY static/ ./static/

# ---- 声明端口 ----
# 纯文档作用，告诉别人这个容器用哪个端口。
# 真正的端口映射由 docker run -p 或 compose 的 ports 决定
EXPOSE 8000

# ---- 启动命令 ----
# ⚠️ 必须是 0.0.0.0，绝不能写 127.0.0.1！
# 写 127.0.0.1 表示"只接受来自容器内部的连接"，
# 宿主机和外面就永远连不上 —— 这是新手最常踩的坑。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
