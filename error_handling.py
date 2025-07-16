#!/usr/bin/env python3
"""
Centralized error handling and custom exceptions
Following 2025 best practices for async error management
"""

import asyncio
import sys
import traceback
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    # Simple fallback logger
    class MockLogger:
        def info(self, msg, **kwargs): print(f"INFO: {msg} {kwargs}")
        def warning(self, msg, **kwargs): print(f"WARNING: {msg} {kwargs}")
        def error(self, msg, **kwargs): print(f"ERROR: {msg} {kwargs}")
        def exception(self, msg, **kwargs): print(f"EXCEPTION: {msg} {kwargs}")
    structlog = type('MockStructlog', (), {'get_logger': lambda name: MockLogger()})()

from pydantic import BaseModel, Field


class ErrorSeverity(str, Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Error categories for better classification"""
    NETWORK = "network"
    VALIDATION = "validation"
    SCRAPING = "scraping"
    PROCESSING = "processing"
    CONFIGURATION = "configuration"
    EXTERNAL_API = "external_api"
    SYSTEM = "system"


class FeedXMLError(Exception):
    """Base exception for all FeedXML-MX errors"""
    
    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
        is_operational: bool = True
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.original_error = original_error
        self.is_operational = is_operational
        self.timestamp = datetime.now()
        
        # Capture stack trace
        self.stack_trace = traceback.format_exc() if original_error else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context,
            "original_error": str(self.original_error) if self.original_error else None,
            "is_operational": self.is_operational,
            "timestamp": self.timestamp.isoformat(),
            "stack_trace": self.stack_trace
        }


class ScrapingError(FeedXMLError):
    """Errors related to web scraping operations"""
    
    def __init__(self, message: str, product_id: Optional[str] = None, url: Optional[str] = None, **kwargs):
        context = kwargs.pop('context', {})
        context.update({
            'product_id': product_id,
            'url': url
        })
        super().__init__(message, category=ErrorCategory.SCRAPING, context=context, **kwargs)


class ValidationError(FeedXMLError):
    """Errors related to data validation"""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Any = None, **kwargs):
        context = kwargs.pop('context', {})
        context.update({
            'field': field,
            'value': str(value) if value is not None else None
        })
        super().__init__(message, category=ErrorCategory.VALIDATION, context=context, **kwargs)


class NetworkError(FeedXMLError):
    """Errors related to network operations"""
    
    def __init__(self, message: str, url: Optional[str] = None, status_code: Optional[int] = None, **kwargs):
        context = kwargs.pop('context', {})
        context.update({
            'url': url,
            'status_code': status_code
        })
        super().__init__(message, category=ErrorCategory.NETWORK, context=context, **kwargs)


class ProcessingError(FeedXMLError):
    """Errors related to feed processing"""
    
    def __init__(self, message: str, feed_type: Optional[str] = None, product_count: Optional[int] = None, **kwargs):
        context = kwargs.pop('context', {})
        context.update({
            'feed_type': feed_type,
            'product_count': product_count
        })
        super().__init__(message, category=ErrorCategory.PROCESSING, context=context, **kwargs)


class ConfigurationError(FeedXMLError):
    """Errors related to configuration"""
    
    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        context = kwargs.pop('context', {})
        context.update({
            'config_key': config_key
        })
        super().__init__(
            message, 
            category=ErrorCategory.CONFIGURATION, 
            severity=ErrorSeverity.HIGH, 
            is_operational=False,  # Configuration errors are not operational
            context=context, 
            **kwargs
        )


class ErrorMetrics(BaseModel):
    """Error metrics for monitoring"""
    total_errors: int = 0
    errors_by_category: Dict[str, int] = Field(default_factory=dict)
    errors_by_severity: Dict[str, int] = Field(default_factory=dict)
    last_error: Optional[datetime] = None
    

class ErrorHandler:
    """Centralized error handler following 2025 best practices"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.metrics = ErrorMetrics()
        self._shutdown_requested = False
    
    async def handle_error(
        self, 
        error: Exception, 
        context: Optional[Dict[str, Any]] = None,
        response_stream: Any = None
    ) -> None:
        """
        Handle errors with centralized logging and monitoring
        Following async best practices from Node.js guide
        """
        try:
            # Convert to FeedXMLError if needed
            if not isinstance(error, FeedXMLError):
                error = FeedXMLError(
                    str(error),
                    original_error=error,
                    context=context
                )
            
            # Update metrics
            self._update_metrics(error)
            
            # Log error with structured logging
            await self._log_error(error)
            
            # Handle critical errors
            if error.severity == ErrorSeverity.CRITICAL:
                await self._handle_critical_error(error)
            
            # Send alerts if needed
            await self._send_alerts_if_needed(error)
            
            # Handle response if provided
            if response_stream and hasattr(response_stream, 'status'):
                await self._send_error_response(error, response_stream)
                
        except Exception as handler_error:
            # Error in error handler - log to stderr and continue
            sys.stderr.write(f"Error in error handler: {handler_error}\n")
            sys.stderr.flush()
    
    def is_trusted_error(self, error: Exception) -> bool:
        """
        Determine if error is operational/trusted
        Following Node.js best practices
        """
        if isinstance(error, FeedXMLError):
            return error.is_operational
        
        # Common trusted errors
        trusted_error_types = (
            ConnectionError,
            TimeoutError,
            ValueError,  # Usually input validation
        )
        
        return isinstance(error, trusted_error_types)
    
    async def _log_error(self, error: FeedXMLError) -> None:
        """Log error with appropriate level and structure"""
        log_data = error.to_dict()
        
        if error.severity == ErrorSeverity.CRITICAL:
            self.logger.critical("Critical error occurred", **log_data)
        elif error.severity == ErrorSeverity.HIGH:
            self.logger.error("High severity error", **log_data)
        elif error.severity == ErrorSeverity.MEDIUM:
            self.logger.warning("Medium severity error", **log_data)
        else:
            self.logger.info("Low severity error", **log_data)
    
    async def _handle_critical_error(self, error: FeedXMLError) -> None:
        """Handle critical errors that might require process restart"""
        self.logger.critical(
            "Critical error - system stability may be compromised",
            error_details=error.to_dict()
        )
        
        # For now, just mark that shutdown was requested
        # In production, this could trigger graceful shutdown
        self._shutdown_requested = True
    
    async def _send_alerts_if_needed(self, error: FeedXMLError) -> None:
        """Send alerts for high/critical severity errors"""
        if error.severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
            # In production, integrate with monitoring systems
            # For now, just log an alert
            self.logger.warning(
                "Alert: High/critical error requires attention",
                error_summary=error.to_dict()
            )
    
    async def _send_error_response(self, error: FeedXMLError, response_stream: Any) -> None:
        """Send appropriate error response if handling HTTP request"""
        try:
            # Determine status code based on error type
            status_code = 500  # Default internal server error
            
            if isinstance(error, NetworkError):
                status_code = error.context.get('status_code', 502)
            elif isinstance(error, ValidationError):
                status_code = 400
            elif isinstance(error, ConfigurationError):
                status_code = 500
            
            # Send minimal error info to client (don't expose internals)
            error_response = {
                "error": True,
                "message": "An error occurred processing your request",
                "timestamp": datetime.now().isoformat()
            }
            
            # In development, include more details
            if hasattr(response_stream, 'json'):
                await response_stream.json(error_response, status_code=status_code)
                
        except Exception:
            # If we can't send response, just continue
            pass
    
    def _update_metrics(self, error: FeedXMLError) -> None:
        """Update error metrics for monitoring"""
        self.metrics.total_errors += 1
        self.metrics.last_error = error.timestamp
        
        # Update category metrics
        category = error.category.value
        self.metrics.errors_by_category[category] = (
            self.metrics.errors_by_category.get(category, 0) + 1
        )
        
        # Update severity metrics
        severity = error.severity.value
        self.metrics.errors_by_severity[severity] = (
            self.metrics.errors_by_severity.get(severity, 0) + 1
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current error metrics"""
        return self.metrics.model_dump()
    
    @property
    def should_shutdown(self) -> bool:
        """Check if shutdown was requested due to critical errors"""
        return self._shutdown_requested


# Global error handler instance
error_handler = ErrorHandler()


def setup_global_error_handlers():
    """Setup global error handlers for unhandled exceptions"""
    
    def handle_exception(exc_type, exc_value, exc_traceback):
        """Handle uncaught exceptions"""
        if issubclass(exc_type, KeyboardInterrupt):
            # Allow keyboard interrupt to work normally
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        # Create error and handle it
        error = FeedXMLError(
            f"Uncaught exception: {exc_value}",
            severity=ErrorSeverity.CRITICAL,
            is_operational=False,
            original_error=exc_value,
            context={
                'exception_type': exc_type.__name__,
                'traceback': ''.join(traceback.format_tb(exc_traceback))
            }
        )
        
        # Use asyncio to handle the error if we're in an async context
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(error_handler.handle_error(error))
        except RuntimeError:
            # No event loop running, handle synchronously
            asyncio.run(error_handler.handle_error(error))
        
        # Exit if it's a non-trusted error
        if not error_handler.is_trusted_error(exc_value):
            sys.exit(1)
    
    def handle_unhandled_rejection(loop, context):
        """Handle unhandled promise rejections (async equivalent)"""
        exception = context.get('exception')
        if exception:
            error = FeedXMLError(
                f"Unhandled async exception: {exception}",
                severity=ErrorSeverity.HIGH,
                original_error=exception,
                context=context
            )
            
            # Handle the error
            loop.create_task(error_handler.handle_error(error))
            
            # Exit if non-trusted
            if not error_handler.is_trusted_error(exception):
                loop.call_soon(lambda: sys.exit(1))
    
    # Set global exception handler
    sys.excepthook = handle_exception
    
    # Set async exception handler if we have an event loop
    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(handle_unhandled_rejection)
    except RuntimeError:
        # No event loop running yet
        pass


# Decorator for wrapping async functions with error handling
def handle_async_errors(func):
    """Decorator to handle async function errors"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            await error_handler.handle_error(e)
            if not error_handler.is_trusted_error(e):
                raise
    return wrapper


# Context manager for error handling
class ErrorContext:
    """Context manager for handling errors in a specific context"""
    
    def __init__(self, context: Dict[str, Any], reraise: bool = True):
        self.context = context
        self.reraise = reraise
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_value:
            await error_handler.handle_error(exc_value, context=self.context)
            if self.reraise and not error_handler.is_trusted_error(exc_value):
                return False  # Re-raise the exception
        return True  # Suppress the exception