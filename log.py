"""
日志模块 - 使用环境变量配置

Enhanced features:
- Structured JSON logging (LOG_FORMAT=json)
- Log rotation (LOG_MAX_SIZE_MB, LOG_BACKUP_COUNT)
- Performance timing helpers (log_timing context manager)
- Enhanced context fields (model, duration_ms, status_code)
"""

import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

# 日志级别定义
LOG_LEVELS = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}

# 线程锁，用于文件写入同步
_file_lock = threading.Lock()

# 文件写入状态标志
_file_writing_disabled = False
_disable_reason = None


def _get_current_log_level():
    """获取当前日志级别"""
    level = os.getenv("LOG_LEVEL", "info").lower()
    return LOG_LEVELS.get(level, LOG_LEVELS["info"])


def _get_log_file_path():
    """获取日志文件路径"""
    return os.getenv("LOG_FILE", "log.txt")


def _get_log_format() -> str:
    """
    Get log format setting.

    Environment variable: LOG_FORMAT
    Values: "text" (default) or "json"
    """
    return os.getenv("LOG_FORMAT", "text").lower()


def _get_log_max_size_mb() -> int:
    """
    Get maximum log file size in MB before rotation.

    Environment variable: LOG_MAX_SIZE_MB
    Default: 10
    """
    try:
        return int(os.getenv("LOG_MAX_SIZE_MB", "10"))
    except ValueError:
        return 10


def _get_log_backup_count() -> int:
    """
    Get number of backup log files to keep.

    Environment variable: LOG_BACKUP_COUNT
    Default: 5
    """
    try:
        return int(os.getenv("LOG_BACKUP_COUNT", "5"))
    except ValueError:
        return 5


def _should_rotate_log(log_file: str) -> bool:
    """
    Check if log file should be rotated based on size.

    Args:
        log_file: Path to the log file

    Returns:
        True if file exceeds max size and should be rotated
    """
    try:
        if not os.path.exists(log_file):
            return False
        file_size_mb = os.path.getsize(log_file) / (1024 * 1024)
        max_size_mb = float(os.getenv("LOG_MAX_SIZE_MB", "10"))
        return file_size_mb >= max_size_mb
    except (OSError, ValueError):
        return False


def _rotate_log_file(log_file: str):
    """
    Rotate log file by renaming existing backups and current file.

    Creates backup files: log.txt.1, log.txt.2, etc.
    """
    backup_count = _get_log_backup_count()

    try:
        # Remove oldest backup if it exists
        oldest_backup = f"{log_file}.{backup_count}"
        if os.path.exists(oldest_backup):
            os.remove(oldest_backup)

        # Shift existing backups
        for i in range(backup_count - 1, 0, -1):
            old_name = f"{log_file}.{i}"
            new_name = f"{log_file}.{i + 1}"
            if os.path.exists(old_name):
                os.rename(old_name, new_name)

        # Rename current file to .1
        if os.path.exists(log_file):
            os.rename(log_file, f"{log_file}.1")
    except OSError:
        pass  # Best effort rotation


def _format_json_entry(
    level: str,
    message: str,
    component: Optional[str] = None,
    req_id: Optional[str] = None,
    **extra_fields: Any,
) -> str:
    """
    Format log entry as JSON string.

    Args:
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        component: Optional component name (e.g., ANTHROPIC, STREAMING)
        req_id: Optional request ID for correlation
        **extra_fields: Additional fields (model, duration_ms, status_code, etc.)

    Returns:
        JSON string representing the log entry
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
    }

    if component:
        entry["component"] = component
    if req_id:
        entry["req_id"] = req_id

    # Add any extra fields
    for key, value in extra_fields.items():
        if value is not None:
            entry[key] = value

    return json.dumps(entry, ensure_ascii=False)


def _format_with_context(
    message: str,
    component: Optional[str] = None,
    req_id: Optional[str] = None,
    model: Optional[str] = None,
    duration_ms: Optional[int] = None,
    status_code: Optional[int] = None,
    **extra: Any,
) -> str:
    """
    Format message with optional context fields.

    Format for text: [COMPONENT] message model=X duration=Yms status=Z reqId=xxx
    Format for JSON: Returns JSON string with all fields

    Args:
        message: The log message
        component: Optional component name (e.g., ANTHROPIC, STREAMING)
        req_id: Optional request ID for correlation
        model: Optional model name
        duration_ms: Optional duration in milliseconds
        status_code: Optional HTTP status code
        **extra: Additional context fields
    """
    log_format = _get_log_format()

    if log_format == "json":
        # For JSON format, return a dict that will be serialized later
        # But since _log expects a string, we format it here
        return _format_json_entry(
            level="",  # Will be set by _log
            message=message,
            component=component,
            req_id=req_id,
            model=model,
            duration_ms=duration_ms,
            status_code=status_code,
            **extra,
        )

    # Text format
    parts = []
    if component:
        parts.append(f"[{component}]")
    parts.append(message)

    # Add optional fields
    if model:
        parts.append(f"model={model}")
    if duration_ms is not None:
        parts.append(f"duration={duration_ms}ms")
    if status_code is not None:
        parts.append(f"status={status_code}")
    if req_id:
        parts.append(f"reqId={req_id}")

    # Add any extra fields
    for key, value in extra.items():
        if value is not None:
            parts.append(f"{key}={value}")

    return " ".join(parts)


def _write_to_file(message: str):
    """线程安全地写入日志文件"""
    global _file_writing_disabled, _disable_reason

    # 如果文件写入已被禁用，直接返回
    if _file_writing_disabled:
        return

    try:
        log_file = _get_log_file_path()

        with _file_lock:
            # Check for rotation before writing
            if _should_rotate_log(log_file):
                _rotate_log_file(log_file)

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(message + "\n")
                f.flush()  # 强制刷新到磁盘，确保实时写入
    except (PermissionError, OSError, IOError) as e:
        # 检测只读文件系统或权限问题，禁用文件写入
        _file_writing_disabled = True
        _disable_reason = str(e)
        print(
            f"Warning: File system appears to be read-only or permission denied. "
            f"Disabling log file writing: {e}",
            file=sys.stderr,
        )
        print("Log messages will continue to display in console only.", file=sys.stderr)
    except Exception as e:
        # 其他异常仍然输出警告但不禁用写入（可能是临时问题）
        print(f"Warning: Failed to write to log file: {e}", file=sys.stderr)


def _log(level: str, message: str):
    """
    内部日志函数
    """
    level = level.lower()
    if level not in LOG_LEVELS:
        print(f"Warning: Unknown log level '{level}'", file=sys.stderr)
        return

    # 检查日志级别
    current_level = _get_current_log_level()
    if LOG_LEVELS[level] < current_level:
        return

    # 格式化日志消息
    log_format = _get_log_format()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if log_format == "json" and message.startswith("{"):
        # Message is already JSON formatted, update level
        try:
            data = json.loads(message)
            data["level"] = level
            data["timestamp"] = datetime.now().isoformat()
            entry = json.dumps(data, ensure_ascii=False)
        except json.JSONDecodeError:
            entry = f"[{timestamp}] [{level.upper()}] {message}"
    else:
        entry = f"[{timestamp}] [{level.upper()}] {message}"

    # 输出到控制台
    if level in ("error", "critical"):
        print(entry, file=sys.stderr)
    else:
        print(entry)

    # 实时写入文件
    _write_to_file(entry)


def set_log_level(level: str):
    """设置日志级别提示"""
    level = level.lower()
    if level not in LOG_LEVELS:
        print(
            f"Warning: Unknown log level '{level}'. Valid levels: {', '.join(LOG_LEVELS.keys())}"
        )
        return False

    print(
        f"Note: To set log level '{level}', please set LOG_LEVEL environment variable"
    )
    return True


class TimingContext:
    """Context object returned by log_timing to access timing results."""

    def __init__(self):
        self.start_time: float = 0
        self.end_time: float = 0
        self.duration_ms: int = 0


@contextmanager
def log_timing(
    operation: str,
    component: Optional[str] = None,
    req_id: Optional[str] = None,
    level: str = "debug",
):
    """
    Context manager for timing operations and logging duration.

    Usage:
        with log_timing("fetch_data", req_id="req_123") as timer:
            # ... operation ...
        print(f"Took {timer.duration_ms}ms")

    Args:
        operation: Name of the operation being timed
        component: Optional component name for logging
        req_id: Optional request ID for correlation
        level: Log level for the timing message (default: debug)
    """
    timer = TimingContext()
    timer.start_time = time.perf_counter()

    try:
        yield timer
    finally:
        timer.end_time = time.perf_counter()
        timer.duration_ms = int((timer.end_time - timer.start_time) * 1000)

        # Log the timing
        message = f"{operation} completed"
        formatted = _format_with_context(
            message,
            component=component,
            req_id=req_id,
            duration_ms=timer.duration_ms,
        )
        _log(level, formatted)


class Logger:
    """支持 log('info', 'msg') 和 log.info('msg') 两种调用方式"""

    def __call__(self, level: str, message: str, **kwargs):
        """支持 log('info', 'message') 调用方式"""
        formatted = _format_with_context(
            message,
            component=kwargs.get("component"),
            req_id=kwargs.get("req_id"),
            model=kwargs.get("model"),
            duration_ms=kwargs.get("duration_ms"),
            status_code=kwargs.get("status_code"),
        )
        _log(level, formatted)

    def debug(self, message: str, **kwargs):
        """记录调试信息"""
        formatted = _format_with_context(
            message,
            component=kwargs.get("component"),
            req_id=kwargs.get("req_id"),
            model=kwargs.get("model"),
            duration_ms=kwargs.get("duration_ms"),
            status_code=kwargs.get("status_code"),
        )
        _log("debug", formatted)

    def info(self, message: str, **kwargs):
        """记录一般信息"""
        formatted = _format_with_context(
            message,
            component=kwargs.get("component"),
            req_id=kwargs.get("req_id"),
            model=kwargs.get("model"),
            duration_ms=kwargs.get("duration_ms"),
            status_code=kwargs.get("status_code"),
        )
        _log("info", formatted)

    def warning(self, message: str, **kwargs):
        """记录警告信息"""
        formatted = _format_with_context(
            message,
            component=kwargs.get("component"),
            req_id=kwargs.get("req_id"),
            model=kwargs.get("model"),
            duration_ms=kwargs.get("duration_ms"),
            status_code=kwargs.get("status_code"),
        )
        _log("warning", formatted)

    def error(self, message: str, **kwargs):
        """记录错误信息"""
        formatted = _format_with_context(
            message,
            component=kwargs.get("component"),
            req_id=kwargs.get("req_id"),
            model=kwargs.get("model"),
            duration_ms=kwargs.get("duration_ms"),
            status_code=kwargs.get("status_code"),
        )
        _log("error", formatted)

    def critical(self, message: str, **kwargs):
        """记录严重错误信息"""
        formatted = _format_with_context(
            message,
            component=kwargs.get("component"),
            req_id=kwargs.get("req_id"),
            model=kwargs.get("model"),
            duration_ms=kwargs.get("duration_ms"),
            status_code=kwargs.get("status_code"),
        )
        _log("critical", formatted)

    # Context-aware logging methods for common components
    def anthropic(self, level: str, message: str, req_id: str = None, **kwargs):
        """Log with ANTHROPIC component"""
        self(level, message, component="ANTHROPIC", req_id=req_id, **kwargs)

    def streaming(self, level: str, message: str, req_id: str = None, **kwargs):
        """Log with STREAMING component"""
        self(level, message, component="STREAMING", req_id=req_id, **kwargs)

    def thinking(self, level: str, message: str, req_id: str = None, **kwargs):
        """Log with THINKING component"""
        self(level, message, component="THINKING", req_id=req_id, **kwargs)

    def get_current_level(self) -> str:
        """获取当前日志级别名称"""
        current_level = _get_current_log_level()
        for name, value in LOG_LEVELS.items():
            if value == current_level:
                return name
        return "info"

    def get_log_file(self) -> str:
        """获取当前日志文件路径"""
        return _get_log_file_path()


# 导出全局日志实例
log = Logger()

# 导出的公共接口
__all__ = ["log", "set_log_level", "LOG_LEVELS", "log_timing", "TimingContext"]

# 使用说明:
# 1. 设置日志级别: export LOG_LEVEL=debug (或在.env文件中设置)
# 2. 设置日志文件: export LOG_FILE=log.txt (或在.env文件中设置)
# 3. 设置日志格式: export LOG_FORMAT=json (text 或 json)
# 4. 设置日志轮换: export LOG_MAX_SIZE_MB=10 LOG_BACKUP_COUNT=5
