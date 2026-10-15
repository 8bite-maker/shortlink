"""ShortLink —— 短链服务 v3

相比 v2 的三处优化（都在"性能"这条线上）：
1. Redis 缓存「短码 → 原链接」，跳转不再查数据库
2. 点击次数先攒在 Redis，后台定时批量落库 —— 跳转路径上零磁盘写
3. 接口限流，防止创建接口被恶意刷
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app import cache
from app.db import Base, engine, get_db, SessionLocal
from app.models import Link

# 后台落库间隔（秒）
SYNC_INTERVAL = 5

# 短码字符表：数字 + 小写 + 大写，共 62 个字符
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CODE_LENGTH = 6
MAX_RETRY = 5
RECENT_LIMIT = 10


def sync_clicks_to_db() -> int:
    """把 Redis 里缓冲的点击量批量写回数据库，返回同步了几条短链。

    这是"写合并"（write coalescing）的典型做法：
    1000 次点击 → 1 次批量 UPDATE，而不是 1000 次单条 UPDATE。
    磁盘写入次数降低几个数量级。
    """
    drained = cache.drain_clicks()
    if not drained:
        return 0
    db = SessionLocal()
    try:
        for code, delta in drained.items():
            # 用 SQL 表达式自增，而不是先读出来再赋值 —— 并发下不会算错
            db.query(Link).filter(Link.code == code).update(
                {Link.clicks: Link.clicks + delta}, synchronize_session=False
            )
        db.commit()
        return len(drained)
    finally:
        db.close()


async def _periodic_sync() -> None:
    """后台循环：每隔 SYNC_INTERVAL 秒把缓冲的点击量落一次库。"""
    while True:
        await asyncio.sleep(SYNC_INTERVAL)
        try:
            sync_clicks_to_db()
        except Exception:
            # 后台任务绝不能因为一次异常就整体退出
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用的生命周期钩子：启动时做准备，关闭时收尾。"""
    Base.metadata.create_all(bind=engine)  # 确保表存在
    task = asyncio.create_task(_periodic_sync())  # 拉起后台同步任务
    yield
    task.cancel()  # 关闭后台任务
    sync_clicks_to_db()  # 关闭前再刷一次，尽量不丢数据


app = FastAPI(
    title="ShortLink",
    description="一个极简的短链服务",
    version="0.3.0",
    lifespan=lifespan,
)


class CreateLinkRequest(BaseModel):
    """请求体：前端 POST 过来的长链接。

    HttpUrl 不是普通字符串，Pydantic 会帮我们校验它是不是合法 URL，
    不合法会直接返回 422，省得我们自己写正则。
    """

    url: HttpUrl


class LinkOut(BaseModel):
    """响应体：一条短链的对外表示。"""

    code: str
    short_url: str
    target: str
    clicks: int
    created_at: datetime


def to_out(link: Link) -> LinkOut:
    """把数据库对象转成响应模型。

    多这一层的意义：数据库表结构以后可能变（加字段、改字段名），
    但只要这里转一下，接口对外的格式就能保持稳定，不影响前端。
    """
    return LinkOut(
        code=link.code,
        short_url=f"/{link.code}",
        target=link.target,
        clicks=link.clicks,
        created_at=link.created_at,
    )


def with_buffered_clicks(link: Link) -> LinkOut:
    """统计要用「数据库里的值 + 还没落库的缓冲」才是实时数字。"""
    item = to_out(link)
    item.clicks += cache.get_buffered_clicks(link.code)
    return item


def generate_code(length: int = CODE_LENGTH) -> str:
    """生成随机短码。

    用 secrets 而不是 random：secrets 是密码学安全的随机源，
    不会被预测。短码要是能被猜到，别人就能遍历你的所有短链。
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


@app.get("/health", summary="健康检查")
def health(db: Session = Depends(get_db)) -> dict:
    """给运维/监控用的接口。"""
    return {
        "status": "ok",
        "total_links": db.query(Link).count(),
        "cache_backend": "redis" if cache.using_real_redis else "fakeredis",
    }


@app.get("/api/links", response_model=list[LinkOut], summary="最近的短链列表")
def list_links(
    limit: int = RECENT_LIMIT, db: Session = Depends(get_db)
) -> list[LinkOut]:
    # 参数保护：外部传进来的值别直接信，夹在 1~100 之间
    limit = max(1, min(limit, 100))
    links = db.query(Link).order_by(Link.id.desc()).limit(limit).all()
    return [with_buffered_clicks(link) for link in links]


@app.post("/api/links", response_model=LinkOut, summary="生成短链")
def create_link(
    payload: CreateLinkRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LinkOut:
    # ---- 限流：按客户端 IP 计数，防止被刷 ----
    client_ip = request.client.host if request.client else "unknown"
    allowed, remaining = cache.allow_request(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,  # 429 = Too Many Requests
            detail=f"请求过于频繁，请 {cache.RATE_LIMIT_WINDOW} 秒后再试",
            headers={"Retry-After": str(cache.RATE_LIMIT_WINDOW)},
        )

    target = str(payload.url)

    # 随机短码有极小概率撞上已有的，撞了就重试
    code = ""
    for _ in range(MAX_RETRY):
        candidate = generate_code()
        if db.query(Link).filter(Link.code == candidate).first() is None:
            code = candidate
            break
    if not code:
        raise HTTPException(status_code=500, detail="短码生成失败，请重试")

    link = Link(code=code, target=target)
    db.add(link)
    db.commit()
    db.refresh(link)  # 回读一次，拿到数据库生成的 id 和默认值

    # 顺手写进缓存，这样第一次跳转就能命中
    cache.cache_target(code, target)

    return to_out(link)


@app.get("/api/links/{code}", response_model=LinkOut, summary="查询单条短链统计")
def get_link(code: str, db: Session = Depends(get_db)) -> LinkOut:
    link = db.query(Link).filter(Link.code == code).first()
    if link is None:
        raise HTTPException(status_code=404, detail="短链不存在")
    return with_buffered_clicks(link)


@app.post("/api/sync", summary="手动把缓冲的点击量落库")
def sync_now() -> dict:
    """调试用：不等后台定时任务，立刻同步一次。"""
    return {"synced_codes": sync_clicks_to_db()}


@app.get("/{code}", summary="短链跳转")
def redirect(code: str, db: Session = Depends(get_db)):
    """访问 /abc123 就跳回原始长链接。

    v3 的关键变化：整条路径上**没有数据库读写** ——
    读走缓存、写进内存，这就是高并发下能扛住的原因。
    """
    # 1. 先查缓存
    target = cache.get_cached_target(code)

    if target is None:
        # 2. 缓存没命中（第一次访问或缓存已过期），才去查数据库
        link = db.query(Link).filter(Link.code == code).first()
        if link is None:
            raise HTTPException(status_code=404, detail="短链不存在或已失效")
        target = link.target
        # 回填缓存，下次访问就命中缓存了 —— 这叫 cache-aside 策略
        cache.cache_target(code, target)

    # 3. 点击量只加到 Redis，等后台任务批量落库
    cache.buffer_click(code)

    # 302 = 临时重定向，保证「可改指向 + 可统计」两个能力
    return RedirectResponse(url=target, status_code=302)


# 前端静态页面挂到根路径。
# 用绝对路径而不是 "static"，这样无论从哪个目录启动都能找到文件。
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
