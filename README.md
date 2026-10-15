# ShortLink

一个极简的短链服务。把长链接换成短链接，访问短链接自动跳回原地址，并统计每次点击。

## 功能

- 网页上粘贴长链接，一键生成短链接
- 访问短链接 → 302 跳转到原始地址
- **点击统计** —— 每条短链被访问多少次
- **数据持久化** —— 重启服务数据不丢
- 首页展示最近生成的短链及其点击量
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

首次启动会自动在项目根目录创建 `shortlink.db`（SQLite 数据库文件）。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查，返回短链总数 |
| GET | `/api/links` | 最近的短链列表（`?limit=10`，上限 100） |
| POST | `/api/links` | 提交 `{"url": "https://..."}`，返回短码 |
| GET | `/api/links/{code}` | 查询单条短链的统计信息 |
| GET | `/{code}` | 跳转到原始链接，并累加点击次数 |

调试用 curl：

```bash
# 生成短链
curl -X POST http://127.0.0.1:8000/api/links \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://www.python.org/\"}"

# 查看统计
curl http://127.0.0.1:8000/api/links/xxxxxx
```

## 项目结构

```
shortlink/
├── app/
│   ├── main.py       # 路由与接口逻辑
│   ├── db.py         # 数据库连接与会话管理
│   └── models.py     # 数据表结构（ORM 模型）
├── static/index.html # 前端页面（原生 HTML + JS）
├── shortlink.db      # SQLite 数据库（自动生成，已在 .gitignore 中忽略）
├── requirements.txt
└── README.md
```

## 技术栈

- **FastAPI** — Web 框架，异步、自带 API 文档
- **Pydantic** — 数据校验（请求体自动检查是否是合法 URL）
- **SQLAlchemy** — ORM，用 Python 类操作数据库
- **SQLite** — 单文件数据库，零配置
- **Uvicorn** — ASGI 服务器，负责实际收发 HTTP 请求
- 前端：原生 HTML + CSS + JavaScript，无构建步骤

## 设计取舍

- **短码用 `secrets` 而非 `random`** — 密码学安全随机源，防止短码被预测后遍历
- **短码碰撞用重试而非覆盖** — 覆盖会导致用户 A 的链接指向 B 的地址
- **用 302 而非 301** — 保证「可改指向 + 可统计」两个能力
- **点击写库是同步的** — 当前够用，高并发下会成为瓶颈，这是后续优化的方向

## Roadmap

- [x] **v1** — 核心功能，内存字典存储
- [x] **v2** — SQLite 持久化 + 点击统计
- [ ] **v3** — Redis 缓存 + 接口限流（读多写少场景的性能优化）
- [ ] **v4** — Docker 部署上线，拿到公网地址
- [ ] **v5** — 布隆过滤器 + 高并发优化

## 已知限制

- 每次跳转都要写一次数据库，高并发场景下会成为写瓶颈
- 没有接口限流，容易被刷
- 单机 SQLite，不支持多实例部署
