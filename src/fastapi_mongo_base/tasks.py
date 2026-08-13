"""Task utilities and mixins for background processing."""

import asyncio
import inspect
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Union, cast

import json_advanced as json
from pydantic import BaseModel, Field, field_serializer, field_validator
from singleton import Singleton

from .i18n.timezone import serialize_response_datetime
from .schemas import BaseEntitySchema
from .utils import basic, timezone

logger = logging.getLogger(__name__)


class TaskStatusEnum(str, Enum):
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
    def finishes(cls) -> list["TaskStatusEnum"]:
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

    @field_serializer("reported_at", when_used="json")
    def serialize_reported_at(self, dt: datetime) -> str:
        """Serialize log timestamps in the request timezone."""
        return serialize_response_datetime(dt)


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
        task_classes: dict[str, type] = {
            subclass.__name__: subclass
            for subclass in basic.get_all_subclasses(TaskMixin)
            if issubclass(subclass, BaseEntitySchema)
        }

        task_class = task_classes.get(self.task_type)
        if not task_class:
            raise ValueError(f"Task type {self.task_type} is not supported.")

        task_item = await cast("Any", task_class).find_one(
            cast("Any", task_class).uid == self.task_id
        )
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

    async def get_task_item(self) -> list[object]:
        """Retrieve all referenced task items."""
        items: list[object] = []
        for task in self.tasks:
            item = await task.get_task_item()
            if isinstance(item, list):
                items.extend(item)
            elif item is not None:
                items.append(item)
        return items

    async def list_processing(self) -> None:
        """
        Process all tasks in the list according to mode.

        Mode can be 'serial' or 'parallel'.
        """
        task_items = await self.get_task_item()
        match self.mode:
            case "serial":
                for task_item in task_items:
                    await cast("Any", task_item).start_processing()
            case "parallel":
                await asyncio.gather(*[
                    cast("Any", task).start_processing() for task in task_items
                ])


class TaskCreateFieldsMixin(BaseModel):
    """Common optional fields accepted when creating async tasks."""

    user_id: str | None = Field(
        None,
        description="Target user id (omitted = authenticated user)",
    )
    webhook_url: str | None = Field(
        None,
        description="URL to notify when the task completes",
    )
    webhook_custom_headers: dict | None = Field(
        None,
        description="Custom headers to send in webhook requests",
    )
    meta_data: dict | None = Field(
        None,
        description=(
            "Client metadata stored on the task and echoed in webhooks"
        ),
    )


class TaskMixin(TaskCreateFieldsMixin):
    """Mixin class for entities with task processing capabilities."""

    task_status: TaskStatusEnum = TaskStatusEnum.draft
    task_report: str | None = None
    task_progress: int = -1
    task_logs: list[TaskLogRecord] = Field(default_factory=list)
    task_references: TaskReferenceList | None = None
    task_start_at: datetime | None = None
    task_end_at: datetime | None = None
    task_order_score: int = 0

    @property
    def webhook_exclude_fields(self) -> set[str] | None:
        """Fields to exclude from webhook payload."""
        return None

    @property
    def webhook_include_fields(self) -> set[str] | None:
        """Fields to include in webhook payload."""
        return None

    @classmethod
    def get_queue_name(cls) -> str:
        """Get the queue name for this task class."""
        return f"{cls.__name__.lower()}_queue"

    @property
    def item_webhook_url(self) -> str:
        """Webhook URL for this task item."""
        item_url = getattr(self, "item_url", "")
        return f"{item_url}/webhook"

    @property
    def task_duration(self) -> object:
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
    ) -> object:
        """Validate and convert task status value."""
        if isinstance(value, str):
            return TaskStatusEnum(value)
        return value

    @field_serializer("task_status")
    def serialize_task_status(self, value: object) -> object:
        """Serialize task status to string."""
        if isinstance(value, TaskStatusEnum):
            return value.value
        return value

    @field_serializer("task_start_at", "task_end_at", when_used="json")
    def serialize_task_datetimes(
        self,
        dt: datetime | None,
    ) -> str | None:
        """Serialize task timestamps in the request timezone."""
        if dt is None:
            return None
        return serialize_response_datetime(dt)

    @classmethod
    def signals(cls) -> list[basic.FunctionOrCoroutine]:
        """Get list of signal handlers for this task class."""
        registry = cast("SignalRegistry", SignalRegistry())
        if cls.__name__ not in registry.signal_map:
            registry.signal_map[cls.__name__] = []
        return registry.signal_map[cls.__name__]

    @classmethod
    def add_signal(cls, signal: basic.FunctionOrCoroutine) -> None:
        """Add a signal handler to this task class."""
        cls.signals().append(signal)

    @classmethod
    async def emit_signals(
        cls, task_instance: object, *, sync: bool = False, **kwargs: object
    ) -> None:
        """Emit all registered signals for the task instance."""
        task = cast("Any", task_instance)

        async def webhook_call(
            *_args: object, **kwargs: object
        ) -> dict[str, object] | None:
            import httpx

            response: httpx.Response | None = None
            try:
                response = await httpx.AsyncClient().post(
                    **cast("Any", kwargs),
                )
                response.raise_for_status()
                return cast("dict[str, object]", response.json())
            except httpx.HTTPStatusError as e:
                status = response.status_code if response is not None else "?"
                text = response.text if response is not None else ""
                await task.save_report(
                    "\n".join([
                        "An error occurred in webhook_call:",
                        f"{type(e)}: {e}",
                        f"{status}",
                        f"{text}",
                    ]),
                    emit=False,
                    log_type="webhook_error",
                )
                await task.save()
                logger.exception("An error occurred in webhook_call")
                return None
            except Exception as e:
                await task.save_report(
                    f"An error occurred in webhook_call: {type(e)}: {e}",
                    emit=False,
                    log_type="webhook_error",
                )
                await task.save()
                logger.exception("An error occurred in webhook_call")
                return None

        signals: list[object] = []
        meta_data = getattr(task, "meta_data", {}) or {}
        task_dict = task.model_dump(
            exclude=task.webhook_exclude_fields,
            include=task.webhook_include_fields,
        )
        task_dict.update({"task_type": task.__class__.__name__})
        task_dict.update(kwargs)

        for webhook_url in [
            task.webhook_url,
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
                        **(task.webhook_custom_headers or {}),
                    },
                    data=json.dumps(task_dict),
                )
            )

        for signal in cls.signals():
            if inspect.iscoroutinefunction(signal):
                signals.append(signal(task))
            else:
                signals.append(asyncio.to_thread(signal, task))

        await basic.gather_sync(cast("list[Any]", signals), sync=sync)

    async def save_status(
        self, status: TaskStatusEnum, **kwargs: object
    ) -> None:
        """Save task status and log the change."""
        self.task_status = status
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=f"Status changed to {status.value}",
                log_type=cast(
                    "str | None", kwargs.get("log_type", "status_update")
                ),
            ),
            **cast("Any", kwargs),
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
                log_type=cast(
                    "str | None", kwargs.get("log_type", "add_reference")
                ),
            ),
            **cast("Any", kwargs),
        )

    async def save_report(self, report: str, **kwargs: object) -> None:
        """Save a task report and log it."""
        self.task_report = report
        await self.add_log(
            TaskLogRecord(
                task_status=self.task_status,
                message=report,
                log_type=cast("str | None", kwargs.get("log_type", "report")),
            ),
            **cast("Any", kwargs),
        )

    async def add_log(
        self,
        log_record: TaskLogRecord,
        *,
        emit: bool = True,
        **_kwargs: object,
    ) -> None:
        """Add a log record to the task."""
        self.task_logs.append(log_record)
        if emit:
            await self.save_and_emit()

    async def start_processing(self, **_kwargs: object) -> None:
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
        await cast("Any", redis_client).lpush(
            queue_name,
            json.dumps(kwargs | self.model_dump(include={"uid"}, mode="json")),
        )

    @basic.try_except_wrapper
    async def save_and_emit(self, **kwargs: object) -> None:
        """Save task and emit signals."""
        me = cast("Any", self)
        if kwargs.get("sync"):
            await me.save()
            await self.emit_signals(self, **cast("Any", kwargs))
        else:
            await asyncio.gather(
                me.save(),
                self.emit_signals(self, **cast("Any", kwargs)),
            )

    async def update_and_emit(self, **kwargs: object) -> None:
        """
        Update task fields and emit signals.

        Args:
            **kwargs: Field updates (task_status, task_progress,
                task_report, etc.).

        """
        if kwargs.get("task_status") in {
            TaskStatusEnum.done,
            TaskStatusEnum.error,
            TaskStatusEnum.completed,
        }:
            kwargs["task_progress"] = kwargs.get("task_progress", 100)
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        if kwargs.get("task_report"):
            await self.add_log(
                TaskLogRecord(
                    task_status=self.task_status,
                    message=str(kwargs["task_report"]),
                    log_type=cast(
                        "str | None",
                        kwargs.get("log_type", "status_update"),
                    ),
                ),
                emit=False,
            )
        await self.save_and_emit()
