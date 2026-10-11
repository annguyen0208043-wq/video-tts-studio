from __future__ import annotations

import asyncio
import json
from collections import defaultdict


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)

    async def subscribe(self, project_id: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers[project_id].add(queue)
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue[str]) -> None:
        self._subscribers[project_id].discard(queue)

    def publish(self, project_id: str, payload: dict) -> None:
        message = json.dumps(payload, ensure_ascii=False)
        for queue in tuple(self._subscribers.get(project_id, set())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass


event_bus = EventBus()

