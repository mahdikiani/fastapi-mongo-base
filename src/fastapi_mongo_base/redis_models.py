import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import json_advanced as json
from pydantic import BaseModel


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
        cls, key: str, business_name: str | None = None
    ) -> "RedisModel":
        item = await redis.hgetall(cls.get_redis_class_key(key, business_name))
        if not item:
            return None
        return cls.from_redis_data(item, {"business_name": business_name})

    @classmethod
    def get_redis_class_key(
        cls, key: str | None = None, business_name: str | None = None
    ) -> str:
        class_key = cls.__name__.lower().replace("redismodel", "")
        if business_name:
            class_key = f"{business_name}:{class_key}"
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
        cls, data: dict[bytes, bytes], default_values: dict[str, Any] = {}
    ) -> "RedisModel":
        data = {k.decode(): get_from_redis(v) for k, v in data.items()}
        data = default_values | data
        return cls(**data)

    async def save_to_redis(self, **kwargs) -> "OrderRedisModel":
        key = self.get_redis_class_key(
            self.uid, business_name=getattr(self, "business_name", None)
        )

        await redis.hset(key, mapping=self.get_redis_hash_data())
        return self

    async def delete_from_redis(self) -> "OrderRedisModel":
        await redis.delete(
            self.get_redis_class_key(
                self.uid, business_name=getattr(self, "business_name", None)
            )
        )
        return self

    async def save_partial_key(self, key: str) -> "OrderRedisModel":
        value = get_redis_value(getattr(self, key))
        await redis.hset(
            self.get_redis_class_key(
                self.uid, business_name=getattr(self, "business_name", None)
            ),
            key,
            value,
        )
        return self

    async def get_partial_key(self, key: str) -> str:
        value = await redis.hget(
            self.get_redis_class_key(
                self.uid, business_name=getattr(self, "business_name", None)
            ),
            key,
        )
        return get_from_redis(value)

    async def publish_event(self, key: str | None = None) -> "OrderRedisModel":
        await redis.publish(
            self.get_redis_class_key(
                key, business_name=getattr(self, "business_name", None)
            ),
            self.model_dump_json(),
        )
        return self
