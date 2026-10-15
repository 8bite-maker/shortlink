"""缓存与限流层。

生产环境用 Redis（独立进程、可持久化、多实例共享）；
本地没有 Redis 时自动降级到 fakeredis（纯 Python 内存实现）。
两者 API 完全一致，业务代码一行都不用改。

v3 用 Redis 做三件事：
1. 缓存「短码 → 原链接」，让跳转不再查数据库
2. 缓冲点击次数，攒一批再落库（避免每次点击都写磁盘）
3. 接口限流，防止被人恶意刷
"""

import os

import fakeredis
import redis

# 配置了 REDIS_URL 就连接真 Redis，否则用内存版
REDIS_URL = os.getenv("REDIS_URL", "")

# 链接缓存有效期：24 小时
CACHE_TTL = 60 * 60 * 24

# 点击缓冲的 key 前缀
CLICK_KEY_PREFIX = "clicks:"

# 限流规则：60 秒内最多创建 10 条短链 —— 具体数值待压测后调整
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 10


def _connect():
    """连接 Redis；连不上就降级到内存实现。

    返回 (客户端, 是否是真 Redis)。
    """
    if REDIS_URL:
        try:
            client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
            client.ping()
            return client, True
        except redis.RedisError:
            pass
    return fakeredis.FakeRedis(decode_responses=True), False


r, using_real_redis = _connect()


# ---------------- 链接缓存 ----------------

def get_cached_target(code: str) -> str | None:
    """从缓存取短码对应的原始链接，没有则返回 None。"""
    return r.get(f"link:{code}")


def cache_target(code: str, target: str) -> None:
    """写入缓存并设置过期时间（ex 参数）。

    为什么要设过期：缓存不可能无限大，没人访问的短链应该自己消失，
    否则内存迟早被塞满。TTL 就是"自动清理"机制。
    """
    r.set(f"link:{code}", target, ex=CACHE_TTL)


# ---------------- 点击缓冲 ----------------

def buffer_click(code: str) -> None:
    """点击次数先累加在内存里，完全不碰数据库。

    INCR 是 Redis 的原子自增命令：多个请求同时 INCR 同一个 key 也不会算错
    （数据库用 UPDATE ... SET clicks = clicks + 1 同样原子，但要走磁盘 IO）。
    """
    r.incr(CLICK_KEY_PREFIX + code)


def get_buffered_clicks(code: str) -> int:
    value = r.get(CLICK_KEY_PREFIX + code)
    return int(value) if value else 0


def drain_clicks() -> dict[str, int]:
    """取出所有缓冲的点击量并清空，供定时任务批量落库。

    GETDEL 是原子操作：取值和删除一步完成，
    避免并发场景下同一个增量被算两次。
    """
    drained: dict[str, int] = {}
    for key in r.scan_iter(match=CLICK_KEY_PREFIX + "*", count=100):
        code = key[len(CLICK_KEY_PREFIX):]
        value = r.getdel(key)
        if value:
            drained[code] = int(value)
    return drained


# ---------------- 接口限流 ----------------

def allow_request(identity: str) -> tuple[bool, int]:
    """固定窗口限流：同一身份在 RATE_LIMIT_WINDOW 秒内最多 RATE_LIMIT_MAX 次。

    返回 (是否放行, 剩余次数)。

    实现原理：
    - INCR 把计数加 1（原子操作，并发安全）
    - 如果是这一次窗口的第 1 次，就给它设个过期时间，窗口到了自动清零
    - 计数没超过阈值就放行
    """
    key = f"ratelimit:{identity}"
    current = r.incr(key)
    if current == 1:
        r.expire(key, RATE_LIMIT_WINDOW)
    remaining = max(0, RATE_LIMIT_MAX - current)
    return current <= RATE_LIMIT_MAX, remaining
