import json
import logging
import uuid

from pymongo import UpdateOne

from .core.config import Settings
from .models import BaseEntity
from .tasks import TaskStatusEnum
from .utils import bsontools

try:
    from server.db import redis
except ImportError:
    from redis import Redis

    redis = Redis()


class CachedMixin(BaseEntity):
    def is_done(self) -> bool:
        return (
            getattr(self, "task_status", "done") in TaskStatusEnum.Finishes()
            or self.is_deleted  # noqa: W503
        )

    async def is_cached(self) -> bool:
        return await redis.hexists(
            f"{Settings.project_name}:{self.__class__.__name__}_updates_hash",
            str(self.uid),
        )

    async def save(self, *args: object, **kwargs: object) -> object:
        if self.is_done():
            result = await super().save(*args, **kwargs)
            await redis.hdel(
                ":".join([
                    Settings.project_name,
                    self.__class__.__name__,
                    "updates_hash",
                ]),
                str(self.uid),
            )
            return result
        else:
            await redis.hset(
                ":".join([
                    Settings.project_name,
                    self.__class__.__name__,
                    "updates_hash",
                ]),
                str(self.uid),
                self.model_dump_json(),
            )

    @classmethod
    async def flush_queue_to_db(cls) -> None:
        # Get all items from the Redis hash in a single operation
        items_data: dict[bytes, bytes] = await redis.hgetall(
            ":".join([
                Settings.project_name,
                cls.__name__,
                "updates_hash",
            ])
        )

        # Clear the Redis hash after a successful batch write
        await redis.delete(
            ":".join([
                Settings.project_name,
                cls.__name__,
                "updates_hash",
            ])
        )

        if items_data:
            # Create a list of MongoDB upsert operations
            # for the bulk update/insert
            bulk_operations = []
            for uid_bytes, item_data in items_data.items():
                item_dict = json.loads(item_data)
                item = cls(**item_dict)
                uid = str(uuid.UUID(uid_bytes.decode("utf-8")))
                filter_query = {"uid": bsontools.get_bson_value(uid)}
                # Assuming the unique identifier is stored in _id
                logging.info(
                    f"Flushing item {uid} to DB "
                    f"{bsontools.get_bson_value(item.model_dump())}"
                )
                update_query = {
                    "$set": bsontools.get_bson_value(item.model_dump())
                }
                bulk_operations.append(
                    UpdateOne(filter_query, update_query, upsert=True)
                )

            # Perform the bulk upsert operation in a single call
            if bulk_operations:
                res = await cls.get_motor_collection().bulk_write(
                    bulk_operations,
                )
                logging.info(
                    f"Flushed {len(bulk_operations)} items to DB \n{res}"
                )

    @classmethod
    async def get_item(
        cls,
        *,
        uid: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        **kwargs: object,
    ) -> BaseEntity:
        if user_id is None and not kwargs.get("ignore_user_id"):
            raise ValueError("user_id is required")
        item_data = await redis.hget(
            ":".join([
                Settings.project_name,
                cls.__name__,
                "updates_hash",
            ]),
            str(uid),
        )
        if item_data:
            item_dict = json.loads(item_data)
            item = cls(**item_dict)
            if user_id and getattr(item, "user_id", None) != user_id:
                return None
            if tenant_id and getattr(item, "tenant_id", None) != tenant_id:
                return None
            return item
        return await super().get_item(
            uid=uid,
            tenant_id=tenant_id,
            user_id=user_id,
            is_deleted=is_deleted,
            **kwargs,
        )
