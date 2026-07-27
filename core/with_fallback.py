"""
core/with_fallback.py — 故障自愈与降级装饰器 v2

实现 Harness Engineering 的「权限与安全护栏」模式。

v2 升级点：
1. 同步/异步双支持（自动检测协程函数，异步路径用 asyncio.wait_for 真超时）
2. 指数退避 + 抖动（替代旧版固定 sleep）
3. 异常分类：仅 retry_on 白名单异常触发重试，业务异常立即抛出
4. 修复旧版 last_error 通过 dir() 探测恒为 "unknown" 的 bug
5. 内置降级兜底提为模块常量；注册降级函数同步/异步均可
6. 可选指标钩子（set_metrics_hook），向 CLEAR 评估体系上报成功/失败/耗时
"""
import asyncio
import functools
import inspect
import logging
import random
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("fallback")

# 全局降级策略注册表
_fallback_registry: dict[str, list[Callable]] = {}

# 指标钩子：fn(service, success, latency_s, attempts)
_metrics_hook: Optional[Callable[[str, bool, float, int], None]] = None

#: 默认可重试异常（网络/超时/临时性错误）；业务异常（ValueError 等）不重试
DEFAULT_RETRYABLE: tuple[type[Exception], ...] = (
    ConnectionError, TimeoutError, asyncio.TimeoutError, OSError,
)

#: 各服务无注册降级策略时的内置兜底（模块常量，避免每次调用重建）
DEGRADED_DEFAULTS: dict[str, dict] = {
    "analyst": {"status": "degraded", "message": "分析服务暂不可用，使用规则引擎兜底", "findings": []},
    "desensitize": {"status": "degraded", "message": "脱敏服务暂不可用，启用本地规则引擎", "fields_masked": 0},
    "report": {"status": "degraded", "message": "报告生成服务暂不可用，返回简化报告", "content": "服务暂不可用，请稍后重试"},
    "supervisor": {"status": "degraded", "message": "调度服务暂不可用，按预设流程执行", "tasks": []},
}


def register_fallback(service: str, fallback_fn: Callable) -> None:
    """为指定服务注册降级策略（同步/异步函数均可）。"""
    _fallback_registry.setdefault(service, []).append(fallback_fn)


def set_metrics_hook(hook: Callable[[str, bool, float, int], None]) -> None:
    """注册指标钩子：hook(service, success, latency_s, attempts)。"""
    global _metrics_hook
    _metrics_hook = hook


def _report(service: str, success: bool, latency_s: float, attempts: int) -> None:
    if _metrics_hook is not None:
        try:
            _metrics_hook(service, success, latency_s, attempts)
        except Exception as e:
            logger.error(f"[{service}] 指标钩子异常: {e}")


def _backoff(attempt: int, base_delay: float) -> float:
    """指数退避 + 抖动：0.5s → 1s → 2s ...，叠加 0~0.3s 随机抖动防惊群。"""
    return base_delay * (2 ** attempt) + random.uniform(0, 0.3)


def with_fallback(
    service: str = "default",
    max_retries: int = 2,
    timeout_s: float = 15.0,
    base_delay: float = 0.5,
    retry_on: tuple[type[Exception], ...] = DEFAULT_RETRYABLE,
    recovery_timeout: Optional[float] = None,
):
    """
    故障自愈装饰器（同步/异步函数通用）

    功能：
    1. 自动重试（max_retries 次，指数退避 + 抖动）
    2. 超时保护（异步路径每次尝试受 timeout_s 限制）
    3. 降级策略池（register_fallback 注册，耗尽重试后依次执行）
    4. 异常分类（仅 retry_on 白名单异常触发重试）
    5. 指标上报（set_metrics_hook）

    用法：
        @with_fallback(service="analyst", max_retries=2)
        async def analyze_contract(contract_id): ...

    兼容：recovery_timeout 为旧版参数，传入时映射为 base_delay。
    """
    if recovery_timeout is not None:
        base_delay = recovery_timeout

    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                last_error: Optional[Exception] = None
                t0 = time.time()
                for attempt in range(max_retries + 1):
                    try:
                        if attempt > 0:
                            logger.warning(f"[{service}] 第{attempt}次重试 {func.__name__}")
                        result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_s)
                        _report(service, True, time.time() - t0, attempt + 1)
                        return result
                    except retry_on as e:
                        last_error = e
                        logger.error(f"[{service}] {func.__name__} 失败(第{attempt + 1}次): {e}")
                        if attempt < max_retries:
                            await asyncio.sleep(_backoff(attempt, base_delay))
                logger.warning(f"[{service}] {func.__name__} 重试耗尽，执行降级")
                result = await _execute_fallback_async(service, func.__name__, last_error, *args, **kwargs)
                _report(service, False, time.time() - t0, max_retries + 1)
                return result
            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            last_error: Optional[Exception] = None
            t0 = time.time()
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        logger.warning(f"[{service}] 第{attempt}次重试 {func.__name__}")
                    result = func(*args, **kwargs)
                    _report(service, True, time.time() - t0, attempt + 1)
                    return result
                except retry_on as e:
                    last_error = e
                    logger.error(f"[{service}] {func.__name__} 失败(第{attempt + 1}次): {e}")
                    if attempt < max_retries:
                        time.sleep(_backoff(attempt, base_delay))
            logger.warning(f"[{service}] {func.__name__} 重试耗尽，执行降级")
            result = _execute_fallback_sync(service, func.__name__, last_error, *args, **kwargs)
            _report(service, False, time.time() - t0, max_retries + 1)
            return result
        return sync_wrapper
    return decorator


def _degraded_default(service: str, last_error: Optional[Exception]) -> dict:
    """内置兜底响应（附带真实错误信息）。"""
    default = dict(DEGRADED_DEFAULTS.get(service, {"status": "degraded"}))
    default["error"] = str(last_error) if last_error else "unknown"
    return default


def _execute_fallback_sync(service: str, func_name: str, last_error: Optional[Exception], *args, **kwargs) -> Any:
    """同步上下文执行降级策略池。"""
    for fn in _fallback_registry.get(service, []):
        try:
            out = fn(*args, **kwargs)
            if inspect.isawaitable(out):
                # 同步上下文无事件循环，安全驱动协程
                out = asyncio.run(out)
            return out
        except Exception as e:
            logger.error(f"[{service}] 降级策略失败: {e}")
            continue
    logger.warning(f"[{service}] 无可用降级策略，返回内置兜底")
    return _degraded_default(service, last_error)


async def _execute_fallback_async(service: str, func_name: str, last_error: Optional[Exception], *args, **kwargs) -> Any:
    """异步上下文执行降级策略池。"""
    for fn in _fallback_registry.get(service, []):
        try:
            out = fn(*args, **kwargs)
            if inspect.isawaitable(out):
                out = await out
            return out
        except Exception as e:
            logger.error(f"[{service}] 降级策略失败: {e}")
            continue
    logger.warning(f"[{service}] 无可用降级策略，返回内置兜底")
    return _degraded_default(service, last_error)


def simulate_failure(rate: float = 1.0):
    """故障注入装饰器（演示 Worker 宕机场景用），同步/异步通用。"""
    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if random.random() < rate:
                    raise ConnectionError(f"[故障注入] {func.__name__} 模拟宕机")
                return await func(*args, **kwargs)
            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if random.random() < rate:
                raise ConnectionError(f"[故障注入] {func.__name__} 模拟宕机")
            return func(*args, **kwargs)
        return sync_wrapper
    return decorator
