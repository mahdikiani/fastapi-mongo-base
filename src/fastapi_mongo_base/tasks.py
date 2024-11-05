import asyncio
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Literal, Union

import json_advanced as json
from pydantic import BaseModel, Field, field_serializer, field_validator
from singleton import Singleton

from ._utils import aionetwork, basic
from .schemas import BaseEntitySchema


class TaskStatusEnum(str, Enum):
    none = "null"
    draft = "draft"
    init = "init"
    processing = "processing"
    paused = "paused"
    completed = "completed"
    done = "done"
    error = "error"

    @classmethod
    def Finishes(cls):
        return [cls.done, cls.error, cls.completed]

    @property
    def is_done(self):
        return self in self.Finishes()


class SignalRegistry(metaclass=Singleton):
    def __init__(self):
        self.signal_map: dict[
            str,
            list[Callable[..., None] | Callable[..., Coroutine[Any, Any, None]]],
        ] = {}


class TaskLogRecord(BaseModel):
    reported_at: datetime = Field(default_factory=datetime.now)
    message: str
    task_status: TaskStatusEnum
    duration: int = 0
    log_type: str | None = None
    # data: dict | None = None

    def __eq__(self, other):
        if isinstance(other, TaskLogRecord):
            return (
                self.reported_at == other.reported_at
                and self.message == other.message
                and self.task_status == other.task_status
                and self.duration == other.duration
                # and self.data == other.data
            )
        return False

    def __hash__(self):
        return hash((self.reported_at, self.message, self.task_status, self.duration))


class TaskReference(BaseModel):
    task_id: uuid.UUID
    task_type: str

    def __eq__(self, other):
        if isinstance(other, TaskReference):
            return self.task_id == other.task_id and self.task_type == other.task_type
        return False

    def __hash__(self):
        return hash((self.task_id, self.task_type))

    async def get_task_item(self) -> BaseEntitySchema | None:
        task_classes = {
            subclass.__name__: subclass
            for subclass in basic.get_all_subclasses(TaskMixin)
            if issubclass(subclass, BaseEntitySchema)
        }
        # task_classes = self._get_all_task_classes()

        task_class = task_classes.get(self.task_type)
        if not task_class:
            raise ValueError(f"Task type {self.task_type} is not supported.")

        task_item = await task_class.find_one(task_class.uid == self.task_id)
        if not task_item:
            raise ValueError(
                f"No task found with id {self.task_id} of type {self.task_type}."
            )

        return task_item


class TaskReferenceList(BaseModel):
    tasks: list[Union[TaskReference, "TaskReferenceList"]] = []
    mode: Literal["serial", "parallel"] = "serial"

    async def list_processing(self):
        task_items = [task.get_task_item() for task in self.tasks]
        match self.mode:
            case "serial":
                for task_item in task_items:
                    await task_item.start_processing()
            case "parallel":
                await asyncio.gather(*[task.start_processing() for task in task_items])


class TaskMixin(BaseModel):
    task_status: TaskStatusEnum = TaskStatusEnum.draft
    task_report: str | None = None
    task_progress: int = -1
    task_logs: list[TaskLogRecord] = []
    task_references: TaskReferenceList | None = None

    @property
    def webhook_url(self):
        return f"{self.item_url}/webhook"

    @field_validator("task_status", mode="before")
    def validate_task_status(cls, value):
        if isinstance(value, str):
            return TaskStatusEnum(value)
        return value

    @field_serializer("task_status")
    def serialize_task_status(self, value):
        if isinstance(value, TaskStatusEnum):
            return value.value
        return value

    @classmethod
    def signals(cls):
        registry = SignalRegistry()
        if cls.__name__ not in registry.signal_map:
            registry.signal_map[cls.__name__] = []
        return registry.signal_map[cls.__name__]

    @classmethod
    def add_signal(
        cls,
        signal: Callable[..., None] | Callable[..., Coroutine[Any, Any, None]],
    ):
        cls.signals().append(signal)

    @classmethod
    async def emit_signals(cls, task_instance: "TaskMixin", **kwargs):

        async def webhook_call(*args, **kwargs):
            try:
                await aionetwork.aio_request(*args, **kwargs)
            except Exception as e:
                await task_instance.save_report(
                    f"An error occurred in webhook_call: {e}",
                    emit=False,
                    log_type="webhook_error",
                )
                await task_instance.save()
                logging.error(f"An error occurred in webhook_call: {e}")
                return None

        webhook_signals = []
        if task_instance.meta_data:
            webhook = task_instance.meta_data.get(
                "webhook"
            ) or task_instance.meta_data.get("webhook_url")
            if webhook:
                task_dict = task_instance.model_dump()
                task_dict.update({"task_type": task_instance.__class__.__name__})
                task_dict.update(kwargs)
                webhook_signals.append(
                    webhook_call(
                        method="post",
                        url=webhook,
                        headers={"Content-Type": "application/json"},
                        data=json.dumps(task_dict),
                    )
                )

        signals = webhook_signals + [
            (
                signal(task_instance)
                if asyncio.iscoroutinefunction(signal)
                else asyncio.to_thread(signal, task_instance)
            )
            for signal in cls.signals()
        ]

        await asyncio.gather(*signals)

    async def save_status(
        self,
        status: TaskStatusEnum,
        **kwargs,
    ):
        self.task_status = status
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=f"Status changed to {status}",
                log_type=kwargs.get("log_type", "status_update"),
            ),
            **kwargs,
        )

    async def add_reference(self, task_id: uuid.UUID, **kwargs):
        self.task_references.append(task_id)
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=f"Added reference to task {task_id}",
                log_type=kwargs.get("log_type", "add_reference"),
            ),
            **kwargs,
        )

    async def save_report(self, report: str, **kwargs):
        self.task_report = report
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=report,
                log_type=kwargs.get("log_type", "report"),
            ),
            **kwargs,
        )

    async def add_log(self, log_record: TaskLogRecord, *, emit: bool = True, **kwargs):
        self.task_logs.append(log_record)
        if emit:
            # await self.emit_signals(self)
            await self.save_and_emit()

    async def start_processing(self):
        if self.task_references is None:
            raise NotImplementedError("Subclasses should implement this method")

        await self.task_references.list_processing()

    @basic.try_except_wrapper
    async def save_and_emit(self):
        await asyncio.gather(self.save(), self.emit_signals(self))

    async def update_and_emit(self, **kwargs):
        if kwargs.get("task_status") in [
            TaskStatusEnum.done,
            TaskStatusEnum.error,
            TaskStatusEnum.completed,
        ]:
            kwargs["task_progress"] = kwargs.get("task_progress", 100)
            # kwargs["task_report"] = kwargs.get("task_report")
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
