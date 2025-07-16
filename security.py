#!/usr/bin/env python3
"""
Security utilities and best practices for FeedXML-MX 2025
Implements defense-in-depth security measures
"""

import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, List, Optional, Set, Union
from urllib.parse import urlparse

try:
    import structlog
except ImportError:
    class MockLogger:
        def info(self, msg, **kwargs): print(f"INFO: {msg} {kwargs}")
        def warning(self, msg, **kwargs): print(f"WARNING: {msg} {kwargs}")
        def error(self, msg, **kwargs): print(f"ERROR: {msg} {kwargs}")
    structlog = type('MockStructlog', (), {'get_logger': lambda name: MockLogger()})()

from pydantic import BaseModel, Field, validator

from error_handling import ConfigurationError, SecurityError, ErrorSeverity


logger = structlog.get_logger(__name__)


class SecurityConfig(BaseModel):
    """Security configuration with secure defaults"""
    
    # Rate limiting
    max_requests_per_minute: int = Field(default=60, ge=1, le=1000)
    max_requests_per_hour: int = Field(default=3600, ge=1, le=10000)
    
    # URL validation
    allowed_domains: Set[str] = Field(default={'tienda.accu-chek.com.mx', 'cdn.gdar.com.mx'})
    blocked_domains: Set[str] = Field(default={'malicious-site.com'})
    
    # Content security
    max_content_length: int = Field(default=10_000_000, ge=1000, le=100_000_000)  # 10MB
    max_description_length: int = Field(default=5000, ge=100, le=10000)
    
    # Request security
    request_timeout: int = Field(default=30, ge=5, le=120)
    max_redirects: int = Field(default=3, ge=0, le=10)
    
    # File security
    allowed_file_extensions: Set[str] = Field(default={'.xml', '.json', '.txt'})
    max_file_size: int = Field(default=50_000_000, ge=1000)  # 50MB
    
    # Data validation
    enable_strict_validation: bool = Field(default=True)
    sanitize_html: bool = Field(default=True)
    validate_urls: bool = Field(default=True)


class RequestTracker:
    """Track requests for rate limiting and anomaly detection"""
    
    def __init__(self):
        self.requests: Dict[str, List[float]] = {}  # IP -> timestamps
        self.blocked_ips: Set[str] = set()
        self.blocked_until: Dict[str, float] = {}  # IP -> unblock timestamp
    
    def is_rate_limited(self, identifier: str, config: SecurityConfig) -> bool:
        """Check if identifier is rate limited"""
        current_time = time.time()
        
        # Check if currently blocked
        if identifier in self.blocked_until:
            if current_time < self.blocked_until[identifier]:
                return True
            else:
                del self.blocked_until[identifier]
                self.blocked_ips.discard(identifier)
        
        # Get recent requests
        if identifier not in self.requests:
            self.requests[identifier] = []
        
        requests = self.requests[identifier]
        
        # Clean old requests (older than 1 hour)
        cutoff_time = current_time - 3600
        requests[:] = [req_time for req_time in requests if req_time > cutoff_time]
        
        # Check minute limit
        minute_cutoff = current_time - 60
        recent_requests = [req_time for req_time in requests if req_time > minute_cutoff]
        
        if len(recent_requests) >= config.max_requests_per_minute:
            self._block_temporarily(identifier, 300)  # Block for 5 minutes
            return True
        
        # Check hour limit
        if len(requests) >= config.max_requests_per_hour:
            self._block_temporarily(identifier, 3600)  # Block for 1 hour
            return True
        
        # Record this request
        requests.append(current_time)
        return False
    
    def _block_temporarily(self, identifier: str, duration: int):
        """Temporarily block an identifier"""
        self.blocked_ips.add(identifier)
        self.blocked_until[identifier] = time.time() + duration
        logger.warning("IP temporarily blocked for rate limiting", 
                      ip=identifier, 
                      duration=duration)


class URLValidator:
    """Secure URL validation and sanitization"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        
        # Dangerous URL patterns
        self.dangerous_patterns = [
            re.compile(r'javascript:', re.IGNORECASE),
            re.compile(r'data:', re.IGNORECASE),
            re.compile(r'vbscript:', re.IGNORECASE),
            re.compile(r'file:', re.IGNORECASE),
            re.compile(r'ftp:', re.IGNORECASE),
        ]
        
        # Suspicious patterns
        self.suspicious_patterns = [
            re.compile(r'[<>"\']'),  # HTML/JS injection
            re.compile(r'%[0-9a-fA-F]{2}'),  # URL encoding (potential bypass)
            re.compile(r'\\x[0-9a-fA-F]{2}'),  # Hex encoding
            re.compile(r'eval\('),  # JavaScript eval
            re.compile(r'expression\('),  # CSS expression
        ]
    
    def validate_url(self, url: str, allow_relative: bool = False) -> bool:
        """Validate URL for security threats"""
        if not url or not isinstance(url, str):
            return False
        
        # Check length
        if len(url) > 2000:  # RFC 2616 recommends max 2000 chars
            logger.warning("URL too long", url_length=len(url))
            return False
        
        # Check for dangerous schemes
        for pattern in self.dangerous_patterns:
            if pattern.search(url):
                logger.warning("Dangerous URL scheme detected", url=url[:100])
                return False
        
        # Check for suspicious patterns
        for pattern in self.suspicious_patterns:
            if pattern.search(url):
                logger.warning("Suspicious URL pattern detected", url=url[:100])
                return False
        
        try:
            parsed = urlparse(url)
            
            # Validate scheme
            if not allow_relative and not parsed.scheme:
                return False
            
            if parsed.scheme and parsed.scheme not in ['http', 'https']:
                return False
            
            # Validate domain
            if parsed.netloc:
                domain = parsed.netloc.lower()
                
                # Check blocked domains
                if any(blocked in domain for blocked in self.config.blocked_domains):
                    logger.warning("Blocked domain detected", domain=domain)
                    return False
                
                # Check allowed domains (if URL validation is strict)
                if (self.config.validate_urls and 
                    not any(allowed in domain for allowed in self.config.allowed_domains)):
                    logger.warning("Domain not in allowed list", domain=domain)
                    return False
            
            return True
            
        except Exception as e:
            logger.warning("URL parsing error", url=url[:100], error=str(e))
            return False
    
    def sanitize_url(self, url: str) -> str:
        """Sanitize URL by removing dangerous components"""
        if not self.validate_url(url):
            raise SecurityError(
                "Invalid or dangerous URL detected",
                context={'url': url[:100]},
                severity=ErrorSeverity.HIGH
            )
        
        try:
            parsed = urlparse(url)
            
            # Reconstruct URL with only safe components
            safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
            # Add query parameters only if they seem safe
            if parsed.query:
                # Simple query parameter validation
                if not any(char in parsed.query for char in ['<', '>', '"', "'"]):
                    safe_url += f"?{parsed.query}"
            
            return safe_url
            
        except Exception as e:
            raise SecurityError(
                "URL sanitization failed",
                context={'url': url[:100]},
                original_error=e
            )


class ContentSanitizer:
    """Sanitize content to prevent injection attacks"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        
        # HTML/Script injection patterns
        self.html_patterns = [
            re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
            re.compile(r'<iframe[^>]*>.*?</iframe>', re.IGNORECASE | re.DOTALL),
            re.compile(r'<object[^>]*>.*?</object>', re.IGNORECASE | re.DOTALL),
            re.compile(r'<embed[^>]*>', re.IGNORECASE),
            re.compile(r'<link[^>]*>', re.IGNORECASE),
            re.compile(r'<meta[^>]*>', re.IGNORECASE),
            re.compile(r'on\w+\s*=', re.IGNORECASE),  # Event handlers
        ]
        
        # SQL injection patterns
        self.sql_patterns = [
            re.compile(r'(\bUNION\b|\bSELECT\b|\bINSERT\b|\bDELETE\b|\bUPDATE\b|\bDROP\b)', re.IGNORECASE),
            re.compile(r'(\bOR\b|\bAND\b)\s+\d+\s*=\s*\d+', re.IGNORECASE),
            re.compile(r"'.*?(\bOR\b|\bAND\b).*?'", re.IGNORECASE),
        ]
    
    def sanitize_text(self, text: str, max_length: Optional[int] = None) -> str:
        """Sanitize text content"""
        if not text or not isinstance(text, str):
            return ""
        
        # Check length
        max_len = max_length or self.config.max_description_length
        if len(text) > max_len:
            text = text[:max_len]
            logger.warning("Text truncated due to length", original_length=len(text))
        
        # Remove HTML if enabled
        if self.config.sanitize_html:
            for pattern in self.html_patterns:
                text = pattern.sub('', text)
        
        # Check for SQL injection patterns
        for pattern in self.sql_patterns:
            if pattern.search(text):
                logger.warning("Potential SQL injection detected", text_preview=text[:100])
                raise SecurityError(
                    "Potentially malicious content detected",
                    context={'content_preview': text[:100]},
                    severity=ErrorSeverity.HIGH
                )
        
        # Remove or escape dangerous characters
        text = text.replace('<', '&lt;').replace('>', '&gt;')
        text = text.replace('"', '&quot;').replace("'", '&#x27;')
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def validate_file_content(self, content: bytes, filename: str) -> bool:
        """Validate file content for security threats"""
        if len(content) > self.config.max_file_size:
            raise SecurityError(
                f"File too large: {len(content)} bytes",
                context={'filename': filename, 'size': len(content)}
            )
        
        # Check file extension
        _, ext = os.path.splitext(filename.lower())
        if ext not in self.config.allowed_file_extensions:
            raise SecurityError(
                f"File extension not allowed: {ext}",
                context={'filename': filename, 'extension': ext}
            )
        
        # Check for binary content in text files
        if ext in ['.xml', '.json', '.txt']:
            try:
                content.decode('utf-8')
            except UnicodeDecodeError:
                raise SecurityError(
                    "Binary content in text file",
                    context={'filename': filename}
                )
        
        # Check for malicious patterns
        content_str = content.decode('utf-8', errors='ignore')[:10000]  # First 10KB
        
        malicious_patterns = [
            b'<?php',
            b'<script',
            b'javascript:',
            b'eval(',
            b'exec(',
        ]
        
        for pattern in malicious_patterns:
            if pattern in content:
                raise SecurityError(
                    "Malicious pattern detected in file",
                    context={'filename': filename, 'pattern': pattern.decode('utf-8', errors='ignore')}
                )
        
        return True


class CryptoUtils:
    """Cryptographic utilities for secure operations"""
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate cryptographically secure random token"""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def hash_data(data: str, salt: Optional[str] = None) -> str:
        """Hash data securely using SHA-256"""
        if salt is None:
            salt = secrets.token_hex(16)
        
        combined = f"{salt}{data}".encode('utf-8')
        hash_obj = hashlib.sha256(combined)
        return f"{salt}:{hash_obj.hexdigest()}"
    
    @staticmethod
    def verify_hash(data: str, hashed: str) -> bool:
        """Verify hashed data"""
        try:
            salt, hash_value = hashed.split(':', 1)
            expected_hash = CryptoUtils.hash_data(data, salt)
            return hmac.compare_digest(expected_hash, hashed)
        except ValueError:
            return False
    
    @staticmethod
    def create_signature(data: str, secret_key: str) -> str:
        """Create HMAC signature"""
        signature = hmac.new(
            secret_key.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        )
        return signature.hexdigest()
    
    @staticmethod
    def verify_signature(data: str, signature: str, secret_key: str) -> bool:
        """Verify HMAC signature"""
        expected_signature = CryptoUtils.create_signature(data, secret_key)
        return hmac.compare_digest(expected_signature, signature)


class SecurityManager:
    """Main security manager coordinating all security measures"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.request_tracker = RequestTracker()
        self.url_validator = URLValidator(config)
        self.content_sanitizer = ContentSanitizer(config)
        self.crypto = CryptoUtils()
        
        # Security headers for HTTP responses
        self.security_headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Content-Security-Policy': "default-src 'self'; script-src 'none'; object-src 'none';",
        }
    
    def validate_request(self, request_data: Dict[str, Any], client_ip: str = "unknown") -> bool:
        """Validate incoming request for security"""
        
        # Rate limiting
        if self.request_tracker.is_rate_limited(client_ip, self.config):
            raise SecurityError(
                "Rate limit exceeded",
                context={'client_ip': client_ip},
                severity=ErrorSeverity.MEDIUM
            )
        
        # Validate request size
        request_size = len(str(request_data))
        if request_size > self.config.max_content_length:
            raise SecurityError(
                "Request too large",
                context={'size': request_size, 'max_size': self.config.max_content_length}
            )
        
        # Validate URLs in request
        for key, value in request_data.items():
            if isinstance(value, str) and ('url' in key.lower() or 'link' in key.lower()):
                if not self.url_validator.validate_url(value):
                    raise SecurityError(
                        f"Invalid URL in field {key}",
                        context={'field': key, 'url': value[:100]}
                    )
        
        return True
    
    def sanitize_product_data(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize product data for security"""
        sanitized = {}
        
        for key, value in product_data.items():
            if isinstance(value, str):
                if 'url' in key.lower() or 'link' in key.lower():
                    # Sanitize URLs
                    sanitized[key] = self.url_validator.sanitize_url(value)
                else:
                    # Sanitize text content
                    max_length = 5000 if 'description' in key.lower() else 500
                    sanitized[key] = self.content_sanitizer.sanitize_text(value, max_length)
            elif isinstance(value, (list, dict)):
                # Recursively sanitize nested structures
                if isinstance(value, list):
                    sanitized[key] = [
                        self.content_sanitizer.sanitize_text(str(item))[:500] 
                        if isinstance(item, str) else item 
                        for item in value[:10]  # Limit list size
                    ]
                else:
                    sanitized[key] = {
                        k: self.content_sanitizer.sanitize_text(str(v))[:200] 
                        if isinstance(v, str) else v 
                        for k, v in list(value.items())[:20]  # Limit dict size
                    }
            else:
                sanitized[key] = value
        
        return sanitized
    
    def get_security_headers(self) -> Dict[str, str]:
        """Get security headers for HTTP responses"""
        return self.security_headers.copy()
    
    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """Log security-related events"""
        logger.warning(
            "Security event detected",
            event_type=event_type,
            timestamp=datetime.now().isoformat(),
            **details
        )


# Security decorators
def require_valid_input(security_manager: SecurityManager):
    """Decorator to validate input data"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract data from args/kwargs for validation
            for arg in args:
                if isinstance(arg, dict):
                    security_manager.validate_request(arg)
            
            for key, value in kwargs.items():
                if isinstance(value, dict):
                    security_manager.validate_request(value)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def rate_limit(security_manager: SecurityManager, identifier_func=lambda: "default"):
    """Decorator for rate limiting"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            identifier = identifier_func()
            
            if security_manager.request_tracker.is_rate_limited(identifier, security_manager.config):
                raise SecurityError(
                    "Rate limit exceeded",
                    context={'identifier': identifier}
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# Environment variable security
class SecureConfig:
    """Secure configuration management"""
    
    @staticmethod
    def get_env_var(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
        """Securely get environment variable"""
        value = os.getenv(name, default)
        
        if required and value is None:
            raise ConfigurationError(
                f"Required environment variable {name} not found",
                config_key=name
            )
        
        # Don't log sensitive values
        if any(sensitive in name.lower() for sensitive in ['password', 'secret', 'key', 'token']):
            logger.debug("Environment variable loaded", name=name, value="***REDACTED***")
        else:
            logger.debug("Environment variable loaded", name=name, value=value)
        
        return value
    
    @staticmethod
    def validate_config_security(config: Dict[str, Any]) -> bool:
        """Validate configuration for security issues"""
        issues = []
        
        # Check for default/weak values
        weak_patterns = {
            'password': ['password', '123456', 'admin', 'default'],
            'secret': ['secret', 'changeme', 'default'],
            'key': ['key', 'test', 'default'],
        }
        
        for key, value in config.items():
            if not isinstance(value, str):
                continue
                
            key_lower = key.lower()
            value_lower = value.lower()
            
            for pattern_type, weak_values in weak_patterns.items():
                if pattern_type in key_lower:
                    if any(weak in value_lower for weak in weak_values):
                        issues.append(f"Weak {pattern_type} detected in {key}")
        
        if issues:
            logger.error("Security configuration issues detected", issues=issues)
            return False
        
        return True


# Initialize default security manager
default_security_config = SecurityConfig()
security_manager = SecurityManager(default_security_config)