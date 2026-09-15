import asyncio
import logging
import time
import traceback
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("facedeep.worker")


@dataclass
class Task:
    func: Callable[..., Coroutine]
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    task_id: str = ""
    created_at: float = field(default_factory=time.time)


class WorkerPool:
    def __init__(self, max_workers: int = 4, max_queue_size: int = 100):
        self._queue: asyncio.Queue[Task] = asyncio.Queue(maxsize=max_queue_size)
        self._workers: list[asyncio.Task] = []
        self._max_workers = max_workers
        self._running = False
        self._stats = {"processed": 0, "failed": 0, "active": 0}

    async def start(self):
        if self._running:
            return
        self._running = True
        for i in range(self._max_workers):
            worker = asyncio.create_task(self._worker_loop(i))
            self._workers.append(worker)
        logger.info(f"WorkerPool started with {self._max_workers} workers")

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("WorkerPool stopped")

    async def submit(self, func: Callable[..., Coroutine], *args, task_id: str = "", **kwargs) -> str:
        if not task_id:
            task_id = f"task_{int(time.time()*1000)}"
        task = Task(func=func, args=args, kwargs=kwargs, task_id=task_id)
        await self._queue.put(task)
        logger.debug(f"Task {task_id} submitted to queue")
        return task_id

    async def _worker_loop(self, worker_id: int):
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            self._stats["active"] += 1
            try:
                await task.func(*task.args, **task.kwargs)
                self._stats["processed"] += 1
            except Exception as e:
                self._stats["failed"] += 1
                logger.error(f"Task {task.task_id} failed: {e}\n{traceback.format_exc()}")
            finally:
                self._stats["active"] -= 1
                self._queue.task_done()

    @property
    def stats(self) -> dict:
        return {
            **self._stats,
            "queue_size": self._queue.qsize(),
        }


worker_pool = WorkerPool(max_workers=4, max_queue_size=256)
