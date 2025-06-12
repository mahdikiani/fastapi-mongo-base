from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import json_advanced as json
from pydantic import BaseModel

try:
    from server.db import redis
except ImportError:
    from redis import Redis

    redis = Redis()


def get_redis_value(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, Decimal):
        return str(value)
    elif isinstance(value, dict):
        return json.dumps(value)
    elif isinstance(value, list):
        return json.dumps(value)
    elif isinstance(value, Enum):
        return value.value
    elif value is None:
        return "None"

    return str(value)


def get_from_redis(value: bytes) -> str | Decimal | dict | list | None:
    value = value.decode()
    if value.startswith("{") or value.startswith("["):
        return json.loads(value)
    elif value.isdigit():
        return Decimal(value)
    elif value == "None":
        return None

    return value


class RedisModel(BaseModel):
    @classmethod
    async def get_by_key(
        cls, key: str, tenant_id: str | None = None
    ) -> "RedisModel":
        item = await redis.hgetall(cls.get_redis_class_key(key, tenant_id))
        if not item:
            return None
        return cls.from_redis_data(item, {"tenant_id": tenant_id})

    @classmethod
    def get_redis_class_key(
        cls, key: str | None = None, tenant_id: str | None = None
    ) -> str:
        class_key = cls.__name__.lower().replace("redismodel", "")
        if tenant_id:
            class_key = f"{tenant_id}:{class_key}"
        if key:
            return f"{class_key}:{key}"
        return class_key

    def get_redis_hash_data(self) -> dict:
        order_dict = self.model_dump()
        redis_data = {}
        for key, value in order_dict.items():
            redis_data[key] = get_redis_value(value)
        return redis_data

    @classmethod
    def from_redis_data(
        cls, data: dict[bytes, bytes], default_values: dict[str, Any] = None
    ) -> "RedisModel":
        if default_values is None:
            default_values = {}
        data = {k.decode(): get_from_redis(v) for k, v in data.items()}
        data = default_values | data
        return cls(**data)

    async def save_to_redis(self, **kwargs) -> "RedisModel":
        key = self.get_redis_class_key(
            self.uid, tenant_id=getattr(self, "tenant_id", None)
        )

        await redis.hset(key, mapping=self.get_redis_hash_data())
        return self

    async def delete_from_redis(self) -> "RedisModel":
        await redis.delete(
            self.get_redis_class_key(
                self.uid, tenant_id=getattr(self, "tenant_id", None)
            )
        )
        return self

    async def save_partial_key(self, key: str) -> "OrderRedisModel":
        value = get_redis_value(getattr(self, key))
        await redis.hset(
            self.get_redis_class_key(
                self.uid, tenant_id=getattr(self, "tenant_id", None)
            ),
            key,
            value,
        )
        return self

    async def get_partial_key(self, key: str) -> str:
        value = await redis.hget(
            self.get_redis_class_key(
                self.uid, tenant_id=getattr(self, "tenant_id", None)
            ),
            key,
        )
        return get_from_redis(value)

    async def publish_event(self, key: str | None = None) -> "OrderRedisModel":
        await redis.publish(
            self.get_redis_class_key(
                key, tenant_id=getattr(self, "tenant_id", None)
            ),
            self.model_dump_json(),
        )
        return self
