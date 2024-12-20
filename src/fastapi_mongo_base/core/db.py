from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from fastapi_mongo_base._utils import basic
from fastapi_mongo_base.models import BaseEntity

try:
    from server.config import Settings
except ImportError:
    from .config import Settings


async def init_mongo_db():
    client = AsyncIOMotorClient(Settings.mongo_uri)
    db = client.get_database(Settings.project_name)
    await init_beanie(
        database=db,
        document_models=[
            cls
            for cls in basic.get_all_subclasses(BaseEntity)
            if not (
                hasattr(cls, "Settings")
                and getattr(cls.Settings, "__abstract__", False)
            )
        ],
    )
    return db


def init_redis():
    try:
        from redis import Redis as RedisSync
        from redis.asyncio.client import Redis

        if getattr(Settings, "redis_uri"):
            redis_sync: RedisSync = RedisSync.from_url(Settings.redis_uri)
            redis: Redis = Redis.from_url(Settings.redis_uri)
    except ImportError:
        redis_sync = None
        redis = None
    ex

    return redis_sync, redis
