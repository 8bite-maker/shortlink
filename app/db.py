"""数据库连接与会话管理。

v2 的核心变化：数据从「内存字典」搬到「SQLite 文件」，进程重启数据不再丢失。

SQLite 是什么：一个文件就是一个完整的数据库，零安装、零配置，
适合起步阶段。等以后并发量上来，再换成 PostgreSQL，代码几乎不用改。
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# 数据库文件放在项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "shortlink.db"

# SQLite 的连接串格式：sqlite:///<文件绝对路径>
DATABASE_URL = f"sqlite:///{DB_PATH}"

# engine 是"数据库连接池"，负责管理连接
# echo=True 会打印每条真实执行的 SQL，调试时很有用，生产环境要关掉
engine = create_engine(
    DATABASE_URL,
    # SQLite 默认禁止跨线程复用连接；FastAPI 处理请求时会切线程，所以要关掉这个检查
    connect_args={"check_same_thread": False},
    echo=False,
)

# 会话工厂：每次要操作数据库，就从这里开一个"会话"（可以理解为一笔事务）
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有表模型的基类。继承它，SQLAlchemy 才知道这个类对应一张表。"""


def get_db():
    """FastAPI 依赖注入用：每个请求分配一个独立会话，请求结束自动关闭。

    这样能保证：一个请求用一条连接，用完归还，不会泄漏。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
