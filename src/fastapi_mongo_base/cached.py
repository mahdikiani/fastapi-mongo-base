import json
import logging
import uuid

from pymongo import UpdateOne

from ._utils import bsontools
from .models import BaseEntity
from .tasks import TaskStatusEnum

try:
    from server.config import Settings
except ImportError:

    class Settings:
        project_name = "fastapi-base-mongo"
        redis_expire = 60


try:
    from server.db import redis
except ImportError:
    from redis import Redis

    redis = Redis()


class CachedMixin(BaseEntity):
    def is_done(self):
        return (
            getattr(self, "task_status", "done") in TaskStatusEnum.Finishes()
            or self.is_deleted
        )

    async def is_cached(self):
        return await redis.hexists(
            f"{Settings.project_name}:{self.__class__.__name__}_updates_hash",
            str(self.uid),
        )

    async def save(self, *args, **kwargs):
        if self.is_done():
            result = await super().save(*args, **kwargs)
            await redis.hdel(
                f"{Settings.project_name}:{self.__class__.__name__}_updates_hash",
                str(self.uid),
            )
            return result
        else:
            await redis.hset(
                f"{Settings.project_name}:{self.__class__.__name__}_updates_hash",
                str(self.uid),
                self.model_dump_json(),
            )

    @classmethod
    async def flush_queue_to_db(cls):
        # Get all items from the Redis hash in a single operation
        items_data: dict[bytes, bytes] = await redis.hgetall(
            f"{Settings.project_name}:{cls.__name__}_updates_hash"
        )

        # Clear the Redis hash after a successful batch write
        await redis.delete(f"{Settings.project_name}:{cls.__name__}_updates_hash")

        if items_data:
            # Create a list of MongoDB upsert operations for the bulk update/insert
            bulk_operations = []
            for uid_bytes, item_data in items_data.items():
                item_dict = json.loads(item_data)
                item = cls(**item_dict)
                uid = uuid.UUID(uid_bytes.decode("utf-8"))
                filter_query = {"uid": bsontools.get_bson_value(uid)}
                # Assuming the unique identifier is stored in _id
                logging.info(
                    f"Flushing item {uid} to DB {bsontools.get_bson_value(item.model_dump())}"
                )
                update_query = {"$set": bsontools.get_bson_value(item.model_dump())}
                bulk_operations.append(
                    UpdateOne(filter_query, update_query, upsert=True)
                )

            # Perform the bulk upsert operation in a single call
            if bulk_operations:
                res = await cls.get_motor_collection().bulk_write(bulk_operations)
                logging.info(f"Flushed {len(bulk_operations)} items to DB \n{res}")

    @classmethod
    async def get_item(
        cls,
        uid,
        user_id: uuid.UUID = None,
        business_name: str = None,
        is_deleted: bool = False,
        *args,
        **kwargs,
    ) -> BaseEntity:
        if user_id == None and kwargs.get("ignore_user_id") != True:
            raise ValueError("user_id is required")
        item_data = await redis.hget(
            f"{Settings.project_name}:{cls.__name__}_updates_hash", str(uid)
        )
        if item_data:
            item_dict = json.loads(item_data)
            item = cls(**item_dict)
            if user_id and getattr(item, "user_id", None) != user_id:
                return None
            if getattr(item, "business_name", None) != business_name:
                return None
            return item
        return await super().get_item(
            uid,
            business_name=business_name,
            user_id=user_id,
            is_deleted=is_deleted,
            *args,
            **kwargs,
        )
