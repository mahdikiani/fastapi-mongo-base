"""Async conditions registry utilities."""

import asyncio
from typing import ClassVar

from singleton import Singleton


class Conditions(metaclass=Singleton):
    """Singleton class for managing asyncio conditions by UID."""

    _conditions: ClassVar[dict[str, asyncio.Condition]] = {}

    def get_condition(self, uid: str) -> asyncio.Condition:
        """
        Get or create condition for a UID.

        Args:
            uid: Unique identifier.

        Returns:
            asyncio.Condition instance.

        """
        if uid not in self._conditions:
            self._conditions[uid] = asyncio.Condition()
        return self._conditions[uid]

    def cleanup_condition(self, uid: str) -> None:
        """
        Remove condition for a UID.

        Args:
            uid: Unique identifier.

        """
        self._conditions.pop(uid, None)

    async def release_condition(self, uid: str) -> None:
        """
        Release and notify all waiters for a condition, then cleanup.

        Args:
            uid: Unique identifier.

        """
        if uid not in self._conditions:
            return

        condition = self.get_condition(uid)
        async with condition:
            condition.notify_all()
        self.cleanup_condition(uid)

    async def wait_condition(self, uid: str) -> None:
        """
        Wait for condition to be notified, then cleanup.

        Args:
            uid: Unique identifier.

        """
        condition = self.get_condition(uid)
        async with condition:
            await condition.wait()
        self.cleanup_condition(uid)
