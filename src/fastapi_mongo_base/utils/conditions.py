import asyncio

from singleton import Singleton


class Conditions(metaclass=Singleton):
    _conditions: dict[str, asyncio.Condition] = {}

    def get_condition(self, uid: str) -> asyncio.Condition:
        """Get or create condition for an imagination"""
        if uid not in self._conditions:
            self._conditions[uid] = asyncio.Condition()
        return self._conditions[uid]

    def cleanup_condition(self, uid: str):
        self._conditions.pop(uid, None)

    async def release_condition(self, uid: str):
        if uid not in self._conditions:
            return

        condition = self.get_condition(uid)
        async with condition:
            condition.notify_all()
        self.cleanup_condition(uid)

    async def wait_condition(self, uid: str):
        condition = self.get_condition(uid)
        async with condition:
            await condition.wait()
        self.cleanup_condition(uid)
