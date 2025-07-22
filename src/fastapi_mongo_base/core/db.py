import logging

from beanie import init_beanie

from fastapi_mongo_base.models import BaseEntity
from fastapi_mongo_base.utils import basic

from .config import Settings


async def init_mongo_db(settings: Settings | None = None) -> object:
    try:
        from pymongo import AsyncMongoClient
    except ImportError:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            AsyncMongoClient = AsyncIOMotorClient
        except ImportError as e:
            raise ImportError("MongoDB is not installed") from e

    if settings is None:
        settings = Settings()

    client = AsyncMongoClient(settings.mongo_uri)
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


def init_redis(settings: Settings | None = None) -> tuple:
    try:
        from redis import Redis as RedisSync
        from redis.asyncio.client import Redis

        if settings is None:
            settings = Settings()

        redis_uri = getattr(settings, "redis_uri", None)
        if redis_uri:
            redis_sync: RedisSync = RedisSync.from_url(redis_uri)
            redis: Redis = Redis.from_url(redis_uri)

            return redis_sync, redis
    except (ImportError, AttributeError, Exception) as e:
        logging.error(f"Error initializing Redis: {e}")

    return None, None
