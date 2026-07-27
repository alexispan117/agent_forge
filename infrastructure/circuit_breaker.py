"""AgentForge — 熔断器（Circuit Breaker）

防止对失败的外部服务重复调用，保护系统稳定性。
"""

import time
import functools


class CircuitBreaker:
    """熔断器

    状态: CLOSED（正常）→ OPEN（熔断）→ HALF_OPEN（半开）→ CLOSED

    用法:
        cb = CircuitBreaker(name="baidu_api", failure_threshold=3, recovery_timeout=30)

        @cb
        def call_api():
            return risky_operation()

        result = call_api()  # 如果熔断会抛出 CircuitBreakerOpenError
    """

    def __init__(self, name: str = "default",
                 failure_threshold: int = 3,
                 recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._state = "CLOSED"  # CLOSED / OPEN / HALF_OPEN
        self._last_failure_time = 0.0
        self._stats = {"total": 0, "success": 0, "failure": 0, "rejected": 0}

    @property
    def state(self) -> str:
        return self._state

    @property
    def stats(self) -> dict:
        return {**self._stats, "state": self._state, "failures": self._failures}

    def _check(self):
        if self._state == "CLOSED":
            return True
        if self._state == "OPEN":
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = "HALF_OPEN"
                return True
            self._stats["rejected"] += 1
            return False
        # HALF_OPEN: 允许一次测试请求
        return True

    def _on_success(self):
        self._failures = 0
        self._state = "CLOSED"
        self._stats["success"] += 1

    def _on_failure(self, exc: Exception | None = None):
        self._failures += 1
        self._stats["failure"] += 1
        self._last_failure_time = time.time()
        if self._failures >= self.failure_threshold:
            self._state = "OPEN"

    def __call__(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            self._stats["total"] += 1
            if not self._check():
                raise CircuitBreakerOpenError(
                    f"熔断器 '{self.name}' 已开启，拒绝请求 "
                    f"(失败 {self._failures}/{self.failure_threshold} 次)"
                )
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure(e)
                raise
        return wrapper


class CircuitBreakerOpenError(Exception):
    """熔断器开启时抛出的异常"""
    pass
