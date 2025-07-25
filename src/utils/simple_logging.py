"""Simple logging configuration that shows only event messages."""

import json
import logging
import sys


class EventOnlyFormatter(logging.Formatter):
    """Formatter that extracts and displays only event messages from JSON logs."""

    def format(self, record):
        """Format log record to show only the event message."""
        try:
            # If the message is JSON, extract the event
            if hasattr(record, "getMessage"):
                msg = record.getMessage()
                if msg.startswith("{") and "event" in msg:
                    log_data = json.loads(msg)
                    event = log_data.get("event", msg)

                    # Add prefix based on log level
                    if record.levelno >= logging.ERROR:
                        return f"❌ {event}"
                    elif record.levelno >= logging.WARNING:
                        return f"⚠️  {event}"
                    else:
                        return f"✓ {event}"
        except:
            # If parsing fails, return original message
            pass

        # Default formatting for non-JSON logs
        return record.getMessage()


def setup_simple_logging(level=logging.INFO):
    """Configure logging to show only event messages.

    Args:
        level: Logging level (default: INFO)

    """
    # Remove all existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler with event-only formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(EventOnlyFormatter())

    # Add handler to root logger
    root_logger.addHandler(console_handler)
    root_logger.setLevel(level)

    # Also configure structlog to output simple format
    try:
        import structlog

        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.dict_tracebacks,
                structlog.dev.ConsoleRenderer(colors=False),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    except ImportError:
        pass


def suppress_verbose_logging():
    """Suppress verbose logging from specific modules."""
    # List of modules to suppress
    verbose_modules = [
        "src.clients",
        "src.core",
        "src.storage",
        "src.agents",
        "src.utils.subprocess_manager",
        "httpx",
        "httpcore",
        "anthropic",
    ]

    for module in verbose_modules:
        logging.getLogger(module).setLevel(logging.WARNING)


# Convenience function to set up clean logging
def use_clean_logging():
    """Set up clean logging with minimal output."""
    setup_simple_logging()
    suppress_verbose_logging()
