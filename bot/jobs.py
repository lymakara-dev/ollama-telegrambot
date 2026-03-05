import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

JobHandler = Callable[[Dict[str, Any]], Awaitable[None]]


class JobRunner:
    def __init__(self, handler: JobHandler, max_queue_size: int = 200) -> None:
        self._handler = handler
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=max_queue_size)
        self._task: asyncio.Task[None] | None = None
        self._logger = logging.getLogger(__name__)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def enqueue(self, payload: Dict[str, Any]) -> bool:
        try:
            self._queue.put_nowait(payload)
            return True
        except asyncio.QueueFull:
            return False

    def queue_size(self) -> int:
        return self._queue.qsize()

    async def _worker(self) -> None:
        while True:
            payload = await self._queue.get()
            try:
                await self._handler(payload)
            except Exception:
                self._logger.exception("Failed processing queued telegram update")
            finally:
                self._queue.task_done()
