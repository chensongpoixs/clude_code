from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Literal


OnLimit = Literal["sleep", "error"]


@dataclass
class AcquireResult:
    ok: bool
    waited_ms: int = 0
    error: str = ""


class RateLimiter:
    """
    线程安全的 LLM 限流器（Token Bucket + 并发 Semaphore）。

    - QPS：用 token bucket 控制“每秒请求数”
    - 并发：用 semaphore 控制“同时在途请求数”
    """

    def __init__(
        self,
        *,
        enabled: bool,
        requests_per_second: float,
        burst: int,
        max_concurrent: int,
        wait_timeout_s: float,
        on_limit: OnLimit,
    ) -> None:
        self.enabled = bool(enabled)
        self.rps = max(float(requests_per_second), 0.0)
        self.capacity = max(int(burst), 0)
        self.wait_timeout_s = max(float(wait_timeout_s), 0.0)
        self.on_limit: OnLimit = on_limit

        self._lock = threading.Lock()
        self._tokens = float(self.capacity)
        self._last = time.monotonic()

        self._sem = threading.Semaphore(max(1, int(max_concurrent)))

    def _refill(self) -> None:
        now = time.monotonic()
        dt = now - self._last
        self._last = now
        if self.rps <= 0 or self.capacity <= 0:
            return
        self._tokens = min(float(self.capacity), self._tokens + dt * self.rps)

    def acquire(self) -> tuple[AcquireResult, Callable[[], None]]:
        """
        获取一次“LLM 请求许可”。返回 (result, release_fn)。
        - 若 result.ok=False，release_fn 仍可安全调用（no-op）。
        """
        if not self.enabled:
            return AcquireResult(ok=True, waited_ms=0), (lambda: None)

        t0 = time.monotonic()

        # 1) 并发控制：最多 wait_timeout_s
        got = self._sem.acquire(timeout=self.wait_timeout_s if self.wait_timeout_s > 0 else None)
        if not got:
            if self.on_limit == "error":
                return AcquireResult(ok=False, waited_ms=int((time.monotonic() - t0) * 1000), error="concurrency_limit_timeout"), (lambda: None)
            # sleep 策略：再等一会（简单处理）
            time.sleep(0.05)
            got = self._sem.acquire(timeout=self.wait_timeout_s if self.wait_timeout_s > 0 else None)
            if not got:
                return AcquireResult(ok=False, waited_ms=int((time.monotonic() - t0) * 1000), error="concurrency_limit_timeout"), (lambda: None)

        released = False

        def _release() -> None:
            nonlocal released
            if released:
                return
            released = True
            try:
                self._sem.release()
            except Exception:
                return

        # 2) QPS 控制：token bucket
        if self.rps <= 0 or self.capacity <= 0:
            # 视为不限制 QPS（只限制并发）
            return AcquireResult(ok=True, waited_ms=int((time.monotonic() - t0) * 1000)), _release

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    waited_ms = int((time.monotonic() - t0) * 1000)
                    return AcquireResult(ok=True, waited_ms=waited_ms), _release

                # 需要等待的时间（秒）
                need = (1.0 - self._tokens) / self.rps if self.rps > 0 else 0.0

            if self.on_limit == "error":
                _release()
                return AcquireResult(ok=False, waited_ms=int((time.monotonic() - t0) * 1000), error="qps_limit"), (lambda: None)

            # sleep 策略：等到 token 补足（加一点 jitter 避免抖动）
            sleep_s = max(0.0, min(need, 0.5))
            if self.wait_timeout_s > 0 and (time.monotonic() - t0) >= self.wait_timeout_s:
                _release()
                return AcquireResult(ok=False, waited_ms=int((time.monotonic() - t0) * 1000), error="qps_wait_timeout"), (lambda: None)
            time.sleep(sleep_s if sleep_s > 0 else 0.01)


