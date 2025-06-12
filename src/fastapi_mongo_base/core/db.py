import logging

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from fastapi_mongo_base.models import BaseEntity
from fastapi_mongo_base.utils import basic

from .config import Settings


async def init_mongo_db(settings: Settings | None = None):
    if settings is None:
        settings = Settings()

    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        await client.server_info()
    except Exception as e:
        logging.error(f"Error initializing MongoDB: {e}")
        raise e

    db = client.get_database(settings.project_name)
    await init_beanie(
        database=db,
        document_models=[
            cls
            for cls in basic.get_all_subclasses(BaseEntity)
            if not (
                "Settings" in cls.__dict__
                and getattr(cls.Settings, "__abstract__", False)  # noqa: W503
            )
        ],
    )
    return db


def init_redis(settings: Settings | None = None):
    try:
        from redis import Redis as RedisSync
        from redis.asyncio.client import Redis

        if settings is None:
            settings = Settings()

        if settings.redis_uri:
            redis_sync: RedisSync = RedisSync.from_url(settings.redis_uri)
            redis: Redis = Redis.from_url(settings.redis_uri)
    except (ImportError, AttributeError, Exception) as e:
        logging.error(f"Error initializing Redis: {e}")
        redis_sync = None
        redis = None

    return redis_sync, redis
