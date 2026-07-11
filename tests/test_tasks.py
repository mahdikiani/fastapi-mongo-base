"""Tests for task utilities."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.fastapi_mongo_base.schemas import BaseEntitySchema
from src.fastapi_mongo_base.tasks import (
    SignalRegistry,
    TaskCreateFieldsMixin,
    TaskLogRecord,
    TaskMixin,
    TaskReference,
    TaskReferenceList,
    TaskStatusEnum,
)
from src.fastapi_mongo_base.utils import timezone

# ── Helper classes ──────────────────────────────────────────────


class _SimpleTask(TaskMixin):
    """Concrete TaskMixin subclass for basic tests."""

    uid: str = "test-uid-123"

    @property
    def item_url(self) -> str:
        return f"https://example.com/api/tasks/{self.uid}"


class _RefEntity(TaskMixin, BaseEntitySchema):
    """Entity combining TaskMixin and BaseEntitySchema for reference tests."""

    meta_data: dict | None = None


# ── TaskStatusEnum ──────────────────────────────────────────────


class TestTaskStatusEnum:
    """Tests for TaskStatusEnum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert TaskStatusEnum.none == "null"
        assert TaskStatusEnum.draft == "draft"
        assert TaskStatusEnum.init == "init"
        assert TaskStatusEnum.processing == "processing"
        assert TaskStatusEnum.paused == "paused"
        assert TaskStatusEnum.completed == "completed"
        assert TaskStatusEnum.done == "done"
        assert TaskStatusEnum.error == "error"

    def test_finishes(self) -> None:
        """Test finishes."""
        assert TaskStatusEnum.finishes() == [
            TaskStatusEnum.done,
            TaskStatusEnum.error,
            TaskStatusEnum.completed,
        ]

    def test_is_done_true_for_finished(self) -> None:
        """Test is_done true for finished states."""
        assert TaskStatusEnum.done.is_done is True
        assert TaskStatusEnum.error.is_done is True
        assert TaskStatusEnum.completed.is_done is True

    def test_is_done_false_for_incomplete(self) -> None:
        """Test is_done false for incomplete states."""
        assert TaskStatusEnum.none.is_done is False
        assert TaskStatusEnum.draft.is_done is False
        assert TaskStatusEnum.init.is_done is False
        assert TaskStatusEnum.processing.is_done is False
        assert TaskStatusEnum.paused.is_done is False


# ── SignalRegistry ──────────────────────────────────────────────


class TestSignalRegistry:
    """Tests for SignalRegistry singleton."""

    def test_singleton_behavior(self) -> None:
        """Test singleton behavior."""
        reg1 = SignalRegistry()
        reg2 = SignalRegistry()
        assert reg1 is reg2

    def test_signal_map_is_mutable(self) -> None:
        """Test signal map is mutable."""
        reg = SignalRegistry()
        reg.signal_map["test_key"] = []
        assert "test_key" in reg.signal_map
        assert reg.signal_map["test_key"] == []


# ── TaskLogRecord ───────────────────────────────────────────────


class TestTaskLogRecord:
    """Tests for TaskLogRecord model."""

    def test_model_creation(self) -> None:
        """Test model creation."""
        record = TaskLogRecord(
            message="hello",
            task_status=TaskStatusEnum.done,
            duration=42,
            log_type="custom",
        )
        assert record.message == "hello"
        assert record.task_status == TaskStatusEnum.done
        assert record.duration == 42
        assert record.log_type == "custom"
        assert isinstance(record.reported_at, datetime)

    def test_defaults(self) -> None:
        """Test defaults."""
        record = TaskLogRecord(message="test", task_status=TaskStatusEnum.init)
        assert record.duration == 0
        assert record.log_type is None

    def test_reported_at_has_timezone(self) -> None:
        """Test reported_at has timezone."""
        record = TaskLogRecord(message="now", task_status=TaskStatusEnum.draft)
        assert record.reported_at.tzinfo is not None

    def test_eq_equal(self) -> None:
        """Test equality of equal records."""
        dt = datetime.now(timezone.tz)
        r1 = TaskLogRecord(
            reported_at=dt,
            message="m",
            task_status=TaskStatusEnum.done,
            duration=5,
        )
        r2 = TaskLogRecord(
            reported_at=dt,
            message="m",
            task_status=TaskStatusEnum.done,
            duration=5,
        )
        assert r1 == r2

    def test_eq_not_equal(self) -> None:
        """Test inequality of different records."""
        r1 = TaskLogRecord(message="a", task_status=TaskStatusEnum.done)
        r2 = TaskLogRecord(message="b", task_status=TaskStatusEnum.done)
        assert r1 != r2

    def test_eq_wrong_type(self) -> None:
        """Test equality with wrong type."""
        record = TaskLogRecord(message="x", task_status=TaskStatusEnum.draft)
        assert record != "not-a-record"

    def test_hash_equal_records(self) -> None:
        """Test hash of equal records."""
        dt = datetime.now(timezone.tz)
        r1 = TaskLogRecord(
            reported_at=dt,
            message="m",
            task_status=TaskStatusEnum.done,
            duration=5,
        )
        r2 = TaskLogRecord(
            reported_at=dt,
            message="m",
            task_status=TaskStatusEnum.done,
            duration=5,
        )
        assert hash(r1) == hash(r2)

    def test_hash_different_records(self) -> None:
        """Test hash of different records."""
        r1 = TaskLogRecord(message="x", task_status=TaskStatusEnum.done)
        r2 = TaskLogRecord(message="y", task_status=TaskStatusEnum.done)
        assert hash(r1) != hash(r2)


# ── TaskReference ───────────────────────────────────────────────


class TestTaskReference:
    """Tests for TaskReference model."""

    def test_model_creation(self) -> None:
        """Test model creation."""
        ref = TaskReference(task_id="id-1", task_type="MyTask")
        assert ref.task_id == "id-1"
        assert ref.task_type == "MyTask"

    def test_eq_equal(self) -> None:
        """Test equality of equal references."""
        r1 = TaskReference(task_id="x", task_type="T")
        r2 = TaskReference(task_id="x", task_type="T")
        assert r1 == r2

    def test_eq_not_equal(self) -> None:
        """Test inequality of different references."""
        r1 = TaskReference(task_id="x", task_type="T")
        r2 = TaskReference(task_id="y", task_type="T")
        assert r1 != r2

    def test_eq_wrong_type(self) -> None:
        """Test equality with wrong type."""
        ref = TaskReference(task_id="x", task_type="T")
        assert ref != "something-else"

    def test_hash(self) -> None:
        """Test hash."""
        r1 = TaskReference(task_id="x", task_type="T")
        r2 = TaskReference(task_id="x", task_type="T")
        assert hash(r1) == hash(r2)

    @pytest.mark.asyncio
    async def test_get_task_item_success(self) -> None:
        """Test get_task_item success."""
        ref = TaskReference(task_id="uid-abc", task_type="_RefEntity")

        mock_item = MagicMock()
        mock_item.uid = "uid-abc"

        with (
            patch.object(_RefEntity, "uid", "some_uid", create=True),
            patch.object(
                _RefEntity, "find_one", new_callable=AsyncMock, create=True
            ) as mock_find,
        ):
            mock_find.return_value = mock_item
            result = await ref.get_task_item()

        assert result is mock_item

    @pytest.mark.asyncio
    async def test_get_task_item_unsupported_type(self) -> None:
        """Test get_task_item unsupported type."""
        ref = TaskReference(task_id="x", task_type="NoSuchClass")
        with pytest.raises(ValueError, match="is not supported"):
            await ref.get_task_item()

    @pytest.mark.asyncio
    async def test_get_task_item_not_found(self) -> None:
        """Test get_task_item not found."""
        ref = TaskReference(task_id="missing", task_type="_RefEntity")

        with (
            patch.object(_RefEntity, "uid", "some_uid", create=True),
            patch.object(
                _RefEntity, "find_one", new_callable=AsyncMock, create=True
            ) as mock_find,
        ):
            mock_find.return_value = None
            with pytest.raises(ValueError, match="No task found"):
                await ref.get_task_item()


# ── TaskReferenceList ───────────────────────────────────────────


class TestTaskReferenceList:
    """Tests for TaskReferenceList model."""

    def test_defaults(self) -> None:
        """Test defaults."""
        ref_list = TaskReferenceList()
        assert ref_list.tasks == []
        assert ref_list.mode == "serial"

    def test_with_tasks(self) -> None:
        """Test with tasks."""
        r1 = TaskReference(task_id="a", task_type="T")
        r2 = TaskReference(task_id="b", task_type="T")
        ref_list = TaskReferenceList(tasks=[r1, r2], mode="parallel")
        assert len(ref_list.tasks) == 2
        assert ref_list.mode == "parallel"

    @pytest.mark.asyncio
    async def test_get_task_items(self) -> None:
        """Test get_task_items."""
        mock_item1 = MagicMock()
        mock_item2 = MagicMock()

        ref1 = TaskReference(task_id="uid-1", task_type="_RefEntity")
        ref2 = TaskReference(task_id="uid-2", task_type="_RefEntity")
        ref_list = TaskReferenceList(tasks=[ref1, ref2])

        with (
            patch.object(_RefEntity, "uid", "some_uid", create=True),
            patch.object(
                _RefEntity, "find_one", new_callable=AsyncMock, create=True
            ) as mock_find,
        ):
            mock_find.side_effect = [mock_item1, mock_item2]
            results = await ref_list.get_task_item()

        assert results == [mock_item1, mock_item2]

    @pytest.mark.asyncio
    async def test_list_processing_serial(self) -> None:
        """Test list processing serial."""
        item1 = MagicMock()
        item1.start_processing = AsyncMock()
        item2 = MagicMock()
        item2.start_processing = AsyncMock()

        ref1 = MagicMock(spec=TaskReference)
        ref1.get_task_item = AsyncMock(return_value=item1)
        ref2 = MagicMock(spec=TaskReference)
        ref2.get_task_item = AsyncMock(return_value=item2)

        ref_list = TaskReferenceList(tasks=[ref1, ref2], mode="serial")
        await ref_list.list_processing()

        item1.start_processing.assert_awaited_once()
        item2.start_processing.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_processing_parallel(self) -> None:
        """Test list processing parallel."""
        item1 = MagicMock()
        item1.start_processing = AsyncMock()
        item2 = MagicMock()
        item2.start_processing = AsyncMock()

        ref1 = MagicMock(spec=TaskReference)
        ref1.get_task_item = AsyncMock(return_value=item1)
        ref2 = MagicMock(spec=TaskReference)
        ref2.get_task_item = AsyncMock(return_value=item2)

        ref_list = TaskReferenceList(tasks=[ref1, ref2], mode="parallel")
        await ref_list.list_processing()

        item1.start_processing.assert_awaited_once()
        item2.start_processing.assert_awaited_once()


# ── TaskCreateFieldsMixin ──────────────────────────────────────


class TestTaskCreateFieldsMixin:
    """Tests for TaskCreateFieldsMixin model."""

    def test_defaults(self) -> None:
        """Test defaults."""
        m = TaskCreateFieldsMixin()
        assert m.user_id is None
        assert m.webhook_url is None
        assert m.webhook_custom_headers is None
        assert m.meta_data is None

    def test_with_values(self) -> None:
        """Test with values."""
        m = TaskCreateFieldsMixin(
            user_id="u1",
            webhook_url="https://hook.example.com",
            webhook_custom_headers={"X-Api-Key": "secret"},
            meta_data={"foo": "bar"},
        )
        assert m.user_id == "u1"
        assert m.webhook_url == "https://hook.example.com"
        assert m.webhook_custom_headers == {"X-Api-Key": "secret"}
        assert m.meta_data == {"foo": "bar"}


# ── TaskMixin ──────────────────────────────────────────────────


class TestTaskMixin:
    """Tests for TaskMixin."""

    def test_defaults(self) -> None:
        """Test defaults."""
        task = _SimpleTask()
        assert task.task_status == TaskStatusEnum.draft
        assert task.task_report is None
        assert task.task_progress == -1
        assert task.task_logs == []
        assert task.task_references is None
        assert task.task_start_at is None
        assert task.task_end_at is None
        assert task.task_order_score == 0

    # ── Properties ──

    def test_webhook_exclude_fields(self) -> None:
        """Test webhook exclude fields."""
        assert _SimpleTask().webhook_exclude_fields is None

    def test_webhook_include_fields(self) -> None:
        """Test webhook include fields."""
        assert _SimpleTask().webhook_include_fields is None

    def test_get_queue_name(self) -> None:
        """Test get_queue_name."""
        assert _SimpleTask.get_queue_name() == "_simpletask_queue"

    def test_item_webhook_url(self) -> None:
        """Test item webhook URL."""
        task = _SimpleTask(uid="my-uid")
        expected = "https://example.com/api/tasks/my-uid/webhook"
        assert task.item_webhook_url == expected

    def test_task_duration_no_times(self) -> None:
        """Test task duration with no times."""
        task = _SimpleTask()
        assert task.task_duration == 0

    def test_task_duration_with_start_only(self) -> None:
        """Test task duration with start only."""
        start = datetime.now(timezone.tz) - timedelta(seconds=30)
        task = _SimpleTask(task_start_at=start)
        duration = task.task_duration
        assert isinstance(duration, timedelta)
        assert 29 <= duration.total_seconds() <= 31

    def test_task_duration_with_start_and_end(self) -> None:
        """Test task duration with start and end."""
        start = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.tz)
        end = datetime(2024, 6, 1, 10, 5, 0, tzinfo=timezone.tz)
        task = _SimpleTask(task_start_at=start, task_end_at=end)
        assert task.task_duration == timedelta(seconds=300)

    # ── validate_task_status ──

    def test_validate_task_status_from_string(self) -> None:
        """Test validate_task_status from string."""
        result = _SimpleTask.validate_task_status("draft")
        assert result == TaskStatusEnum.draft

    def test_validate_task_status_passthrough_enum(self) -> None:
        """Test validate_task_status passthrough enum."""
        result = _SimpleTask.validate_task_status(TaskStatusEnum.error)
        assert result == TaskStatusEnum.error

    def test_validate_task_status_via_init(self) -> None:
        """Test validate_task_status via init."""
        task = _SimpleTask(task_status="completed")
        assert task.task_status == TaskStatusEnum.completed

    # ── serialize_task_status ──

    def test_serialize_task_status_enum(self) -> None:
        """Test serialize_task_status enum."""
        task = _SimpleTask(task_status=TaskStatusEnum.processing)
        result = task.serialize_task_status(task.task_status)
        assert result == "processing"

    def test_serialize_task_status_raw(self) -> None:
        """Test serialize_task_status raw."""
        task = _SimpleTask()
        result = task.serialize_task_status("raw_value")
        assert result == "raw_value"

    def test_serialize_task_status_in_dump(self) -> None:
        """Test serialize_task_status in dump."""
        task = _SimpleTask(task_status=TaskStatusEnum.paused)
        dumped = task.model_dump(mode="json")
        assert dumped["task_status"] == "paused"

    # ── signals / add_signal ──

    def test_signals_returns_list(self) -> None:
        """Test signals returns list."""
        sigs = _SimpleTask.signals()
        assert isinstance(sigs, list)

    def test_add_signal_appends_handler(self) -> None:
        """Test add_signal appends handler."""

        async def handler(instance: object) -> None:
            pass

        _SimpleTask.add_signal(handler)
        assert handler in _SimpleTask.signals()
        _SimpleTask.signals().remove(handler)

    def test_signal_registry_is_singleton(self) -> None:
        """Test signal registry is singleton."""
        sigs1 = _SimpleTask.signals()
        sigs2 = _SimpleTask.signals()
        assert sigs1 is sigs2

    # ── emit_signals ──

    @pytest.mark.asyncio
    async def test_emit_signals_with_webhook(self) -> None:
        """Test emit_signals with webhook."""
        task = _SimpleTask(
            webhook_url="https://hook.example.com/callback",
            uid="emit-uid",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": "ok"}

        handler_called = False

        def signal_handler(instance: object) -> None:
            nonlocal handler_called
            handler_called = True

        _SimpleTask.add_signal(signal_handler)

        with (
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
            ) as mock_post,
            patch.object(
                _SimpleTask, "save", new_callable=AsyncMock, create=True
            ),
            patch.object(_SimpleTask, "save_report", new_callable=AsyncMock),
        ):
            mock_post.return_value = mock_response
            await _SimpleTask.emit_signals(task)

        assert handler_called
        mock_post.assert_awaited_once()
        _, call_kwargs = mock_post.call_args
        assert call_kwargs["url"] == "https://hook.example.com/callback"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"
        payload = json.loads(call_kwargs["data"])
        assert payload["task_type"] == "_SimpleTask"
        assert payload["uid"] == "emit-uid"

        _SimpleTask.signals().remove(signal_handler)

    @pytest.mark.asyncio
    async def test_emit_signals_with_meta_data_webhook(self) -> None:
        """Test emit_signals with meta_data webhook."""
        task = _SimpleTask(
            uid="meta-uid",
            meta_data={"webhook_url": "https://meta.hook/notify"},
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}

        with (
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
            ) as mock_post,
            patch.object(
                _SimpleTask, "save", new_callable=AsyncMock, create=True
            ),
            patch.object(_SimpleTask, "save_report", new_callable=AsyncMock),
        ):
            mock_post.return_value = mock_response
            await _SimpleTask.emit_signals(task)

        mock_post.assert_awaited()

    @pytest.mark.asyncio
    async def test_emit_signals_without_webhook(self) -> None:
        """Test emit_signals without webhook."""
        task = _SimpleTask(uid="no-hook-uid")

        handler_called = False

        def signal_handler(instance: object) -> None:
            nonlocal handler_called
            handler_called = True

        _SimpleTask.add_signal(signal_handler)

        with (
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
            ),
            patch.object(
                _SimpleTask, "save", new_callable=AsyncMock, create=True
            ),
            patch.object(_SimpleTask, "save_report", new_callable=AsyncMock),
        ):
            await _SimpleTask.emit_signals(task)

        assert handler_called

        _SimpleTask.signals().remove(signal_handler)

    # ── save_status ──

    @pytest.mark.asyncio
    async def test_save_status(self) -> None:
        """Test save_status."""
        task = _SimpleTask()

        with patch.object(
            _SimpleTask, "add_log", new_callable=AsyncMock
        ) as mock_log:
            await task.save_status(TaskStatusEnum.processing)

        assert task.task_status == TaskStatusEnum.processing
        mock_log.assert_awaited_once()
        record = mock_log.call_args[0][0]
        assert isinstance(record, TaskLogRecord)
        assert record.message == "Status changed to processing"
        assert record.task_status == TaskStatusEnum.processing

    # ── add_reference ──

    @pytest.mark.asyncio
    async def test_add_reference_initializes_list(self) -> None:
        """Test add_reference initializes list."""
        task = _SimpleTask()
        assert task.task_references is None

        with patch.object(_SimpleTask, "add_log", new_callable=AsyncMock):
            await task.add_reference(task_id="ref-1")

        assert task.task_references is not None
        assert len(task.task_references.tasks) == 1
        ref = task.task_references.tasks[0]
        assert ref.task_id == "ref-1"
        assert ref.task_type == "_SimpleTask"

    @pytest.mark.asyncio
    async def test_add_reference_appends_to_existing(self) -> None:
        """Test add_reference appends to existing."""
        task = _SimpleTask()
        task.task_references = TaskReferenceList(
            tasks=[TaskReference(task_id="existing", task_type="Other")]
        )

        with patch.object(_SimpleTask, "add_log", new_callable=AsyncMock):
            await task.add_reference(task_id="new-ref")

        assert len(task.task_references.tasks) == 2

    # ── save_report ──

    @pytest.mark.asyncio
    async def test_save_report(self) -> None:
        """Test save_report."""
        task = _SimpleTask()

        with patch.object(
            _SimpleTask, "add_log", new_callable=AsyncMock
        ) as mock_log:
            await task.save_report("Something went wrong")

        assert task.task_report == "Something went wrong"
        mock_log.assert_awaited_once()
        record = mock_log.call_args[0][0]
        assert record.message == "Something went wrong"

    # ── add_log ──

    @pytest.mark.asyncio
    async def test_add_log_appends_and_emits(self) -> None:
        """Test add_log appends and emits."""
        task = _SimpleTask()
        record = TaskLogRecord(
            message="log me",
            task_status=TaskStatusEnum.draft,
        )

        with patch.object(
            _SimpleTask, "save_and_emit", new_callable=AsyncMock
        ) as mock_sae:
            await task.add_log(record)

        assert record in task.task_logs
        mock_sae.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_log_skips_emit_when_emit_false(self) -> None:
        """Test add_log skips emit when emit is false."""
        task = _SimpleTask()
        record = TaskLogRecord(
            message="silent",
            task_status=TaskStatusEnum.draft,
        )

        with patch.object(
            _SimpleTask, "save_and_emit", new_callable=AsyncMock
        ) as mock_sae:
            await task.add_log(record, emit=False)

        assert record in task.task_logs
        mock_sae.assert_not_called()

    # ── start_processing ──

    @pytest.mark.asyncio
    async def test_start_processing_raises_not_implemented(self) -> None:
        """Test start_processing raises not implemented."""
        task = _SimpleTask()
        assert task.task_references is None

        with pytest.raises(
            NotImplementedError,
            match="Subclasses should implement",
        ):
            await task.start_processing()

    @pytest.mark.asyncio
    async def test_start_processing_with_references(self) -> None:
        """Test start_processing with references."""
        task = _SimpleTask()
        task.task_references = MagicMock(spec=TaskReferenceList)
        task.task_references.list_processing = AsyncMock()

        await task.start_processing()
        task.task_references.list_processing.assert_awaited_once()

    # ── push_to_queue ──

    @pytest.mark.asyncio
    async def test_push_to_queue(self) -> None:
        """Test push_to_queue."""
        task = _SimpleTask(uid="queue-uid-456")
        mock_redis = AsyncMock()

        await task.push_to_queue(mock_redis, custom_field="val")

        mock_redis.lpush.assert_awaited_once()
        args, _ = mock_redis.lpush.call_args
        assert args[0] == "_simpletask_queue"
        payload = json.loads(args[1])
        assert payload["uid"] == "queue-uid-456"
        assert payload["custom_field"] == "val"

    # ── save_and_emit ──

    @pytest.mark.asyncio
    async def test_save_and_emit_parallel(self) -> None:
        """Test save_and_emit parallel."""
        task = _SimpleTask()

        with (
            patch.object(
                _SimpleTask, "save", new_callable=AsyncMock, create=True
            ) as mock_save,
            patch.object(
                _SimpleTask, "emit_signals", new_callable=AsyncMock
            ) as mock_emit,
        ):
            await task.save_and_emit()

        mock_save.assert_awaited_once()
        mock_emit.assert_awaited_once_with(task)

    @pytest.mark.asyncio
    async def test_save_and_emit_sync(self) -> None:
        """Test save_and_emit sync."""
        task = _SimpleTask()

        with (
            patch.object(
                _SimpleTask, "save", new_callable=AsyncMock, create=True
            ) as mock_save,
            patch.object(
                _SimpleTask, "emit_signals", new_callable=AsyncMock
            ) as mock_emit,
        ):
            await task.save_and_emit(sync=True)

        mock_save.assert_awaited_once()
        mock_emit.assert_awaited_once_with(task, sync=True)

    @pytest.mark.asyncio
    async def test_save_and_emit_catches_exception(self) -> None:
        """Test save_and_emit catches exception."""
        task = _SimpleTask()

        with patch.object(
            _SimpleTask, "save", new_callable=AsyncMock, create=True
        ) as mock_save:
            mock_save.side_effect = RuntimeError("boom")
            result = await task.save_and_emit()

        assert result is None

    # ── update_and_emit ──

    @pytest.mark.asyncio
    async def test_update_and_emit_sets_fields(self) -> None:
        """Test update_and_emit sets fields."""
        task = _SimpleTask()

        with (
            patch.object(_SimpleTask, "save_and_emit", new_callable=AsyncMock),
            patch.object(_SimpleTask, "add_log", new_callable=AsyncMock),
        ):
            await task.update_and_emit(
                task_status=TaskStatusEnum.processing,
                task_progress=50,
                task_report="Halfway there",
            )

        assert task.task_status == TaskStatusEnum.processing
        assert task.task_progress == 50
        assert task.task_report == "Halfway there"

    @pytest.mark.asyncio
    async def test_update_and_emit_auto_progress_on_finish(self) -> None:
        """Test update_and_emit auto progress on finish."""
        task = _SimpleTask()

        with (
            patch.object(_SimpleTask, "save_and_emit", new_callable=AsyncMock),
            patch.object(_SimpleTask, "add_log", new_callable=AsyncMock),
        ):
            await task.update_and_emit(task_status=TaskStatusEnum.done)

        assert task.task_progress == 100

    @pytest.mark.asyncio
    async def test_update_and_emit_does_not_override_explicit_progress(
        self,
    ) -> None:
        """Test update_and_emit does not override explicit progress."""
        task = _SimpleTask()

        with (
            patch.object(_SimpleTask, "save_and_emit", new_callable=AsyncMock),
            patch.object(_SimpleTask, "add_log", new_callable=AsyncMock),
        ):
            await task.update_and_emit(
                task_status=TaskStatusEnum.error,
                task_progress=50,
            )

        assert task.task_progress == 50

    @pytest.mark.asyncio
    async def test_update_and_emit_adds_log_for_report(self) -> None:
        """Test update_and_emit adds log for report."""
        task = _SimpleTask()

        with (
            patch.object(
                _SimpleTask, "save_and_emit", new_callable=AsyncMock
            ) as mock_sae,
            patch.object(
                _SimpleTask, "add_log", new_callable=AsyncMock
            ) as mock_log,
        ):
            await task.update_and_emit(
                task_status=TaskStatusEnum.completed,
                task_report="All done!",
            )

        mock_log.assert_awaited_once()
        record = mock_log.call_args[0][0]
        assert record.message == "All done!"
        assert record.task_status == TaskStatusEnum.completed
        mock_sae.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_and_emit_calls_save_and_emit(self) -> None:
        """Test update_and_emit calls save_and_emit."""
        task = _SimpleTask()

        with (
            patch.object(
                _SimpleTask, "save_and_emit", new_callable=AsyncMock
            ) as mock_sae,
            patch.object(_SimpleTask, "add_log", new_callable=AsyncMock),
        ):
            await task.update_and_emit(task_status=TaskStatusEnum.paused)

        mock_sae.assert_awaited_once()
