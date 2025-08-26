"""
Logging utilities for the Injective Market Making Bot.
"""

import logging
import sys
from typing import Optional
import structlog
from config.settings import settings


def setup_logger(name: str = "injective_bot", level: Optional[str] = None) -> structlog.BoundLogger:
    """
    Set up structured logging for the application.
    
    Args:
        name: Logger name
        level: Log level (debug, info, warning, error)
        
    Returns:
        Configured structured logger
    """
    log_level = level or settings.log_level.upper()
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level),
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    return structlog.get_logger(name)


# Global logger instance
logger = setup_logger()


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Module name
        
    Returns:
        Logger instance
    """
    return structlog.get_logger(name)
