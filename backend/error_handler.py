#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
错误处理与重试模块
提供详细的错误报告和智能重试机制
"""

import asyncio
import time
from typing import Optional, Callable, Any, Dict, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class ErrorType(Enum):
    """错误类型枚举"""
    NETWORK_CONNECT = "network_connect"          # 网络连接错误
    NETWORK_TIMEOUT = "network_timeout"         # 网络超时
    RATE_LIMIT = "rate_limit"                  # 频率限制 (429)
    AUTH_ERROR = "auth_error"                   # 认证错误 (401)
    NOT_FOUND = "not_found"                     # 资源不存在 (404)
    SERVER_ERROR = "server_error"               # 服务器错误 (5xx)
    VALIDATION_ERROR = "validation_error"       # 验证错误
    UNKNOWN_ERROR = "unknown_error"             # 未知错误


class RetryStrategy(Enum):
    """重试策略"""
    IMMEDIATE = "immediate"      # 立即重试
    LINEAR_BACKOFF = "linear"     # 线性退避
    EXPONENTIAL_BACKOFF = "exp"   # 指数退避
    FIBONACCI_BACKOFF = "fib"     # 斐波那契退避


@dataclass
class ErrorContext:
    """错误上下文信息"""
    error_type: ErrorType
    message: str
    original_error: Optional[Exception]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    retry_count: int = 0
    max_retries: int = 3
    last_retry_delay: float = 0.0
    page_info: Optional[str] = None  # 页码信息，如 "第3页"
    additional_data: Dict[str, Any] = field(default_factory=dict)

    def to_user_message(self) -> str:
        """生成用户友好的错误消息"""
        base_msg = self.message

        if self.error_type == ErrorType.NETWORK_TIMEOUT:
            page_info = self.page_info or ""
            retry_info = f"（已重试 {self.retry_count}/{self.max_retries} 次）"
            return f"{page_info}网络超时{retry_info}，正在等待 {self.last_retry_delay:.1f}s 后重试..."

        elif self.error_type == ErrorType.RATE_LIMIT:
            page_info = self.page_info or ""
            retry_after = self.additional_data.get('retry_after', '稍后')
            return f"{page_info}请求频率超限，{retry_after} 后重试（已尝试 {self.retry_count}/{self.max_retries} 次）"

        elif self.error_type == ErrorType.NETWORK_CONNECT:
            page_info = self.page_info or ""
            return f"{page_info}网络连接失败，正在重试..."

        elif self.error_type == ErrorType.NOT_FOUND:
            return f"资源不存在（404）：{self.additional_data.get('model', '模型')} 可能不可用，请检查配置"

        elif self.error_type == ErrorType.AUTH_ERROR:
            return "认证失败：API Key 无效或已过期，请检查配置"

        elif self.error_type == ErrorType.SERVER_ERROR:
            page_info = self.page_info or ""
            status_code = self.additional_data.get('status_code', '5xx')
            return f"{page_info}服务器错误（{status_code}），正在重试..."

        return base_msg


class RetryHandler:
    """
    带智能重试的错误处理器
    提供详细的进度报告和用户友好的错误消息
    """

    # 各错误类型的默认重试策略
    DEFAULT_STRATEGIES = {
        ErrorType.NETWORK_CONNECT: (3, RetryStrategy.EXPONENTIAL_BACKOFF, [1, 2, 4]),
        ErrorType.NETWORK_TIMEOUT: (3, RetryStrategy.EXPONENTIAL_BACKOFF, [2, 4, 8]),
        ErrorType.RATE_LIMIT: (3, RetryStrategy.LINEAR_BACKOFF, [5, 10, 15]),
        ErrorType.SERVER_ERROR: (3, RetryStrategy.EXPONENTIAL_BACKOFF, [1, 2, 4]),
        ErrorType.UNKNOWN_ERROR: (2, RetryStrategy.LINEAR_BACKOFF, [1, 2]),
    }

    def __init__(
        self,
        progress_callback: Optional[Callable[[str, str], None]] = None,
        default_max_retries: int = 3
    ):
        """
        初始化重试处理器

        Args:
            progress_callback: 进度回调函数，签名为 (status_type, message)
                           status_type: 'info' | 'retry' | 'warning' | 'error'
                           message: 状态消息
            default_max_retries: 默认最大重试次数
        """
        self.progress_callback = progress_callback
        self.default_max_retries = default_max_retries

    def _emit_progress(
        self,
        status: str,
        message: str,
        error_context: Optional[ErrorContext] = None
    ) -> None:
        """发送进度更新"""
        if self.progress_callback:
            self.progress_callback(status, message)

    def _classify_error(self, exception: Exception) -> ErrorType:
        """分类错误类型"""
        error_str = str(exception).lower()
        exception_type = type(exception).__name__

        # 根据异常类型和消息内容分类
        if 'timeout' in error_str or 'TimeoutException' in exception_type:
            return ErrorType.NETWORK_TIMEOUT

        if 'connect' in error_str or 'ConnectError' in exception_type:
            return ErrorType.NETWORK_CONNECT

        if '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str:
            return ErrorType.RATE_LIMIT

        if '401' in error_str or 'auth' in error_str or 'unauthorized' in error_str:
            return ErrorType.AUTH_ERROR

        if '404' in error_str or 'not found' in error_str:
            return ErrorType.NOT_FOUND

        if '500' in error_str or '502' in error_str or '503' in error_str or 'server error' in error_str:
            return ErrorType.SERVER_ERROR

        return ErrorType.UNKNOWN_ERROR

    def _get_retry_config(self, error_type: ErrorType) -> tuple:
        """获取错误类型的重试配置"""
        if error_type in self.DEFAULT_STRATEGIES:
            return self.DEFAULT_STRATEGIES[error_type]
        return (self.default_max_retries, RetryStrategy.LINEAR_BACKOFF, [1] * self.default_max_retries)

    def _calculate_delay(
        self,
        strategy: RetryStrategy,
        delays: List[float],
        attempt: int
    ) -> float:
        """计算重试延迟"""
        if attempt < len(delays):
            return delays[attempt]

        # 回退到线性
        return delays[-1] if delays else 1.0

    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        page_info: Optional[str] = None,
        error_context_extra: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """
        执行函数并在失败时重试

        Args:
            func: 要执行的异步函数
            *args: 函数位置参数
            page_info: 页码信息（如 "第3页"）
            error_context_extra: 额外的错误上下文数据
            **kwargs: 函数关键字参数

        Returns:
            函数执行结果

        Raises:
            Exception: 所有重试都失败后抛出最后一次异常
        """
        error_type = ErrorType.UNKNOWN_ERROR
        last_error: Optional[Exception] = None
        retry_count = 0
        max_retries = self.default_max_retries
        delays: List[float] = [1, 2, 4]

        # 先尝试执行一次
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_type = self._classify_error(e)
            max_retries, strategy, delays = self._get_retry_config(error_type)

            self._emit_progress(
                'info',
                f"{page_info or ''} 发生错误: {str(e)[:50]}...",
                None
            )

        # 重试循环
        for attempt in range(max_retries):
            retry_count = attempt + 1
            delay = self._calculate_delay(strategy, delays, attempt)

            # 构建错误上下文
            context = ErrorContext(
                error_type=error_type,
                message=str(last_error) if last_error else "未知错误",
                original_error=last_error,
                retry_count=retry_count,
                max_retries=max_retries,
                last_retry_delay=delay,
                page_info=page_info,
                additional_data=error_context_extra or {}
            )

            # 发送重试进度消息
            self._emit_progress('retry', context.to_user_message(), context)

            # 等待
            await asyncio.sleep(delay)

            # 再次尝试
            try:
                result = await func(*args, **kwargs)
                if retry_count > 1:
                    self._emit_progress(
                        'info',
                        f"{page_info or ''} 重试成功（第 {retry_count}/{max_retries} 次）",
                        None
                    )
                return result
            except Exception as e:
                last_error = e
                error_type = self._classify_error(e)

                # 如果是不可重试的错误，立即抛出
                if error_type in (ErrorType.AUTH_ERROR, ErrorType.NOT_FOUND, ErrorType.VALIDATION_ERROR):
                    raise

        # 所有重试都失败
        final_context = ErrorContext(
            error_type=error_type,
            message=str(last_error) if last_error else "未知错误",
            original_error=last_error,
            retry_count=retry_count,
            max_retries=max_retries,
            page_info=page_info,
            additional_data=error_context_extra or {}
        )

        self._emit_progress('error', f"{page_info or ''} 重试 {max_retries} 次后仍失败: {final_context.message}", final_context)

        raise last_error


class DetailedErrorCollector:
    """
    收集并汇总转换过程中的详细错误信息
    用于生成按页的错误报告
    """

    def __init__(self):
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []

    def add_error(
        self,
        page_num: int,
        error_type: str,
        message: str,
        recoverable: bool = True,
        retry_count: int = 0
    ) -> None:
        """添加一个错误"""
        self.errors.append({
            'page': page_num,
            'type': error_type,
            'message': message,
            'recoverable': recoverable,
            'retry_count': retry_count,
            'timestamp': datetime.now().isoformat()
        })

    def add_warning(
        self,
        page_num: int,
        message: str
    ) -> None:
        """添加一个警告"""
        self.warnings.append({
            'page': page_num,
            'message': message,
            'timestamp': datetime.now().isoformat()
        })

    def get_page_summary(self, page_num: int) -> Dict[str, Any]:
        """获取特定页面的错误摘要"""
        page_errors = [e for e in self.errors if e['page'] == page_num]
        page_warnings = [w for w in self.warnings if w['page'] == page_num]

        return {
            'page': page_num,
            'error_count': len(page_errors),
            'warning_count': len(page_warnings),
            'errors': page_errors,
            'warnings': page_warnings,
            'is_recoverable': any(e['recoverable'] for e in page_errors)
        }

    def get_summary(self) -> Dict[str, Any]:
        """获取总体错误摘要"""
        total_errors = len(self.errors)
        total_warnings = len(self.warnings)
        recoverable = sum(1 for e in self.errors if e['recoverable'])
        non_recoverable = total_errors - recoverable

        # 按错误类型分组
        errors_by_type: Dict[str, int] = {}
        for e in self.errors:
            err_type = e['type']
            errors_by_type[err_type] = errors_by_type.get(err_type, 0) + 1

        return {
            'total_errors': total_errors,
            'total_warnings': total_warnings,
            'recoverable_errors': recoverable,
            'non_recoverable_errors': non_recoverable,
            'errors_by_type': errors_by_type,
            'failed_pages': list(set(e['page'] for e in self.errors))
        }

    def format_for_user(self) -> str:
        """格式化错误信息为用户友好的字符串"""
        summary = self.get_summary()

        if summary['total_errors'] == 0:
            return ""

        lines = []
        lines.append(f"\n{'='*50}")
        lines.append("错误摘要：")
        lines.append(f"  总错误数: {summary['total_errors']}")
        lines.append(f"  可恢复错误: {summary['recoverable_errors']}")
        lines.append(f"  不可恢复错误: {summary['non_recoverable_errors']}")

        if summary['errors_by_type']:
            lines.append("  错误类型分布:")
            for err_type, count in summary['errors_by_type'].items():
                lines.append(f"    - {err_type}: {count}")

        lines.append(f"  失败页面: {summary['failed_pages']}")
        lines.append(f"{'='*50}\n")

        return "\n".join(lines)


# 快捷函数
def create_error_context(
    exception: Exception,
    page_info: Optional[str] = None,
    retry_count: int = 0,
    max_retries: int = 3
) -> ErrorContext:
    """从异常创建错误上下文"""
    error_types = {
        'timeout': ErrorType.NETWORK_TIMEOUT,
        'connect': ErrorType.NETWORK_CONNECT,
        '429': ErrorType.RATE_LIMIT,
        '401': ErrorType.AUTH_ERROR,
        '404': ErrorType.NOT_FOUND,
        '5': ErrorType.SERVER_ERROR,
    }

    error_type = ErrorType.UNKNOWN_ERROR
    error_str = str(exception).lower()

    for key, et in error_types.items():
        if key in error_str:
            error_type = et
            break

    return ErrorContext(
        error_type=error_type,
        message=str(exception),
        original_error=exception,
        retry_count=retry_count,
        max_retries=max_retries,
        page_info=page_info
    )