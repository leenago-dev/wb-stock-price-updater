import asyncio
import time
from typing import Callable, TypeVar, Awaitable
from app.config import settings

T = TypeVar("T")


class RequestQueue:
    """Rate limiting을 적용한 요청 큐"""

    def __init__(self):
        self.queue: list[dict] = []
        self.running = 0
        self.last_request_time = 0
        self.lock = asyncio.Lock()

    async def add(self, fn: Callable[[], Awaitable[T]]) -> T:
        """요청을 큐에 추가하고 실행"""
        future = asyncio.Future()

        async with self.lock:
            self.queue.append({
                "execute": fn,
                "future": future,
            })

        await self._process()
        return await future

    async def _process(self):
        """큐에서 요청을 처리"""
        async with self.lock:
            if (
                self.running >= settings.max_concurrent_requests
                or len(self.queue) == 0
            ):
                return

            self.running += 1
            task = self.queue.pop(0)

        try:
            # Rate limiting: 최소 요청 간격 확인
            now = time.time() * 1000  # 밀리초
            time_since_last = now - self.last_request_time
            min_delay = settings.min_request_delay_ms

            if time_since_last < min_delay:
                await asyncio.sleep((min_delay - time_since_last) / 1000)

            # 요청 실행
            result = await task["execute"]()
            self.last_request_time = time.time() * 1000

            task["future"].set_result(result)
        except Exception as e:
            task["future"].set_exception(e)
        finally:
            async with self.lock:
                self.running -= 1

            # 다음 요청 처리
            await self._process()


# 전역 RequestQueue 인스턴스
request_queue = RequestQueue()
