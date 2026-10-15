# ShortLink

一个极简的短链服务。把长链接换成短链接，访问短链接自动跳回原地址。

## 功能

- 网页上粘贴长链接，一键生成短链接
- 访问短链接 → 302 跳转到原始地址
- `/health` 健康检查接口

## 快速开始

```bash
# 1. 创建虚拟环境（只做一次）
python -m venv .venv

# 2. 激活虚拟环境
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动服务
uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000> 就能看到页面。
接口文档（FastAPI 自动生成）：<http://127.0.0.1:8000/docs>

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查，返回短链总数 |
| POST | `/api/links` | 提交 `{"url": "https://..."}`，返回短码 |
| GET | `/{code}` | 跳转到原始链接 |

调试用 curl：

```bash
curl -X POST http://127.0.0.1:8000/api/links \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://www.python.org/\"}"
```

## 技术栈

- **FastAPI** — Web 框架，异步、自带 API 文档
- **Pydantic** — 数据校验（请求体自动检查是否是合法 URL）
- **Uvicorn** — ASGI 服务器，负责实际收发 HTTP 请求
- 前端：原生 HTML + CSS + JavaScript，无构建步骤

## Roadmap

- [x] **v1** — 核心功能，内存字典存储
- [ ] **v2** — SQLite 持久化 + 点击统计（重启不丢数据）
- [ ] **v3** — Redis 缓存 + 接口限流
- [ ] **v4** — Docker 部署上线，拿到公网地址
- [ ] **v5** — 布隆过滤器 + 高并发优化

## 已知限制

v1 的数据存在内存里，**进程重启后就没了**。这是 v2 要解决的问题。
