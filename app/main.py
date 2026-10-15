"""ShortLink —— 短链服务 v2

相比 v1 的三处变化：
1. 存储从「内存字典」换成「SQLite 数据库」—— 进程重启数据不再丢失
2. 新增点击统计 —— 每次跳转累加计数
3. 新增列表/统计接口 —— 前端可以展示历史短链
"""

from datetime import datetime
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import Link

app = FastAPI(
    title="ShortLink",
    description="一个极简的短链服务",
    version="0.2.0",
)

# 启动时确保数据表存在（已存在则什么都不做）。
# 开发阶段这样够用；生产环境应该换成 Alembic 做正式的数据库迁移。
Base.metadata.create_all(bind=engine)

# 短码字符表：数字 + 小写 + 大写，共 62 个字符
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CODE_LENGTH = 6
MAX_RETRY = 5
RECENT_LIMIT = 10


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


def generate_code(length: int = CODE_LENGTH) -> str:
    """生成随机短码。

    用 secrets 而不是 random：secrets 是密码学安全的随机源，
    不会被预测。短码要是能被猜到，别人就能遍历你的所有短链。
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


@app.get("/health", summary="健康检查")
def health(db: Session = Depends(get_db)) -> dict:
    """给运维/监控用的接口：服务还活着吗，库里有多少条数据。"""
    return {"status": "ok", "total_links": db.query(Link).count()}


@app.get("/api/links", response_model=list[LinkOut], summary="最近的短链列表")
def list_links(
    limit: int = RECENT_LIMIT, db: Session = Depends(get_db)
) -> list[LinkOut]:
    # 参数保护：外部传进来的值别直接信，夹在 1~100 之间
    limit = max(1, min(limit, 100))
    links = db.query(Link).order_by(Link.id.desc()).limit(limit).all()
    return [to_out(link) for link in links]


@app.post("/api/links", response_model=LinkOut, summary="生成短链")
def create_link(payload: CreateLinkRequest, db: Session = Depends(get_db)) -> LinkOut:
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
    return to_out(link)


@app.get("/api/links/{code}", response_model=LinkOut, summary="查询单条短链统计")
def get_link(code: str, db: Session = Depends(get_db)) -> LinkOut:
    link = db.query(Link).filter(Link.code == code).first()
    if link is None:
        raise HTTPException(status_code=404, detail="短链不存在")
    return to_out(link)


@app.get("/{code}", summary="短链跳转")
def redirect(code: str, db: Session = Depends(get_db)):
    """访问 /abc123 就跳回原始长链接，同时累加点击次数。"""
    link = db.query(Link).filter(Link.code == code).first()
    if link is None:
        raise HTTPException(status_code=404, detail="短链不存在或已失效")

    # 每次点击都写一次数据库。当前够用，但高并发下这里会成为瓶颈 ——
    # 这正是 v3 要引入 Redis 的原因之一（先在内存累加，再批量落库）。
    link.clicks += 1
    db.commit()

    # 302 = 临时重定向，保证「可改指向 + 可统计」两个能力
    return RedirectResponse(url=link.target, status_code=302)


# 前端静态页面挂到根路径。
# 用绝对路径而不是 "static"，这样无论从哪个目录启动都能找到文件。
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
