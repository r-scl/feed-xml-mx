#!/usr/bin/env python3
"""
Comprehensive monitoring and observability for FeedXML-MX 2025
Implements structured logging, metrics, tracing, and alerting
"""

import asyncio
import psutil
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass, field

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
    structlog = type('MockStructlog', (), {'get_logger': lambda name: MockLogger()})()

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from pydantic import BaseModel, Field

try:
    from error_handling import FeedXMLError, ErrorSeverity
except ImportError:
    # Fallback error classes
    class FeedXMLError(Exception): pass
    class ErrorSeverity: 
        INFO = "info"
        WARNING = "warning"
        ERROR = "error"


class MetricType(str, Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMING = "timing"


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MetricPoint:
    """Individual metric data point"""
    name: str
    value: Union[int, float]
    metric_type: MetricType
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'value': self.value,
            'type': self.metric_type.value,
            'timestamp': self.timestamp,
            'tags': self.tags
        }


@dataclass
class Alert:
    """Alert data structure"""
    name: str
    message: str
    severity: AlertSeverity
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'message': self.message,
            'severity': self.severity.value,
            'timestamp': self.timestamp,
            'context': self.context,
            'resolved': self.resolved
        }


class PerformanceMetrics(BaseModel):
    """System performance metrics"""
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    memory_used_mb: float = Field(ge=0)
    memory_available_mb: float = Field(ge=0)
    disk_usage_percent: float = Field(ge=0, le=100)
    load_average: Optional[float] = None
    open_file_descriptors: Optional[int] = None
    network_connections: Optional[int] = None


class ApplicationMetrics(BaseModel):
    """Application-specific metrics"""
    total_requests: int = Field(ge=0, default=0)
    successful_requests: int = Field(ge=0, default=0)
    failed_requests: int = Field(ge=0, default=0)
    active_scrapers: int = Field(ge=0, default=0)
    cache_hit_ratio: float = Field(ge=0, le=1, default=0)
    average_response_time: float = Field(ge=0, default=0)
    products_processed: int = Field(ge=0, default=0)
    feeds_generated: int = Field(ge=0, default=0)
    errors_per_hour: int = Field(ge=0, default=0)


class MetricsCollector:
    """Collects and stores application metrics"""
    
    def __init__(self, max_points: int = 10000):
        self.max_points = max_points
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points))
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        
        # Application-specific metrics
        self.app_metrics = ApplicationMetrics()
        
        # Performance tracking
        self.last_system_check = 0
        self.system_metrics_cache = None
        self.cache_ttl = 30  # 30 seconds
    
    def increment_counter(self, name: str, value: float = 1, tags: Optional[Dict[str, str]] = None):
        """Increment a counter metric"""
        self.counters[name] += value
        self._record_metric(name, self.counters[name], MetricType.COUNTER, tags)
    
    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Set a gauge metric"""
        self.gauges[name] = value
        self._record_metric(name, value, MetricType.GAUGE, tags)
    
    def record_timing(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record a timing metric"""
        self.histograms[name].append(value)
        self._record_metric(name, value, MetricType.TIMING, tags)
    
    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record a histogram metric"""
        self.histograms[name].append(value)
        self._record_metric(name, value, MetricType.HISTOGRAM, tags)
    
    def _record_metric(self, name: str, value: float, metric_type: MetricType, tags: Optional[Dict[str, str]]):
        """Internal method to record metric"""
        point = MetricPoint(name, value, metric_type, tags=tags or {})
        self.metrics[name].append(point)
    
    def get_system_metrics(self) -> PerformanceMetrics:
        """Get current system performance metrics"""
        current_time = time.time()
        
        # Use cache if recent
        if (self.system_metrics_cache and 
            current_time - self.last_system_check < self.cache_ttl):
            return self.system_metrics_cache
        
        if not PSUTIL_AVAILABLE:
            # Return mock metrics when psutil is not available
            return PerformanceMetrics(
                cpu_percent=10.0, memory_percent=50.0, memory_used_mb=1024.0,
                memory_available_mb=2048.0, disk_usage_percent=30.0
            )
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Load average (Unix systems only)
            load_avg = None
            try:
                load_avg = psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else None
            except (AttributeError, OSError):
                pass
            
            # File descriptors (Unix systems only)
            open_fds = None
            try:
                process = psutil.Process()
                open_fds = process.num_fds() if hasattr(process, 'num_fds') else None
            except (AttributeError, psutil.NoSuchProcess):
                pass
            
            # Network connections
            net_connections = None
            try:
                net_connections = len(psutil.net_connections())
            except (psutil.AccessDenied, OSError):
                pass
            
            metrics = PerformanceMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                memory_available_mb=memory.available / (1024 * 1024),
                disk_usage_percent=disk.percent,
                load_average=load_avg,
                open_file_descriptors=open_fds,
                network_connections=net_connections
            )
            
            # Cache the result
            self.system_metrics_cache = metrics
            self.last_system_check = current_time
            
            # Record as metrics
            self.set_gauge("system.cpu_percent", cpu_percent)
            self.set_gauge("system.memory_percent", memory.percent)
            self.set_gauge("system.memory_used_mb", memory.used / (1024 * 1024))
            self.set_gauge("system.disk_usage_percent", disk.percent)
            
            if load_avg is not None:
                self.set_gauge("system.load_average", load_avg)
            
            return metrics
            
        except Exception as e:
            structlog.get_logger().warning("Failed to collect system metrics", error=str(e))
            return PerformanceMetrics(
                cpu_percent=0, memory_percent=0, memory_used_mb=0,
                memory_available_mb=0, disk_usage_percent=0
            )
    
    def get_metrics_summary(self, since_minutes: int = 60) -> Dict[str, Any]:
        """Get metrics summary for the last N minutes"""
        cutoff_time = time.time() - (since_minutes * 60)
        summary = {}
        
        for name, points in self.metrics.items():
            recent_points = [p for p in points if p.timestamp > cutoff_time]
            
            if not recent_points:
                continue
            
            values = [p.value for p in recent_points]
            summary[name] = {
                'count': len(values),
                'avg': sum(values) / len(values),
                'min': min(values),
                'max': max(values),
                'latest': values[-1] if values else 0
            }
        
        return summary
    
    def update_app_metrics(self, **kwargs):
        """Update application metrics"""
        for key, value in kwargs.items():
            if hasattr(self.app_metrics, key):
                setattr(self.app_metrics, key, value)
        
        # Record as individual metrics
        for field_name in self.app_metrics.__fields__:
            value = getattr(self.app_metrics, field_name)
            self.set_gauge(f"app.{field_name}", float(value))


class AlertManager:
    """Manages alerts and notifications"""
    
    def __init__(self):
        self.alerts: List[Alert] = []
        self.alert_rules: List[Callable] = []
        self.max_alerts = 1000
        
        # Alert thresholds
        self.thresholds = {
            'cpu_percent': 80,
            'memory_percent': 85,
            'disk_usage_percent': 90,
            'error_rate': 0.1,  # 10% error rate
            'response_time': 30,  # 30 seconds
        }
    
    def add_alert_rule(self, rule: Callable[[Dict[str, Any]], Optional[Alert]]):
        """Add custom alert rule"""
        self.alert_rules.append(rule)
    
    def check_alerts(self, metrics: Dict[str, Any], system_metrics: PerformanceMetrics):
        """Check all alert conditions"""
        
        # System alerts
        if system_metrics.cpu_percent > self.thresholds['cpu_percent']:
            self.create_alert(
                "high_cpu_usage",
                f"CPU usage is {system_metrics.cpu_percent:.1f}%",
                AlertSeverity.WARNING,
                {'cpu_percent': system_metrics.cpu_percent}
            )
        
        if system_metrics.memory_percent > self.thresholds['memory_percent']:
            self.create_alert(
                "high_memory_usage",
                f"Memory usage is {system_metrics.memory_percent:.1f}%",
                AlertSeverity.WARNING,
                {'memory_percent': system_metrics.memory_percent}
            )
        
        if system_metrics.disk_usage_percent > self.thresholds['disk_usage_percent']:
            self.create_alert(
                "high_disk_usage",
                f"Disk usage is {system_metrics.disk_usage_percent:.1f}%",
                AlertSeverity.ERROR,
                {'disk_usage_percent': system_metrics.disk_usage_percent}
            )
        
        # Application alerts
        total_requests = metrics.get('app.total_requests', {}).get('latest', 0)
        failed_requests = metrics.get('app.failed_requests', {}).get('latest', 0)
        
        if total_requests > 0:
            error_rate = failed_requests / total_requests
            if error_rate > self.thresholds['error_rate']:
                self.create_alert(
                    "high_error_rate",
                    f"Error rate is {error_rate:.2%}",
                    AlertSeverity.ERROR,
                    {'error_rate': error_rate, 'total_requests': total_requests, 'failed_requests': failed_requests}
                )
        
        avg_response_time = metrics.get('app.average_response_time', {}).get('latest', 0)
        if avg_response_time > self.thresholds['response_time']:
            self.create_alert(
                "slow_response_time",
                f"Average response time is {avg_response_time:.1f}s",
                AlertSeverity.WARNING,
                {'response_time': avg_response_time}
            )
        
        # Custom alert rules
        for rule in self.alert_rules:
            try:
                alert = rule(metrics)
                if alert:
                    self.alerts.append(alert)
            except Exception as e:
                structlog.get_logger().error("Alert rule failed", error=str(e))
    
    def create_alert(self, name: str, message: str, severity: AlertSeverity, context: Dict[str, Any]):
        """Create a new alert"""
        # Check if similar alert already exists
        for alert in self.alerts[-10:]:  # Check last 10 alerts
            if (alert.name == name and not alert.resolved and 
                time.time() - alert.timestamp < 300):  # 5 minutes
                return  # Don't create duplicate alert
        
        alert = Alert(name, message, severity, context=context)
        self.alerts.append(alert)
        
        # Limit alert history
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]
        
        # Log alert
        logger = structlog.get_logger()
        log_method = getattr(logger, severity.value)
        log_method("Alert triggered", alert=alert.to_dict())
    
    def resolve_alert(self, name: str):
        """Mark alerts as resolved"""
        for alert in self.alerts:
            if alert.name == name and not alert.resolved:
                alert.resolved = True
                structlog.get_logger().info("Alert resolved", alert_name=name)
    
    def get_active_alerts(self) -> List[Alert]:
        """Get currently active alerts"""
        return [alert for alert in self.alerts if not alert.resolved]
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary"""
        active_alerts = self.get_active_alerts()
        
        by_severity = defaultdict(int)
        for alert in active_alerts:
            by_severity[alert.severity.value] += 1
        
        return {
            'total_active': len(active_alerts),
            'by_severity': dict(by_severity),
            'recent_alerts': [alert.to_dict() for alert in self.alerts[-10:]]
        }


class PerformanceTracker:
    """Track function and operation performance"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.active_operations: Dict[str, float] = {}
    
    @asynccontextmanager
    async def track_operation(self, operation_name: str, tags: Optional[Dict[str, str]] = None):
        """Context manager to track operation performance"""
        start_time = time.time()
        operation_id = f"{operation_name}_{id(asyncio.current_task())}"
        
        self.active_operations[operation_id] = start_time
        self.metrics.set_gauge("active_operations", len(self.active_operations))
        
        try:
            yield
            # Success
            duration = time.time() - start_time
            self.metrics.record_timing(f"operation.{operation_name}.duration", duration, tags)
            self.metrics.increment_counter(f"operation.{operation_name}.success", tags=tags)
            
        except Exception as e:
            # Failure
            duration = time.time() - start_time
            self.metrics.record_timing(f"operation.{operation_name}.duration", duration, tags)
            self.metrics.increment_counter(f"operation.{operation_name}.error", tags=tags)
            
            # Log error with performance context
            structlog.get_logger().error(
                "Operation failed",
                operation=operation_name,
                duration=duration,
                error=str(e),
                tags=tags
            )
            raise
            
        finally:
            self.active_operations.pop(operation_id, None)
            self.metrics.set_gauge("active_operations", len(self.active_operations))
    
    def track_function(self, function_name: Optional[str] = None, tags: Optional[Dict[str, str]] = None):
        """Decorator to track function performance"""
        def decorator(func):
            name = function_name or f"{func.__module__}.{func.__name__}"
            
            if asyncio.iscoroutinefunction(func):
                async def async_wrapper(*args, **kwargs):
                    async with self.track_operation(name, tags):
                        return await func(*args, **kwargs)
                return async_wrapper
            else:
                def sync_wrapper(*args, **kwargs):
                    start_time = time.time()
                    try:
                        result = func(*args, **kwargs)
                        duration = time.time() - start_time
                        self.metrics.record_timing(f"function.{name}.duration", duration, tags)
                        self.metrics.increment_counter(f"function.{name}.success", tags=tags)
                        return result
                    except Exception as e:
                        duration = time.time() - start_time
                        self.metrics.record_timing(f"function.{name}.duration", duration, tags)
                        self.metrics.increment_counter(f"function.{name}.error", tags=tags)
                        raise
                return sync_wrapper
        return decorator


class HealthChecker:
    """Health check system"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.health_checks: Dict[str, Callable] = {}
        
    def register_health_check(self, name: str, check_func: Callable[[], bool]):
        """Register a health check function"""
        self.health_checks[name] = check_func
    
    async def run_health_checks(self) -> Dict[str, Any]:
        """Run all health checks"""
        results = {}
        overall_healthy = True
        
        for name, check_func in self.health_checks.items():
            try:
                start_time = time.time()
                
                # Run check with timeout
                if asyncio.iscoroutinefunction(check_func):
                    healthy = await asyncio.wait_for(check_func(), timeout=10)
                else:
                    healthy = check_func()
                
                duration = time.time() - start_time
                
                results[name] = {
                    'healthy': healthy,
                    'duration': duration,
                    'timestamp': time.time()
                }
                
                if not healthy:
                    overall_healthy = False
                
                # Record metrics
                self.metrics.record_timing(f"health_check.{name}.duration", duration)
                self.metrics.set_gauge(f"health_check.{name}.status", 1 if healthy else 0)
                
            except Exception as e:
                results[name] = {
                    'healthy': False,
                    'error': str(e),
                    'timestamp': time.time()
                }
                overall_healthy = False
                self.metrics.set_gauge(f"health_check.{name}.status", 0)
        
        results['overall'] = {'healthy': overall_healthy}
        self.metrics.set_gauge("health_check.overall.status", 1 if overall_healthy else 0)
        
        return results


class MonitoringManager:
    """Main monitoring manager coordinating all monitoring components"""
    
    def __init__(self):
        self.metrics = MetricsCollector()
        self.alerts = AlertManager()
        self.performance = PerformanceTracker(self.metrics)
        self.health = HealthChecker(self.metrics)
        
        self._monitoring_task: Optional[asyncio.Task] = None
        self._monitoring_interval = 60  # 1 minute
        
        # Setup default health checks
        self._setup_default_health_checks()
        
        # Setup default alert rules
        self._setup_default_alert_rules()
    
    def _setup_default_health_checks(self):
        """Setup default health checks"""
        
        def memory_check():
            system_metrics = self.metrics.get_system_metrics()
            return system_metrics.memory_percent < 90
        
        def disk_check():
            system_metrics = self.metrics.get_system_metrics()
            return system_metrics.disk_usage_percent < 95
        
        self.health.register_health_check("memory", memory_check)
        self.health.register_health_check("disk", disk_check)
    
    def _setup_default_alert_rules(self):
        """Setup default alert rules"""
        
        def check_scraping_performance(metrics: Dict[str, Any]) -> Optional[Alert]:
            avg_response = metrics.get('app.average_response_time', {}).get('latest', 0)
            if avg_response > 60:  # 1 minute
                return Alert(
                    "slow_scraping",
                    f"Scraping is taking too long: {avg_response:.1f}s average",
                    AlertSeverity.WARNING,
                    context={'avg_response_time': avg_response}
                )
            return None
        
        self.alerts.add_alert_rule(check_scraping_performance)
    
    async def start_monitoring(self):
        """Start background monitoring task"""
        if self._monitoring_task and not self._monitoring_task.done():
            return
        
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        structlog.get_logger().info("Monitoring started")
    
    async def stop_monitoring(self):
        """Stop background monitoring"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        structlog.get_logger().info("Monitoring stopped")
    
    async def _monitoring_loop(self):
        """Background monitoring loop"""
        while True:
            try:
                # Collect system metrics
                system_metrics = self.metrics.get_system_metrics()
                
                # Get metrics summary
                metrics_summary = self.metrics.get_metrics_summary()
                
                # Check alerts
                self.alerts.check_alerts(metrics_summary, system_metrics)
                
                # Run health checks
                health_results = await self.health.run_health_checks()
                
                # Log summary
                structlog.get_logger().info(
                    "Monitoring cycle completed",
                    system_metrics=system_metrics.dict(),
                    active_alerts=len(self.alerts.get_active_alerts()),
                    health_status=health_results['overall']['healthy']
                )
                
                await asyncio.sleep(self._monitoring_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                structlog.get_logger().error("Monitoring loop error", error=str(e))
                await asyncio.sleep(10)  # Wait before retrying
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive monitoring data for dashboard"""
        return {
            'timestamp': datetime.now().isoformat(),
            'system_metrics': self.metrics.get_system_metrics().dict(),
            'app_metrics': self.metrics.app_metrics.dict(),
            'metrics_summary': self.metrics.get_metrics_summary(60),  # Last hour
            'alerts': self.alerts.get_alert_summary(),
            'health_checks': asyncio.create_task(self.health.run_health_checks()) if asyncio.get_event_loop().is_running() else None,
            'performance_stats': {
                'active_operations': len(self.performance.active_operations),
                'cache_entries': len(self.metrics.metrics)
            }
        }


# Global monitoring instance
monitoring = MonitoringManager()

# Convenience functions
track_operation = monitoring.performance.track_operation
track_function = monitoring.performance.track_function