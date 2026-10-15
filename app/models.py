"""数据表结构定义。

ORM 的思路：用 Python 类描述表，用对象操作行数据，不用手写 SQL。
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    """统一用 UTC 时间存库，避免时区混乱。展示时再转成本地时间。"""
    return datetime.now(timezone.utc)


class Link(Base):
    """短链表：一行 = 一条短链记录。"""

    __tablename__ = "links"

    # 主键：数据库自动分配的唯一年代号，跟短码无关，只用于内部标识
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 短码：unique=True 由数据库兜底保证绝不重复（应用层的重试是第一道防线，
    # 这里是第二道）；index=True 让"按短码查链接"这个最频繁的操作走索引
    code: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, nullable=False
    )

    # 原始长链接：2048 是主流浏览器的 URL 长度上限
    target: Mapped[str] = mapped_column(String(2048), nullable=False)

    # 点击次数 —— v2 的核心新字段
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Link code={self.code!r} clicks={self.clicks}>"
