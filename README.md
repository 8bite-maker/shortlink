# ShortLink

一个极简的短链服务。把长链接换成短链接，访问短链接自动跳回原地址，并统计每次点击。

## 功能

- 网页上粘贴长链接，一键生成短链接
- 访问短链接 → 302 跳转到原始地址
- **点击统计** —— 每条短链被访问多少次
- **数据持久化** —— 重启服务数据不丢
- **缓存加速** —— 跳转命中缓存时完全不查数据库
- **接口限流** —— 防止创建接口被恶意刷
- 首页展示最近生成的短链及其点击量
- `/health` 健康检查接口

## 快速开始

### Windows：一键启动（最省事）

装好依赖后，直接**双击项目根目录的 `start.bat`**，会弹出一个命令行窗口并自动启动服务。
关闭那个窗口 = 停止服务。

首次使用需要先建好虚拟环境并装依赖（只做一次）：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 手动启动

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

### 关于 Redis

**不装 Redis 也能直接跑**。缓存层会自动降级到 `fakeredis`（纯 Python 内存实现），
API 与真 Redis 完全一致。要接真 Redis，只需设置环境变量：

```bash
# Linux / macOS
export REDIS_URL="redis://127.0.0.1:6379/0"

# Windows PowerShell
$env:REDIS_URL = "redis://127.0.0.1:6379/0"
```

## Docker 部署（推荐）

不用装 Python、不用配环境，一条命令全起来：

```bash
# 构建镜像并启动 web + redis 两个容器
docker compose up -d --build

# 查看运行状态
docker compose ps

# 实时看应用日志
docker compose logs -f web

# 停止并移除容器（数据仍保留）
docker compose down
```

启动后访问 <http://127.0.0.1:8000>。

**它做了什么：**

| 组件 | 说明 |
| --- | --- |
| `web` 容器 | 把你的代码 + Python 3.13 + 依赖一起打包运行 |
| `redis` 容器 | 官方 Redis 7 镜像，只在内部网络可见，不暴露到宿主机 |
| `./data` 目录 | 数据库文件挂载到宿主机，**删掉容器数据也不丢** |
| `redis-data` 卷 | Redis 数据的命名卷，由 Docker 统一管理 |

**连数据一起彻底清理：**

```bash
docker compose down -v && rm -rf ./data
```

**为什么 Dockerfile 里必须写 `--host 0.0.0.0`：**
写 `127.0.0.1` 表示只接受容器内部的连接，宿主机永远连不上。这是新手最常踩的坑。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查，返回短链总数与当前缓存后端 |
| GET | `/api/links` | 最近的短链列表（`?limit=10`，上限 100） |
| POST | `/api/links` | 提交 `{"url": "https://..."}`，返回短码（有限流） |
| GET | `/api/links/{code}` | 查询单条短链的统计信息 |
| POST | `/api/sync` | 手动把缓冲的点击量落库（调试用） |
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
│   ├── main.py         # 路由与接口逻辑
│   ├── db.py           # 数据库连接与会话管理
│   ├── models.py       # 数据表结构（ORM 模型）
│   └── cache.py        # 缓存、点击缓冲、限流
├── static/index.html   # 前端页面（原生 HTML + JS）
├── Dockerfile          # 镜像构建说明
├── docker-compose.yml  # 一键启动 web + redis
├── .dockerignore       # 构建镜像时忽略的文件
├── data/               # 挂载出来的数据目录（自动生成，已忽略）
├── shortlink.db        # SQLite 数据库（自动生成，已忽略）
├── requirements.txt
└── README.md
```

## 技术栈

- **FastAPI** — Web 框架，异步、自带 API 文档
- **Pydantic** — 数据校验（请求体自动检查是否是合法 URL）
- **SQLAlchemy** — ORM，用 Python 类操作数据库
- **SQLite** — 单文件数据库，零配置
- **Redis** — 缓存链接、缓冲点击量、实现限流
- **Uvicorn** — ASGI 服务器，负责实际收发 HTTP 请求
- 前端：原生 HTML + CSS + JavaScript，无构建步骤

## 设计取舍

- **短码用 `secrets` 而非 `random`** — 密码学安全随机源，防止短码被预测后遍历
- **短码碰撞用重试而非覆盖** — 覆盖会导致用户 A 的链接指向 B 的地址
- **用 302 而非 301** — 保证「可改指向 + 可统计」两个能力
- **缓存用 cache-aside 策略** — 先查缓存，未命中再查库并回填
- **点击量先缓冲再批量落库** — 1000 次点击合并成 1 次 UPDATE，磁盘写入降几个数量级
- **缓存设 TTL（24 小时）** — 没人访问的短链自动从内存消失，防止内存被撑满
- **限流用固定窗口计数** — 实现简单；缺点是在窗口边界可能瞬时双倍放行

## Roadmap

- [x] **v1** — 核心功能，内存字典存储
- [x] **v2** — SQLite 持久化 + 点击统计
- [x] **v3** — Redis 缓存 + 点击缓冲 + 接口限流
- [x] **v4** — Docker 容器化，`docker compose up` 一键启动
- [ ] **v5** — 部署到公网，拿到可分享的地址
- [ ] **v6** — 布隆过滤器解决缓存穿透 + 高并发优化

## 已知限制

- 本地默认走 `fakeredis`，它活在应用进程内，**应用重启缓冲的点击量会丢**；Docker 部署后接的是真 Redis，没这个问题
- 限流按 IP 计数，同一 NAT 后的多个用户会共享额度
- 缓存的链接在 TTL 内不会被主动失效（暂不支持改指向）
- 单机 SQLite，不支持多实例部署
- Dockerfile 为便于理解采用单阶段构建，生产环境可用多阶段构建进一步缩小镜像
