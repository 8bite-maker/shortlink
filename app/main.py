"""ShortLink —— 短链服务 v1

v1 的目标很小：把长链接变成短链接，访问短链接能跳回去。

存储用的是内存字典（Python 的 dict），进程一重启数据就没了 ——
这不是 bug，是刻意留给 v2 解决的第一个问题。
"""

from pathlib import Path
import secrets

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

app = FastAPI(
    title="ShortLink",
    description="一个极简的短链服务",
    version="0.1.0",
)

# 短码字符表：数字 + 小写 + 大写，共 62 个字符
# 6 位短码的组合数是 62^6 ≈ 568 亿，够用很久
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CODE_LENGTH = 6
MAX_RETRY = 5

# v1 的"数据库"：内存字典 {短码: 原始链接}
_links: dict[str, str] = {}


class CreateLinkRequest(BaseModel):
    """请求体：前端 POST 过来的长链接。

    HttpUrl 不是普通字符串，Pydantic 会帮我们校验它是不是合法 URL，
    不合法会直接返回 422，省得我们自己写正则。
    """

    url: HttpUrl


class CreateLinkResponse(BaseModel):
    """响应体：生成好的短码和短链接。"""

    code: str
    short_url: str
    target: str


def generate_code(length: int = CODE_LENGTH) -> str:
    """生成随机短码。

    用 secrets 而不是 random：secrets 是密码学安全的随机源，
    不会被预测。短码要是能被猜到，别人就能遍历你的所有短链。
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


@app.get("/health", summary="健康检查")
def health() -> dict:
    """给运维/监控用的接口：服务还活着吗。"""
    return {"status": "ok", "total_links": len(_links)}


@app.post("/api/links", response_model=CreateLinkResponse, summary="生成短链")
def create_link(payload: CreateLinkRequest) -> CreateLinkResponse:
    target = str(payload.url)

    # 随机短码有极小概率撞上已有的，撞了就重试
    code = ""
    for _ in range(MAX_RETRY):
        candidate = generate_code()
        if candidate not in _links:
            code = candidate
            break
    if not code:
        raise HTTPException(status_code=500, detail="短码生成失败，请重试")

    _links[code] = target
    return CreateLinkResponse(code=code, short_url=f"/{code}", target=target)


@app.get("/{code}", summary="短链跳转")
def redirect(code: str):
    """访问 /abc123 就跳回原始长链接。"""
    target = _links.get(code)
    if target is None:
        raise HTTPException(status_code=404, detail="短链不存在或已失效")
    # 302 = 临时重定向。用 301（永久）浏览器会把结果缓存起来，
    # 之后你再改这条短链指向哪儿，老用户就永远看不到新地址了
    return RedirectResponse(url=target, status_code=302)


# 前端静态页面挂到根路径。
# 用绝对路径而不是 "static"，这样无论从哪个目录启动都能找到文件。
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
