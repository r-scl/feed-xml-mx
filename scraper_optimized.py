#!/usr/bin/env python3
"""
Optimized Product Scraper for 2025
High-performance async scraping with advanced concurrency control
"""

import asyncio
import aiofiles
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Union, AsyncGenerator
from urllib.parse import urljoin

import structlog
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from bs4 import BeautifulSoup
from asyncio_throttle import Throttler

from models import ScrapedProductData, ScrapingConfig
from error_handling import (
    ScrapingError, 
    NetworkError, 
    handle_async_errors, 
    ErrorContext,
    ErrorSeverity
)


logger = structlog.get_logger(__name__)


@dataclass
class ScrapingStats:
    """Statistics for scraping performance monitoring"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_time: float = 0.0
    average_response_time: float = 0.0
    requests_per_second: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    
    def calculate_metrics(self):
        """Calculate derived metrics"""
        if self.total_requests > 0:
            self.average_response_time = self.total_time / self.total_requests
            if self.total_time > 0:
                self.requests_per_second = self.total_requests / self.total_time


class CacheEntry:
    """Cache entry with TTL support"""
    
    def __init__(self, data: ScrapedProductData, ttl_seconds: int = 3600):
        self.data = data
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)
    
    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


class OptimizedProductScraper:
    """
    High-performance product scraper with advanced features:
    - Connection pooling and reuse
    - Intelligent rate limiting
    - Memory-efficient caching
    - Concurrent request management
    - Error recovery and retries
    """
    
    def __init__(self, config: ScrapingConfig):
        self.config = config
        self.stats = ScrapingStats()
        self.cache: Dict[str, CacheEntry] = {}
        self.failed_urls: Set[str] = set()
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.throttler = Throttler(rate_limit=config.max_concurrent_requests, period=1.0)
        
        # Performance optimizations
        self._semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self._session_timeout = aiofiles.os.getenv('SESSION_TIMEOUT', 300)  # 5 minutes
        
    @asynccontextmanager
    async def _browser_session(self) -> AsyncGenerator[Browser, None]:
        """Context manager for browser session with connection pooling"""
        if not self.browser:
            playwright = await async_playwright().start()
            try:
                # Optimized browser launch for performance
                self.browser = await playwright.chromium.launch(
                    headless=self.config.headless_browser,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-extensions',
                        '--disable-plugins',
                        '--disable-images',  # Disable images for faster loading
                        '--disable-javascript',  # We'll enable selectively
                        '--disable-web-security',
                        '--disable-gpu',
                        '--memory-pressure-off',
                        '--max_old_space_size=4096',
                    ],
                    # Performance settings
                    slow_mo=0,
                    timeout=self.config.request_timeout,
                )
                
                # Create persistent context for connection reuse
                self.context = await self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent=self.config.user_agent,
                    extra_http_headers={
                        'Accept-Language': 'es-MX,es;q=0.9,en;q=0.8',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Cache-Control': 'max-age=3600',
                    },
                    # Performance optimizations
                    ignore_https_errors=True,
                    java_script_enabled=True,  # Enable JS only when needed
                )
                
                yield self.browser
                
            finally:
                if self.context:
                    await self.context.close()
                if self.browser:
                    await self.browser.close()
                await playwright.stop()
        else:
            yield self.browser
    
    async def _create_optimized_page(self) -> Page:
        """Create an optimized page instance"""
        if not self.context:
            raise ScrapingError("Browser context not initialized")
        
        page = await self.context.new_page()
        
        # Block unnecessary resources for performance
        await page.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,css}", 
                        lambda route: route.abort())
        
        # Block tracking and analytics
        await page.route("**/google-analytics.com/**", lambda route: route.abort())
        await page.route("**/googletagmanager.com/**", lambda route: route.abort())
        await page.route("**/facebook.com/**", lambda route: route.abort())
        
        # Set optimized timeout
        page.set_default_timeout(self.config.request_timeout)
        
        return page
    
    @handle_async_errors
    async def scrape_product_page(self, product_url: str, product_id: str) -> Optional[ScrapedProductData]:
        """Scrape single product with optimizations and caching"""
        
        # Check cache first
        cache_key = f"{product_id}:{product_url}"
        if cache_key in self.cache and not self.cache[cache_key].is_expired:
            self.stats.cache_hits += 1
            logger.debug("Cache hit", product_id=product_id)
            return self.cache[cache_key].data
        
        self.stats.cache_misses += 1
        
        # Check if URL previously failed
        if product_url in self.failed_urls:
            logger.warning("Skipping previously failed URL", url=product_url)
            return None
        
        async with self._semaphore:  # Control concurrency
            async with self.throttler:  # Rate limiting
                return await self._scrape_with_retries(product_url, product_id, cache_key)
    
    async def _scrape_with_retries(self, product_url: str, product_id: str, cache_key: str) -> Optional[ScrapedProductData]:
        """Scrape with retry logic and error handling"""
        
        start_time = time.time()
        last_error = None
        
        for attempt in range(self.config.retry_attempts + 1):
            try:
                async with ErrorContext({'product_id': product_id, 'url': product_url, 'attempt': attempt}):
                    result = await self._perform_scrape(product_url, product_id)
                    
                    if result:
                        # Cache successful result
                        self.cache[cache_key] = CacheEntry(result, ttl_seconds=3600)
                        
                        # Update stats
                        self.stats.successful_requests += 1
                        self.stats.total_time += time.time() - start_time
                        
                        logger.info("Successfully scraped product", 
                                  product_id=product_id, 
                                  attempt=attempt + 1,
                                  response_time=time.time() - start_time)
                        return result
                
            except Exception as e:
                last_error = e
                
                if attempt < self.config.retry_attempts:
                    delay = self.config.delay_between_requests * (2 ** attempt)  # Exponential backoff
                    logger.warning("Retrying after error", 
                                 product_id=product_id, 
                                 attempt=attempt + 1,
                                 delay=delay,
                                 error=str(e))
                    await asyncio.sleep(delay)
                else:
                    logger.error("Max retries exceeded", 
                               product_id=product_id, 
                               error=str(e))
        
        # Mark as failed
        self.failed_urls.add(product_url)
        self.stats.failed_requests += 1
        
        if last_error:
            raise ScrapingError(
                f"Failed to scrape after {self.config.retry_attempts} retries",
                product_id=product_id,
                url=product_url,
                original_error=last_error,
                severity=ErrorSeverity.MEDIUM
            )
        
        return None
    
    async def _perform_scrape(self, product_url: str, product_id: str) -> Optional[ScrapedProductData]:
        """Perform the actual scraping operation"""
        
        async with self._browser_session():
            page = await self._create_optimized_page()
            
            try:
                # Navigate with timeout
                response = await page.goto(
                    product_url, 
                    wait_until='domcontentloaded',  # Don't wait for all resources
                    timeout=self.config.request_timeout
                )
                
                if not response or response.status >= 400:
                    raise NetworkError(
                        f"HTTP {response.status if response else 'unknown'} error",
                        url=product_url,
                        status_code=response.status if response else None
                    )
                
                # Check for 404 in page content
                page_title = await page.title()
                if any(error_text in page_title.lower() for error_text in 
                      ['404', 'not found', 'página no encontrada', 'error']):
                    raise ScrapingError(
                        "Product page not found (404)",
                        product_id=product_id,
                        url=product_url
                    )
                
                # Wait for critical content to load
                try:
                    await page.wait_for_selector('script:has-text("dataProd")', timeout=5000)
                except:
                    logger.warning("dataProd script not found, continuing", product_id=product_id)
                
                # Get page content
                content = await page.content()
                soup = BeautifulSoup(content, 'lxml')  # lxml is faster than html.parser
                
                # Extract data using optimized methods
                return await self._extract_product_data(soup, product_id, product_url)
                
            finally:
                await page.close()
    
    async def _extract_product_data(self, soup: BeautifulSoup, product_id: str, product_url: str) -> ScrapedProductData:
        """Extract product data with performance optimizations"""
        
        # Use asyncio.gather for parallel extraction
        tasks = [
            self._extract_price_info_async(soup),
            self._extract_stock_info_async(soup),
            self._extract_description_async(soup),
            self._extract_images_async(soup),
        ]
        
        price_info, stock_quantity, description, images = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions from parallel extraction
        if isinstance(price_info, Exception):
            logger.warning("Price extraction failed", error=str(price_info))
            price_info = {}
        if isinstance(stock_quantity, Exception):
            logger.warning("Stock extraction failed", error=str(stock_quantity))
            stock_quantity = None
        if isinstance(description, Exception):
            logger.warning("Description extraction failed", error=str(description))
            description = None
        if isinstance(images, Exception):
            logger.warning("Images extraction failed", error=str(images))
            images = []
        
        # Create validated model
        return ScrapedProductData(
            product_id=product_id,
            sku=product_id,
            original_price=price_info.get('original_price'),
            sale_price=price_info.get('sale_price'),
            discount_percentage=price_info.get('discount_percentage'),
            promotion_text=price_info.get('promotion_text'),
            stock_quantity=stock_quantity,
            detailed_description=description,
            additional_images=images[:10] if images else [],  # Limit images
        )
    
    async def _extract_price_info_async(self, soup: BeautifulSoup) -> Dict[str, Optional[Union[float, int, str]]]:
        """Async price extraction with optimization"""
        # This could be CPU-bound, so we might want to run in executor
        # For now, keeping it simple but could be optimized further
        return await asyncio.get_event_loop().run_in_executor(
            None, self._extract_price_info_sync, soup
        )
    
    def _extract_price_info_sync(self, soup: BeautifulSoup) -> Dict[str, Optional[Union[float, int, str]]]:
        """Optimized synchronous price extraction"""
        price_info = {
            'original_price': None,
            'sale_price': None,
            'discount_percentage': None,
            'promotion_text': None
        }
        
        try:
            # Get page text once
            page_text = soup.get_text()
            
            # Optimized price pattern matching
            price_pattern = re.compile(r'\$?([0-9,]+\.?[0-9]*)\s*MXN?')
            price_matches = price_pattern.findall(page_text.replace(',', ''))
            
            # Process prices
            valid_prices = []
            for price_str in price_matches:
                try:
                    price_val = float(price_str)
                    if 100 <= price_val <= 10000:  # Reasonable range
                        valid_prices.append(price_val)
                except ValueError:
                    continue
            
            # Remove duplicates and sort
            unique_prices = sorted(list(set(valid_prices)), reverse=True)
            
            if len(unique_prices) >= 2:
                price_info['original_price'] = unique_prices[0]
                price_info['sale_price'] = unique_prices[1]
                
                # Calculate discount
                if price_info['original_price'] and price_info['sale_price']:
                    discount = ((price_info['original_price'] - price_info['sale_price']) / price_info['original_price']) * 100
                    price_info['discount_percentage'] = round(discount)
                    
            elif len(unique_prices) == 1:
                price_info['sale_price'] = unique_prices[0]
            
        except Exception as e:
            logger.warning("Price extraction error", error=str(e))
        
        return price_info
    
    async def _extract_stock_info_async(self, soup: BeautifulSoup) -> Optional[int]:
        """Async stock extraction"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._extract_stock_info_sync, soup
        )
    
    def _extract_stock_info_sync(self, soup: BeautifulSoup) -> Optional[int]:
        """Optimized stock extraction"""
        try:
            # Check quantity input first (fastest)
            quantity_input = soup.find('input', class_='js-quantity')
            if quantity_input and quantity_input.get('max'):
                return int(quantity_input.get('max'))
            
            # Search in text content
            page_text = soup.get_text()
            
            # Optimized stock patterns
            stock_patterns = [
                re.compile(r'disponibles:\s*(\d+)', re.IGNORECASE),
                re.compile(r'(\d+)\s*disponibles?', re.IGNORECASE),
                re.compile(r'stock:\s*(\d+)', re.IGNORECASE),
            ]
            
            for pattern in stock_patterns:
                match = pattern.search(page_text)
                if match:
                    stock_num = int(match.group(1))
                    if 1 <= stock_num <= 1000:
                        return stock_num
            
        except Exception as e:
            logger.warning("Stock extraction error", error=str(e))
        
        return None
    
    async def _extract_description_async(self, soup: BeautifulSoup) -> Optional[str]:
        """Async description extraction"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._extract_description_sync, soup
        )
    
    def _extract_description_sync(self, soup: BeautifulSoup) -> Optional[str]:
        """Optimized description extraction"""
        try:
            # Try dataProd first (fastest path)
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'let dataProd' in script.string:
                    desc_match = re.search(r'"descripcionLarga"\s*:\s*"([^"]*)"', script.string)
                    if desc_match:
                        desc_text = desc_match.group(1)
                        desc_text = desc_text.replace('\\"', '"').replace('\\n', ' ').replace('\\r', '')
                        if len(desc_text.strip()) > 10:
                            return desc_text.strip()
            
            # Fallback to #description div
            desc_div = soup.find('div', id='description')
            if desc_div:
                text = desc_div.get_text(strip=True)
                if len(text) > 10:
                    return text
            
        except Exception as e:
            logger.warning("Description extraction error", error=str(e))
        
        return None
    
    async def _extract_images_async(self, soup: BeautifulSoup) -> List[str]:
        """Async image extraction"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._extract_images_sync, soup
        )
    
    def _extract_images_sync(self, soup: BeautifulSoup) -> List[str]:
        """Optimized image extraction"""
        try:
            images = []
            seen_images = set()
            
            # Find product images efficiently
            img_elements = soup.find_all('img', src=re.compile(r'(product|ecommerce|cdn\.gdar|accu-chek)', re.I))
            
            for img in img_elements[:20]:  # Limit processing
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if not src or src in seen_images:
                    continue
                
                # Convert to absolute URL if needed
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin('https://tienda.accu-chek.com.mx', src)
                
                if src.startswith('http') and 'thumb' not in src.lower():
                    images.append(src)
                    seen_images.add(src)
                    
                    if len(images) >= 10:  # Limit total images
                        break
            
            return images
            
        except Exception as e:
            logger.warning("Image extraction error", error=str(e))
            return []
    
    async def scrape_multiple_products(self, product_urls: List[tuple]) -> Dict[str, ScrapedProductData]:
        """Scrape multiple products with optimized concurrency"""
        
        logger.info("Starting optimized batch scraping", total_products=len(product_urls))
        start_time = time.time()
        
        # Reset stats
        self.stats = ScrapingStats()
        self.stats.total_requests = len(product_urls)
        
        # Create tasks for all products
        tasks = [
            self.scrape_product_page(url, product_id) 
            for url, product_id in product_urls
        ]
        
        # Execute with progress tracking
        results = {}
        completed = 0
        
        # Process in batches to avoid overwhelming the system
        batch_size = min(self.config.max_concurrent_requests * 2, 20)
        
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            
            for j, result in enumerate(batch_results):
                product_id = product_urls[i + j][1]
                
                if isinstance(result, Exception):
                    logger.error("Product scraping failed", 
                               product_id=product_id, 
                               error=str(result))
                elif result:
                    results[product_id] = result
                
                completed += 1
                
                # Log progress every 10 products
                if completed % 10 == 0:
                    progress = (completed / len(product_urls)) * 100
                    logger.info("Scraping progress", 
                              completed=completed, 
                              total=len(product_urls),
                              progress=f"{progress:.1f}%")
        
        # Calculate final stats
        total_time = time.time() - start_time
        self.stats.total_time = total_time
        self.stats.calculate_metrics()
        
        logger.info("Batch scraping completed", 
                   successful=len(results),
                   failed=self.stats.failed_requests,
                   total_time=f"{total_time:.2f}s",
                   avg_response_time=f"{self.stats.average_response_time:.2f}s",
                   requests_per_second=f"{self.stats.requests_per_second:.2f}",
                   cache_hits=self.stats.cache_hits)
        
        return results
    
    def get_performance_stats(self) -> Dict[str, Union[int, float]]:
        """Get current performance statistics"""
        return {
            'total_requests': self.stats.total_requests,
            'successful_requests': self.stats.successful_requests,
            'failed_requests': self.stats.failed_requests,
            'success_rate': (self.stats.successful_requests / max(self.stats.total_requests, 1)) * 100,
            'average_response_time': self.stats.average_response_time,
            'requests_per_second': self.stats.requests_per_second,
            'cache_hit_rate': (self.stats.cache_hits / max(self.stats.cache_hits + self.stats.cache_misses, 1)) * 100,
            'total_cache_entries': len(self.cache),
            'failed_urls_count': len(self.failed_urls),
        }
    
    def clear_cache(self):
        """Clear expired cache entries"""
        expired_keys = [
            key for key, entry in self.cache.items() 
            if entry.is_expired
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        logger.info("Cache cleanup completed", 
                   expired_entries=len(expired_keys),
                   remaining_entries=len(self.cache))


# Performance monitoring decorator
def monitor_performance(func):
    """Decorator to monitor function performance"""
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            logger.debug("Function completed", 
                        function=func.__name__,
                        duration=f"{duration:.3f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error("Function failed", 
                        function=func.__name__,
                        duration=f"{duration:.3f}s",
                        error=str(e))
            raise
    return wrapper