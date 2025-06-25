"""Logging configuration for the Agentic Coding System.

This module sets up structured logging with multiple handlers, formatters,
and contextual information for debugging and monitoring.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import orjson
import structlog
from rich.console import Console
from rich.logging import RichHandler
from structlog.processors import CallsiteParameter

from config import LogLevel, get_settings


console = Console()


class OrjsonRenderer:
    """Custom JSON renderer using orjson for better performance."""
    
    def __call__(self, logger: Any, name: str, event_dict: Dict[str, Any]) -> str:
        """Render log event as JSON.
        
        Args:
            logger: Logger instance
            name: Logger name
            event_dict: Event dictionary
            
        Returns:
            JSON-encoded string
        """
        return orjson.dumps(event_dict).decode("utf-8")


def add_timestamp(logger: Any, name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add ISO format timestamp to log events.
    
    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary
        
    Returns:
        Updated event dictionary
    """
    event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return event_dict


def add_app_context(logger: Any, name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add application context to log events.
    
    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary
        
    Returns:
        Updated event dictionary
    """
    settings = get_settings()
    event_dict["app"] = {
        "name": settings.project_name,
        "version": settings.version,
        "environment": settings.environment.value,
    }
    return event_dict


def filter_sensitive_data(logger: Any, name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Filter sensitive data from logs.
    
    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary
        
    Returns:
        Filtered event dictionary
    """
    sensitive_keys = {
        "password", "token", "secret", "api_key", "apikey", 
        "auth", "credential", "private_key", "privatekey"
    }
    
    def _filter_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively filter sensitive keys from dictionary."""
        filtered = {}
        for key, value in d.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                filtered[key] = "***REDACTED***"
            elif isinstance(value, dict):
                filtered[key] = _filter_dict(value)
            elif isinstance(value, list):
                filtered[key] = [
                    _filter_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                filtered[key] = value
        return filtered
    
    return _filter_dict(event_dict)


def setup_logging(
    log_level: Optional[LogLevel] = None,
    log_file: Optional[Path] = None,
    use_json: Optional[bool] = None,
) -> None:
    """Configure logging for the application.
    
    Args:
        log_level: Override default log level
        log_file: Override default log file path
        use_json: Override JSON formatting setting
    """
    settings = get_settings()
    
    # Use provided values or fall back to settings
    log_level = log_level or settings.logging.level
    log_file = log_file or settings.logging.file_path
    use_json = use_json if use_json is not None else (settings.logging.format == "json")
    
    # Common processors
    base_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_timestamp,
        add_app_context,
        filter_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    # Add callsite info in debug mode
    if settings.debug or log_level == LogLevel.DEBUG:
        base_processors.insert(
            -1,
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    CallsiteParameter.FILENAME,
                    CallsiteParameter.FUNC_NAME,
                    CallsiteParameter.LINENO,
                ]
            ),
        )
    
    # Configure structlog
    if use_json:
        renderer = OrjsonRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    structlog.configure(
        processors=base_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.value))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    if use_json:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=renderer,
                foreign_pre_chain=base_processors,
            )
        )
    else:
        console_handler = RichHandler(
            console=console,
            show_time=False,  # We add our own timestamp
            show_path=settings.debug,
            rich_tracebacks=True,
            tracebacks_show_locals=settings.debug,
        )
        console_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=renderer,
                foreign_pre_chain=base_processors,
            )
        )
    
    root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        if settings.logging.max_file_size_mb > 0:
            from logging.handlers import RotatingFileHandler
            
            file_handler = RotatingFileHandler(
                str(log_file),
                maxBytes=settings.logging.max_file_size_mb * 1024 * 1024,
                backupCount=settings.logging.backup_count,
                encoding="utf-8",
            )
        else:
            file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        
        # Always use JSON for file logging
        file_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=OrjsonRenderer(),
                foreign_pre_chain=base_processors,
            )
        )
        
        root_logger.addHandler(file_handler)
    
    # Configure third-party loggers
    configure_third_party_loggers(log_level)
    
    # Log initialization
    logger = structlog.get_logger(__name__)
    logger.info(
        "Logging configured",
        log_level=log_level.value,
        use_json=use_json,
        log_file=str(log_file) if log_file else None,
        handlers=len(root_logger.handlers),
    )


def configure_third_party_loggers(log_level: LogLevel) -> None:
    """Configure log levels for third-party libraries.
    
    Args:
        log_level: Application log level
    """
    # Suppress noisy loggers
    noisy_loggers = [
        "urllib3",
        "httpx",
        "httpcore",
        "asyncio",
        "aiohttp",
    ]
    
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    # Set Anthropic SDK to match our level
    logging.getLogger("anthropic").setLevel(getattr(logging, log_level.value))


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """Get a configured logger instance.
    
    Args:
        name: Logger name (defaults to caller's module)
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding temporary log context."""
    
    def __init__(self, **kwargs: Any):
        """Initialize with context values.
        
        Args:
            **kwargs: Key-value pairs to add to log context
        """
        self.context = kwargs
        self.tokens: list = []
    
    def __enter__(self) -> "LogContext":
        """Enter context and bind values."""
        for key, value in self.context.items():
            token = structlog.contextvars.bind_contextvars(**{key: value})
            self.tokens.append(token)
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and unbind values."""
        for token in self.tokens:
            structlog.contextvars.unbind_contextvars(token)


def log_execution_time(func_name: str) -> Any:
    """Decorator to log function execution time.
    
    Args:
        func_name: Name to use in logs
        
    Returns:
        Decorator function
    """
    def decorator(func: Any) -> Any:
        """Actual decorator."""
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Async wrapper function."""
            logger = get_logger(func.__module__)
            start_time = datetime.utcnow()
            
            try:
                logger.debug(f"Starting {func_name}")
                result = await func(*args, **kwargs)
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                logger.info(
                    f"Completed {func_name}",
                    elapsed_seconds=elapsed,
                    success=True,
                )
                return result
                
            except Exception as e:
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                logger.error(
                    f"Failed {func_name}",
                    elapsed_seconds=elapsed,
                    success=False,
                    error=str(e),
                    exc_info=True,
                )
                raise
        
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Sync wrapper function."""
            logger = get_logger(func.__module__)
            start_time = datetime.utcnow()
            
            try:
                logger.debug(f"Starting {func_name}")
                result = func(*args, **kwargs)
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                logger.info(
                    f"Completed {func_name}",
                    elapsed_seconds=elapsed,
                    success=True,
                )
                return result
                
            except Exception as e:
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                logger.error(
                    f"Failed {func_name}",
                    elapsed_seconds=elapsed,
                    success=False,
                    error=str(e),
                    exc_info=True,
                )
                raise
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Initialize logging on module import if settings are available
try:
    setup_logging()
except Exception:
    # Settings might not be available during testing or initial setup
    pass