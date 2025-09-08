import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Union

import json_advanced as json
from pydantic import BaseModel, Field, field_serializer, field_validator
from singleton import Singleton

from .schemas import BaseEntitySchema
from .utils import basic, timezone


class TaskStatusEnum(StrEnum):
    none = "null"
    draft = "draft"
    init = "init"
    processing = "processing"
    paused = "paused"
    completed = "completed"
    done = "done"
    error = "error"

    @classmethod
    def finishes(cls) -> list["TaskStatusEnum"]:
        return [cls.done, cls.error, cls.completed]

    @property
    def is_done(self) -> bool:
        return self in self.finishes()


class SignalRegistry(metaclass=Singleton):
    def __init__(self) -> None:
        self.signal_map: dict[
            str,
            list[
                Callable[..., None] | Callable[..., Coroutine[Any, Any, None]]
            ],
        ] = {}


class TaskLogRecord(BaseModel):
    reported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.tz)
    )
    message: str
    task_status: TaskStatusEnum
    duration: int = 0
    log_type: str | None = None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TaskLogRecord):
            return (
                self.reported_at == other.reported_at
                and self.message == other.message
                and self.task_status == other.task_status
                and self.duration == other.duration
                # and self.data == other.data
            )
        return False

    def __hash__(self) -> int:
        return hash((
            self.reported_at,
            self.message,
            self.task_status,
            self.duration,
        ))


class TaskReference(BaseModel):
    task_id: str
    task_type: str

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TaskReference):
            return (
                self.task_id == other.task_id
                and self.task_type == other.task_type
            )
        return False

    def __hash__(self) -> int:
        return hash((self.task_id, self.task_type))

    async def get_task_item(self) -> BaseEntitySchema | None:
        task_classes = {
            subclass.__name__: subclass
            for subclass in basic.get_all_subclasses(TaskMixin)
            if issubclass(subclass, BaseEntitySchema)
        }

        task_class = task_classes.get(self.task_type)
        if not task_class:
            raise ValueError(f"Task type {self.task_type} is not supported.")

        task_item = await task_class.find_one(task_class.uid == self.task_id)
        if not task_item:
            raise ValueError(
                f"No task found with id {self.task_id} of type "
                f"{self.task_type}."
            )

        return task_item


class TaskReferenceList(BaseModel):
    tasks: list[Union[TaskReference, "TaskReferenceList"]] = []
    mode: Literal["serial", "parallel"] = "serial"

    async def get_task_item(self) -> list[BaseEntitySchema]:
        return [await task.get_task_item() for task in self.tasks]

    async def list_processing(self) -> None:
        task_items = [await task.get_task_item() for task in self.tasks]
        match self.mode:
            case "serial":
                for task_item in task_items:
                    await task_item.start_processing()  # type: ignore
            case "parallel":
                await asyncio.gather(*[
                    task.start_processing()  # type: ignore
                    for task in task_items
                ])


class TaskMixin(BaseModel):
    task_status: TaskStatusEnum = TaskStatusEnum.draft
    task_report: str | None = None
    task_progress: int = -1
    task_logs: list[TaskLogRecord] = []
    task_references: TaskReferenceList | None = None
    task_start_at: datetime | None = None
    task_end_at: datetime | None = None
    task_order_score: int = 0
    webhook_custom_headers: dict | None = None
    webhook_url: str | None = None

    @classmethod
    def get_queue_name(cls) -> str:
        return f"{cls.__name__.lower()}_queue"

    @property
    def item_webhook_url(self) -> str:
        return f"{self.item_url}/webhook"  # type: ignore

    @property
    def task_duration(self) -> int:
        if self.task_start_at:
            if self.task_end_at:
                return self.task_end_at - self.task_start_at
            return datetime.now(timezone.tz) - self.task_start_at
        return 0

    @field_validator("task_status", mode="before")
    @classmethod
    def validate_task_status(
        cls,
        value: object,
    ) -> "TaskStatusEnum":
        if isinstance(value, str):
            return TaskStatusEnum(value)
        return value

    @field_serializer("task_status")
    def serialize_task_status(self, value: object) -> str:
        if isinstance(value, TaskStatusEnum):
            return value.value
        return value

    @classmethod
    def signals(
        cls,
    ) -> list[Callable[..., None] | Callable[..., Coroutine[Any, Any, None]]]:
        registry = SignalRegistry()
        if cls.__name__ not in registry.signal_map:
            registry.signal_map[cls.__name__] = []
        return registry.signal_map[cls.__name__]

    @classmethod
    def add_signal(
        cls,
        signal: Callable[..., None] | Callable[..., Coroutine[Any, Any, None]],
    ) -> None:
        cls.signals().append(signal)

    @classmethod
    async def emit_signals(
        cls,
        task_instance: "TaskMixin",
        *,
        sync: bool = False,
        **kwargs: object,
    ) -> None:
        async def webhook_call(*args: object, **kwargs: object) -> None:
            import httpx

            try:
                await httpx.AsyncClient().post(*args, **kwargs)
            except Exception as e:
                import traceback

                traceback_str = "".join(traceback.format_tb(e.__traceback__))
                await task_instance.save_report(
                    f"An error occurred in webhook_call: {type(e)}: {e}",
                    emit=False,
                    log_type="webhook_error",
                )
                await task_instance.save()  # type: ignore
                logging.exception(
                    "\n".join([
                        "An error occurred in webhook_call:",
                        traceback_str,
                    ])
                )

        def webhook_task(webhook_url: str) -> None:
            return

        signals = []
        meta_data = getattr(task_instance, "meta_data", {}) or {}
        task_dict = task_instance.model_dump()
        task_dict.update({"task_type": task_instance.__class__.__name__})
        task_dict.update(kwargs)

        for webhook_url in [
            task_instance.webhook_url,
            meta_data.get("webhook"),
            meta_data.get("webhook_url"),
        ]:
            if not webhook_url:
                continue
            signals.append(
                webhook_call(
                    method="post",
                    url=webhook_url,
                    headers={
                        "Content-Type": "application/json",
                        **(task_instance.webhook_custom_headers or {}),
                    },
                    data=json.dumps(task_dict),
                )
            )

        signals += [
            (
                signal(task_instance)
                if asyncio.iscoroutinefunction(signal)
                else asyncio.to_thread(signal, task_instance)
            )
            for signal in cls.signals()
        ]

        if not sync:
            await asyncio.gather(*signals)
            return

        for signal in signals:
            await signal

    async def save_status(
        self,
        status: TaskStatusEnum,
        **kwargs: object,
    ) -> None:
        self.task_status = status
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=f"Status changed to {status}",
                log_type=kwargs.get("log_type", "status_update"),
            ),
            **kwargs,
        )

    async def add_reference(self, task_id: str, **kwargs: object) -> None:
        if self.task_references is None:
            self.task_references = TaskReferenceList()
        self.task_references.tasks.append(
            TaskReference(task_id=task_id, task_type=self.__class__.__name__)
        )
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=f"Added reference to task {task_id}",
                log_type=kwargs.get("log_type", "add_reference"),
            ),
            **kwargs,
        )

    async def save_report(self, report: str, **kwargs: object) -> None:
        self.task_report = report
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=report,
                log_type=kwargs.get("log_type", "report"),
            ),
            **kwargs,
        )

    async def add_log(
        self,
        log_record: TaskLogRecord,
        *,
        emit: bool = True,
        **kwargs: object,
    ) -> None:
        self.task_logs.append(log_record)
        if emit:
            await self.save_and_emit()

    async def start_processing(self, **kwargs: object) -> None:
        if self.task_references is None:
            raise NotImplementedError(
                "Subclasses should implement this method"
            )

        await self.task_references.list_processing()

    async def push_to_queue(
        self, redis_client: object, **kwargs: object
    ) -> None:
        """Add the task to Redis queue"""
        import json

        queue_name = f"{self.__class__.__name__.lower()}_queue"
        await redis_client.lpush(
            queue_name,
            json.dumps(kwargs | self.model_dump(include={"uid"}, mode="json")),
        )

    @basic.try_except_wrapper
    async def save_and_emit(self, **kwargs: object) -> None:
        if kwargs.get("sync"):
            await self.save()  # type: ignore
            await self.emit_signals(self, **kwargs)
        else:
            await asyncio.gather(
                self.save(),  # type: ignore
                self.emit_signals(self, **kwargs),
            )

    async def update_and_emit(self, **kwargs: object) -> None:
        if kwargs.get("task_status") in [
            TaskStatusEnum.done,
            TaskStatusEnum.error,
            TaskStatusEnum.completed,
        ]:
            kwargs["task_progress"] = kwargs.get("task_progress", 100)
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        if kwargs.get("task_report"):
            await self.add_log(
                TaskLogRecord(
                    task_status=self.task_status,
                    message=kwargs["task_report"],
                    log_type=kwargs.get("log_type", "status_update"),
                ),
                emit=False,
            )
        await self.save_and_emit()
