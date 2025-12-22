"""Task utilities and mixins for background processing."""

import asyncio
import logging
from collections.abc import Coroutine
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self, Union

import json_advanced as json
from pydantic import BaseModel, Field, field_serializer, field_validator
from singleton import Singleton

from .schemas import BaseEntitySchema
from .utils import basic, timezone


class TaskStatusEnum(StrEnum):
    """Enumeration of task status values."""

    none = "null"
    draft = "draft"
    init = "init"
    processing = "processing"
    paused = "paused"
    completed = "completed"
    done = "done"
    error = "error"

    @classmethod
    def finishes(cls) -> list[Self]:
        """
        Get list of statuses that indicate task completion.

        Returns:
            List of finished status enums (done, error, completed).

        """
        return [cls.done, cls.error, cls.completed]

    @property
    def is_done(self) -> bool:
        """Check if task status indicates completion."""
        return self in self.finishes()


class SignalRegistry(metaclass=Singleton):
    """Singleton registry for task signal handlers."""

    def __init__(self) -> None:
        """Initialize the signal registry."""
        self.signal_map: dict[str, list[basic.FunctionOrCoroutine]] = {}


class TaskLogRecord(BaseModel):
    """Record of a task log entry."""

    reported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.tz)
    )
    message: str
    task_status: TaskStatusEnum
    duration: int = 0
    log_type: str | None = None

    def __eq__(self, other: object) -> bool:
        """Check equality with another TaskLogRecord."""
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
        """Generate hash from task log record fields."""
        return hash((
            self.reported_at,
            self.message,
            self.task_status,
            self.duration,
        ))


class TaskReference(BaseModel):
    """Reference to another task."""

    task_id: str
    task_type: str

    def __eq__(self, other: object) -> bool:
        """Check equality with another TaskReference."""
        if isinstance(other, TaskReference):
            return (
                self.task_id == other.task_id
                and self.task_type == other.task_type
            )
        return False

    def __hash__(self) -> int:
        """Generate hash from task reference fields."""
        return hash((self.task_id, self.task_type))

    async def get_task_item(self) -> BaseEntitySchema | None:
        """Retrieve the referenced task item."""
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
    """List of task references with processing mode."""

    tasks: list[Union[TaskReference, "TaskReferenceList"]] = Field(
        default_factory=list
    )
    mode: Literal["serial", "parallel"] = "serial"

    async def get_task_item(self) -> list[BaseEntitySchema]:
        """Retrieve all referenced task items."""
        return [await task.get_task_item() for task in self.tasks]

    async def list_processing(self) -> None:
        """
        Process all tasks in the list according to mode.

        Mode can be 'serial' or 'parallel'.
        """
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
    """Mixin class for entities with task processing capabilities."""

    task_status: TaskStatusEnum = TaskStatusEnum.draft
    task_report: str | None = None
    task_progress: int = -1
    task_logs: list[TaskLogRecord] = Field(default_factory=list)
    task_references: TaskReferenceList | None = None
    task_start_at: datetime | None = None
    task_end_at: datetime | None = None
    task_order_score: int = 0
    webhook_custom_headers: dict | None = None
    webhook_url: str | None = None

    @property
    def webhook_exclude_fields(self) -> set[str] | None:
        """Get fields to exclude from webhook payload."""
        return None

    @property
    def webhook_include_fields(self) -> set[str] | None:
        """Get fields to include in webhook payload."""
        return None

    @classmethod
    def get_queue_name(cls) -> str:
        """Get the queue name for this task class."""
        return f"{cls.__name__.lower()}_queue"

    @property
    def item_webhook_url(self) -> str:
        """Get the webhook URL for this task item."""
        return f"{self.item_url}/webhook"  # type: ignore

    @property
    def task_duration(self) -> int:
        """Calculate task duration in seconds."""
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
    ) -> Self:
        """Validate and convert task status value."""
        if isinstance(value, str):
            return TaskStatusEnum(value)
        return value

    @field_serializer("task_status")
    def serialize_task_status(self, value: object) -> str:
        """Serialize task status to string."""
        if isinstance(value, TaskStatusEnum):
            return value.value
        return value

    @classmethod
    def signals(cls) -> list[basic.FunctionOrCoroutine]:
        """Get list of signal handlers for this task class."""
        registry = SignalRegistry()
        if cls.__name__ not in registry.signal_map:
            registry.signal_map[cls.__name__] = []
        return registry.signal_map[cls.__name__]

    @classmethod
    def add_signal(cls, signal: basic.FunctionOrCoroutine) -> None:
        """Add a signal handler to this task class."""
        cls.signals().append(signal)

    @classmethod
    async def emit_signals(
        cls, task_instance: Self, *, sync: bool = False, **kwargs: object
    ) -> None:
        """Emit all registered signals for the task instance."""

        async def webhook_call(
            *args: object, **kwargs: object
        ) -> dict[str, object]:
            import httpx

            try:
                response = await httpx.AsyncClient().post(*args, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                await task_instance.save_report(
                    "\n".join([
                        "An error occurred in webhook_call:",
                        f"{type(e)}: {e}",
                        f"{response.status_code}",
                        f"{response.text}",
                    ]),
                    emit=False,
                    log_type="webhook_error",
                )
                await task_instance.save()  # type: ignore
                logging.exception("An error occurred in webhook_call")
            except Exception as e:
                await task_instance.save_report(
                    f"An error occurred in webhook_call: {type(e)}: {e}",
                    emit=False,
                    log_type="webhook_error",
                )
                await task_instance.save()  # type: ignore
                logging.exception("An error occurred in webhook_call")

        signals: list[Coroutine[object, object, None]] = []
        meta_data = getattr(task_instance, "meta_data", {}) or {}
        task_dict = task_instance.model_dump(
            exclude=task_instance.webhook_exclude_fields,
            include=task_instance.webhook_include_fields,
        )
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

        await basic.gather_sync(signals, sync=sync)

    async def save_status(
        self, status: TaskStatusEnum, **kwargs: object
    ) -> None:
        """Save task status and log the change."""
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
        """Add a reference to another task."""
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
        """Save a task report and log it."""
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
        self, log_record: TaskLogRecord, *, emit: bool = True, **kwargs: object
    ) -> None:
        """Add a log record to the task."""
        self.task_logs.append(log_record)
        if emit:
            await self.save_and_emit()

    async def start_processing(self, **kwargs: object) -> None:
        """Start processing task references."""
        if self.task_references is None:
            raise NotImplementedError(
                "Subclasses should implement this method"
            )

        await self.task_references.list_processing()

    async def push_to_queue(
        self, redis_client: object, **kwargs: object
    ) -> None:
        """
        Add the task to Redis queue for background processing.

        Args:
            redis_client: Redis client instance.
            **kwargs: Additional task parameters.

        """
        import json

        queue_name = f"{self.__class__.__name__.lower()}_queue"
        await redis_client.lpush(
            queue_name,
            json.dumps(kwargs | self.model_dump(include={"uid"}, mode="json")),
        )

    @basic.try_except_wrapper
    async def save_and_emit(self, **kwargs: object) -> None:
        """Save task and emit signals."""
        if kwargs.get("sync"):
            await self.save()  # type: ignore
            await self.emit_signals(self, **kwargs)
        else:
            await asyncio.gather(
                self.save(),  # type: ignore
                self.emit_signals(self, **kwargs),
            )

    async def update_and_emit(self, **kwargs: object) -> None:
        """
        Update task fields and emit signals.

        Args:
            **kwargs: Field updates (task_status, task_progress,
                task_report, etc.).

        """
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
