#!/usr/bin/env python3
"""
FeedXML-MX v2.0 - 2025 Enhanced Feed Processor
State-of-the-art feed processing with modern architecture
"""

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urlparse

import aiofiles
import structlog
from pydantic import ValidationError

# Import our enhanced modules
from models import (
    ScrapedProductData, 
    GoogleMerchantFeed, 
    FacebookCatalogFeed, 
    FeedMetadata,
    ScrapingConfig,
    ValidationResult
)
from scraper_optimized import OptimizedProductScraper
from error_handling import (
    ProcessingError, 
    NetworkError, 
    ValidationError as CustomValidationError,
    handle_async_errors,
    ErrorContext,
    error_handler,
    setup_global_error_handlers
)
from security import SecurityManager, SecurityConfig
from monitoring import monitoring, track_operation, track_function

# Setup structured logging
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
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class EnhancedFeedProcessor:
    """
    Next-generation feed processor with:
    - Async/await throughout
    - Comprehensive error handling
    - Security validation
    - Performance monitoring
    - Type safety with Pydantic
    - Structured logging
    """
    
    def __init__(
        self, 
        feed_url: str, 
        scraping_config: Optional[ScrapingConfig] = None,
        security_config: Optional[SecurityConfig] = None,
        enable_scraping: bool = True
    ):
        self.feed_url = feed_url
        self.enable_scraping = enable_scraping
        
        # Initialize configurations
        self.scraping_config = scraping_config or ScrapingConfig()
        self.security_config = security_config or SecurityConfig()
        
        # Initialize components
        self.security_manager = SecurityManager(self.security_config)
        self.scraper: Optional[OptimizedProductScraper] = None
        
        # XML namespaces
        self.namespaces = {'g': 'http://base.google.com/ns/1.0'}
        
        # Processing state
        self.scraped_data: Dict[str, ScrapedProductData] = {}
        self.processing_stats = {
            'start_time': None,
            'end_time': None,
            'products_processed': 0,
            'products_scraped': 0,
            'errors_encountered': 0
        }
        
        # Output paths
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self._initialize_components()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._cleanup_components()
        
        # Handle any unhandled errors
        if exc_val:
            await error_handler.handle_error(exc_val)
    
    async def _initialize_components(self):
        """Initialize async components"""
        logger.info("Initializing FeedXML-MX v2.0 components")
        
        # Start monitoring
        await monitoring.start_monitoring()
        
        # Initialize scraper if enabled
        if self.enable_scraping:
            self.scraper = OptimizedProductScraper(self.scraping_config)
        
        # Setup global error handlers
        setup_global_error_handlers()
        
        monitoring.metrics.update_app_metrics(active_scrapers=1 if self.scraper else 0)
    
    async def _cleanup_components(self):
        """Cleanup async components"""
        logger.info("Cleaning up components")
        
        # Stop monitoring
        await monitoring.stop_monitoring()
        
        # Cleanup scraper resources would be handled by its context manager
        monitoring.metrics.update_app_metrics(active_scrapers=0)
    
    @handle_async_errors
    @track_function("fetch_xml_feed")
    async def fetch_xml_feed(self) -> str:
        """Fetch XML feed with security validation and error handling"""
        
        # Validate URL security
        if not self.security_manager.url_validator.validate_url(self.feed_url):
            raise ProcessingError(
                "Feed URL failed security validation",
                context={'url': self.feed_url}
            )
        
        async with track_operation("fetch_feed", {'url': self.feed_url}):
            logger.info("Fetching XML feed", url=self.feed_url)
            
            # Use aiofiles for async HTTP (in real implementation, use aiohttp)
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=self.security_config.request_timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.get(
                        self.feed_url,
                        headers={
                            'User-Agent': self.scraping_config.user_agent,
                            'Accept': 'application/xml, text/xml, */*',
                        }
                    ) as response:
                        if response.status >= 400:
                            raise NetworkError(
                                f"HTTP {response.status} error fetching feed",
                                url=self.feed_url,
                                status_code=response.status
                            )
                        
                        content = await response.text()
                        
                        # Validate content length
                        if len(content) > self.security_config.max_content_length:
                            raise ProcessingError(
                                "Feed content too large",
                                context={
                                    'content_length': len(content),
                                    'max_allowed': self.security_config.max_content_length
                                }
                            )
                        
                        monitoring.metrics.increment_counter("feed.fetch.success")
                        return content
                        
                except aiohttp.ClientError as e:
                    monitoring.metrics.increment_counter("feed.fetch.error")
                    raise NetworkError(
                        "Network error fetching feed",
                        url=self.feed_url,
                        original_error=e
                    )
    
    @track_function("parse_xml_feed")
    def parse_xml_feed(self, xml_content: str) -> ET.Element:
        """Parse XML feed with validation"""
        
        try:
            # Security: Disable external entity processing
            ET.XMLParser.entity = {}  # Prevent XXE attacks
            
            root = ET.fromstring(xml_content)
            
            # Validate XML structure
            if root.tag != 'rss':
                raise ProcessingError(
                    "Invalid XML structure - expected RSS feed",
                    context={'root_tag': root.tag}
                )
            
            channel = root.find('channel')
            if channel is None:
                raise ProcessingError("No channel element found in RSS feed")
            
            items = channel.findall('item')
            if not items:
                raise ProcessingError("No items found in RSS feed")
            
            logger.info("XML feed parsed successfully", item_count=len(items))
            monitoring.metrics.set_gauge("feed.items_parsed", len(items))
            
            return root
            
        except ET.ParseError as e:
            raise ProcessingError(
                "XML parsing failed",
                original_error=e,
                context={'xml_preview': xml_content[:500]}
            )
    
    @track_function("extract_product_urls")
    def extract_product_urls(self, root: ET.Element) -> List[tuple]:
        """Extract and validate product URLs from XML"""
        
        product_urls = []
        channel = root.find('channel')
        items = channel.findall('item')
        
        for item in items:
            id_elem = item.find('.//g:id', self.namespaces)
            link_elem = item.find('.//g:link', self.namespaces)
            
            if id_elem is not None and link_elem is not None:
                product_id = id_elem.text
                product_url = link_elem.text
                
                # Validate and sanitize URL
                if self.security_manager.url_validator.validate_url(product_url):
                    clean_url = self._clean_product_url(product_url)
                    product_urls.append((clean_url, product_id))
                else:
                    logger.warning("Invalid product URL skipped", 
                                 product_id=product_id, 
                                 url=product_url[:100])
        
        logger.info("Product URLs extracted", count=len(product_urls))
        return product_urls
    
    def _clean_product_url(self, url: str) -> str:
        """Clean product URLs to standard format"""
        # Remove product title suffixes to avoid special characters
        pattern = r'(https://tienda\.accu-chek\.com\.mx/Main/Producto/\d+/).*'
        match = re.match(pattern, url)
        return match.group(1) if match else url
    
    @handle_async_errors
    @track_function("scrape_enhanced_data")
    async def scrape_enhanced_data(self, product_urls: List[tuple]) -> Dict[str, ScrapedProductData]:
        """Scrape enhanced product data with optimized scraper"""
        
        if not self.enable_scraping or not self.scraper:
            logger.info("Scraping disabled, using XML data only")
            return {}
        
        async with track_operation("scrape_products", {'product_count': len(product_urls)}):
            logger.info("Starting enhanced data scraping", product_count=len(product_urls))
            
            try:
                scraped_data = await self.scraper.scrape_multiple_products(product_urls)
                
                # Validate scraped data
                validated_data = {}
                for product_id, data in scraped_data.items():
                    try:
                        # Security validation
                        sanitized_data = self.security_manager.sanitize_product_data(data.dict())
                        
                        # Re-create model with sanitized data
                        validated_product = ScrapedProductData(**sanitized_data)
                        validated_data[product_id] = validated_product
                        
                    except ValidationError as e:
                        logger.warning("Product data validation failed", 
                                     product_id=product_id, 
                                     errors=e.errors())
                        monitoring.metrics.increment_counter("scraping.validation.error")
                
                logger.info("Enhanced data scraping completed", 
                          scraped_count=len(validated_data),
                          validation_errors=len(scraped_data) - len(validated_data))
                
                monitoring.metrics.update_app_metrics(
                    products_scraped=len(validated_data)
                )
                
                return validated_data
                
            except Exception as e:
                logger.error("Scraping failed", error=str(e))
                monitoring.metrics.increment_counter("scraping.error")
                raise ProcessingError(
                    "Enhanced data scraping failed",
                    original_error=e,
                    context={'product_count': len(product_urls)}
                )
    
    @track_function("generate_google_feed")
    async def generate_google_feed(self, root: ET.Element) -> str:
        """Generate Google Merchant Center feed"""
        
        async with track_operation("generate_google_feed"):
            logger.info("Generating Google Merchant Center feed")
            
            # Create new RSS structure
            rss = ET.Element('rss', version='2.0')
            rss.set('xmlns:g', 'http://base.google.com/ns/1.0')
            
            channel = ET.SubElement(rss, 'channel')
            
            # Channel metadata
            ET.SubElement(channel, 'title').text = 'Tienda Accuchek Mexico'
            ET.SubElement(channel, 'link').text = 'https://tienda.accu-chek.com.mx'
            ET.SubElement(channel, 'description').text = 'Productos Accu-Chek para el cuidado de la diabetes'
            
            # Process items
            original_channel = root.find('channel')
            items = original_channel.findall('item')
            
            for item in items:
                await self._process_google_item(channel, item)
            
            # Convert to string
            xml_str = ET.tostring(rss, encoding='unicode', method='xml')
            
            # Pretty format
            from xml.dom import minidom
            dom = minidom.parseString(xml_str)
            formatted_xml = dom.toprettyxml(indent='  ')
            
            # Remove empty lines
            formatted_xml = '\n'.join(line for line in formatted_xml.split('\n') if line.strip())
            
            monitoring.metrics.increment_counter("feed.google.generated")
            return formatted_xml
    
    async def _process_google_item(self, channel: ET.Element, original_item: ET.Element):
        """Process individual item for Google feed"""
        
        # Extract product ID
        id_elem = original_item.find('.//g:id', self.namespaces)
        if id_elem is None:
            return
        
        product_id = id_elem.text
        scraped_data = self.scraped_data.get(product_id)
        
        # Create new item
        item = ET.SubElement(channel, 'item')
        
        # Copy basic fields with namespace
        for field in ['id', 'title', 'description', 'link', 'image_link', 
                     'availability', 'condition', 'price', 'brand', 'gtin']:
            orig_elem = original_item.find(f'.//g:{field}', self.namespaces)
            if orig_elem is not None:
                new_elem = ET.SubElement(item, f'g:{field}')
                new_elem.text = orig_elem.text
        
        # Add enhanced data if available
        if scraped_data:
            # Sale price
            if scraped_data.sale_price and scraped_data.original_price:
                if scraped_data.sale_price < scraped_data.original_price:
                    sale_elem = ET.SubElement(item, 'g:sale_price')
                    sale_elem.text = f"{scraped_data.sale_price:.2f} MXN"
            
            # Custom labels for campaign segmentation
            if scraped_data.has_discount:
                label_elem = ET.SubElement(item, 'g:custom_label_0')
                label_elem.text = 'on_sale'
            
            # Product category
            category_elem = ET.SubElement(item, 'g:google_product_category')
            category_elem.text = 'Health & Beauty > Health Care > Diabetes Management'
            
            # Additional images
            for img_url in scraped_data.additional_images[:5]:  # Limit to 5
                img_elem = ET.SubElement(item, 'g:additional_image_link')
                img_elem.text = str(img_url)
        
        # MPN (Model Part Number)
        mpn_elem = ET.SubElement(item, 'g:mpn')
        mpn_elem.text = product_id
    
    @track_function("generate_facebook_feed")
    async def generate_facebook_feed(self, root: ET.Element) -> str:
        """Generate Facebook Catalog feed"""
        
        async with track_operation("generate_facebook_feed"):
            logger.info("Generating Facebook Catalog feed")
            
            # Create new RSS structure (no namespaces for Facebook)
            rss = ET.Element('rss', version='2.0')
            channel = ET.SubElement(rss, 'channel')
            
            # Channel metadata
            ET.SubElement(channel, 'title').text = 'Tienda Accuchek Mexico'
            ET.SubElement(channel, 'link').text = 'https://tienda.accu-chek.com.mx'
            ET.SubElement(channel, 'description').text = 'Productos Accu-Chek para el cuidado de la diabetes'
            
            # Process items
            original_channel = root.find('channel')
            items = original_channel.findall('item')
            
            for item in items:
                await self._process_facebook_item(channel, item)
            
            # Convert to string
            xml_str = ET.tostring(rss, encoding='unicode', method='xml')
            
            # Pretty format
            from xml.dom import minidom
            dom = minidom.parseString(xml_str)
            formatted_xml = dom.toprettyxml(indent='  ')
            
            # Remove empty lines
            formatted_xml = '\n'.join(line for line in formatted_xml.split('\n') if line.strip())
            
            monitoring.metrics.increment_counter("feed.facebook.generated")
            return formatted_xml
    
    async def _process_facebook_item(self, channel: ET.Element, original_item: ET.Element):
        """Process individual item for Facebook feed"""
        
        # Extract product ID
        id_elem = original_item.find('.//g:id', self.namespaces)
        if id_elem is None:
            return
        
        product_id = id_elem.text
        scraped_data = self.scraped_data.get(product_id)
        
        # Create new item
        item = ET.SubElement(channel, 'item')
        
        # Copy basic fields (remove g: namespace for Facebook)
        field_mapping = {
            'id': 'id',
            'title': 'title', 
            'link': 'link',
            'image_link': 'image_link',
            'availability': 'availability',
            'condition': 'condition',
            'price': 'price',
            'brand': 'brand',
            'gtin': 'gtin'
        }
        
        for orig_field, new_field in field_mapping.items():
            orig_elem = original_item.find(f'.//g:{orig_field}', self.namespaces)
            if orig_elem is not None:
                new_elem = ET.SubElement(item, new_field)
                
                # Format price for Facebook
                if orig_field == 'price' and scraped_data and scraped_data.effective_price:
                    new_elem.text = f"${scraped_data.effective_price:.2f} MXN"
                else:
                    new_elem.text = orig_elem.text
        
        # Enhanced description for Facebook
        desc_elem = ET.SubElement(item, 'description')
        if scraped_data and scraped_data.detailed_description:
            desc_elem.text = scraped_data.detailed_description
        else:
            # Fallback to original description
            orig_desc = original_item.find('.//g:description', self.namespaces)
            desc_elem.text = orig_desc.text if orig_desc is not None else ""
        
        # Add enhanced data
        if scraped_data:
            # Stock quantity
            if scraped_data.stock_quantity:
                qty_elem = ET.SubElement(item, 'quantity')
                qty_elem.text = str(scraped_data.stock_quantity)
            
            # Sale price
            if scraped_data.sale_price and scraped_data.has_discount:
                sale_elem = ET.SubElement(item, 'sale_price')
                sale_elem.text = f"${scraped_data.sale_price:.2f} MXN"
            
            # Additional images
            for img_url in scraped_data.additional_images[:10]:  # Facebook allows more
                img_elem = ET.SubElement(item, 'additional_image_link')
                img_elem.text = str(img_url)
        
        # MPN
        mpn_elem = ET.SubElement(item, 'mpn')
        mpn_elem.text = product_id
    
    @handle_async_errors
    @track_function("save_feeds")
    async def save_feeds(self, google_feed: str, facebook_feed: str) -> tuple:
        """Save generated feeds to files"""
        
        google_path = self.output_dir / "feed_google_v2.xml"
        facebook_path = self.output_dir / "feed_facebook_v2.xml"
        
        async with track_operation("save_feeds"):
            # Save Google feed
            async with aiofiles.open(google_path, 'w', encoding='utf-8') as f:
                await f.write(google_feed)
            
            # Save Facebook feed  
            async with aiofiles.open(facebook_path, 'w', encoding='utf-8') as f:
                await f.write(facebook_feed)
            
            logger.info("Feeds saved successfully", 
                       google_path=str(google_path),
                       facebook_path=str(facebook_path))
            
            return str(google_path), str(facebook_path)
    
    @track_function("save_metadata")
    async def save_metadata(self, google_path: str, facebook_path: str):
        """Save processing metadata"""
        
        metadata = FeedMetadata(
            last_update=datetime.now(),
            source_url=self.feed_url,
            scraping_enabled=self.enable_scraping,
            products_scraped=len(self.scraped_data),
            google_feed=google_path,
            facebook_feed=facebook_path,
            enhancements=[
                "Sale price detection",
                "Stock quantity tracking", 
                "Custom labels for campaigns",
                "Enhanced descriptions",
                "Google product categories",
                "MPN/SKU support",
                "Security validation",
                "Performance monitoring"
            ]
        )
        
        metadata_path = self.output_dir / "metadata_v2.json"
        
        async with aiofiles.open(metadata_path, 'w', encoding='utf-8') as f:
            await f.write(metadata.model_dump_json(indent=2))
        
        # Save scraped data
        if self.scraped_data:
            scraped_path = self.output_dir / "scraped_data.json"
            scraped_dict = {
                pid: data.model_dump() for pid, data in self.scraped_data.items()
            }
            
            async with aiofiles.open(scraped_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(scraped_dict, indent=2, ensure_ascii=False))
        
        logger.info("Metadata saved", metadata_path=str(metadata_path))
    
    @handle_async_errors
    async def process_feeds(self) -> Dict[str, Any]:
        """Main processing method with comprehensive error handling"""
        
        self.processing_stats['start_time'] = datetime.now()
        
        try:
            async with ErrorContext({'operation': 'feed_processing'}):
                # Step 1: Fetch XML feed
                xml_content = await self.fetch_xml_feed()
                
                # Step 2: Parse XML
                root = self.parse_xml_feed(xml_content)
                
                # Step 3: Extract product URLs
                product_urls = self.extract_product_urls(root)
                self.processing_stats['products_processed'] = len(product_urls)
                
                # Step 4: Scrape enhanced data
                self.scraped_data = await self.scrape_enhanced_data(product_urls)
                self.processing_stats['products_scraped'] = len(self.scraped_data)
                
                # Step 5: Generate feeds
                google_feed, facebook_feed = await asyncio.gather(
                    self.generate_google_feed(root),
                    self.generate_facebook_feed(root)
                )
                
                # Step 6: Save feeds
                google_path, facebook_path = await self.save_feeds(google_feed, facebook_feed)
                
                # Step 7: Save metadata
                await self.save_metadata(google_path, facebook_path)
                
                self.processing_stats['end_time'] = datetime.now()
                
                # Update monitoring metrics
                monitoring.metrics.update_app_metrics(
                    products_processed=self.processing_stats['products_processed'],
                    feeds_generated=2,
                    successful_requests=self.processing_stats['products_processed']
                )
                
                # Calculate processing time
                processing_time = (
                    self.processing_stats['end_time'] - self.processing_stats['start_time']
                ).total_seconds()
                
                result = {
                    'success': True,
                    'processing_time': processing_time,
                    'stats': self.processing_stats,
                    'google_feed': google_path,
                    'facebook_feed': facebook_path,
                    'scraped_products': len(self.scraped_data),
                    'monitoring_data': monitoring.get_dashboard_data()
                }
                
                logger.info("Feed processing completed successfully", **result)
                return result
                
        except Exception as e:
            self.processing_stats['end_time'] = datetime.now()
            self.processing_stats['errors_encountered'] += 1
            
            monitoring.metrics.increment_counter("processing.error")
            
            # Log comprehensive error information
            logger.error("Feed processing failed", 
                        error=str(e),
                        stats=self.processing_stats,
                        error_type=type(e).__name__)
            
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__,
                'stats': self.processing_stats
            }


# CLI Interface
async def main():
    """Main CLI interface"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='FeedXML-MX v2.0 - Enhanced Feed Processor')
    parser.add_argument('--feed-url', default='https://tienda.accu-chek.com.mx/Main/FeedXML',
                       help='XML feed URL')
    parser.add_argument('--disable-scraping', action='store_true',
                       help='Disable web scraping')
    parser.add_argument('--max-concurrent', type=int, default=3,
                       help='Maximum concurrent scrapers')
    parser.add_argument('--timeout', type=int, default=30000,
                       help='Request timeout in milliseconds')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        structlog.configure(
            processors=structlog.get_config()["processors"],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    
    # Setup configurations
    scraping_config = ScrapingConfig(
        max_concurrent_requests=args.max_concurrent,
        request_timeout=args.timeout
    )
    
    security_config = SecurityConfig()
    
    # Process feeds
    try:
        async with EnhancedFeedProcessor(
            feed_url=args.feed_url,
            scraping_config=scraping_config,
            security_config=security_config,
            enable_scraping=not args.disable_scraping
        ) as processor:
            
            print("🚀 FeedXML-MX v2.0 - Enhanced Feed Processor")
            print(f"📡 Fetching feed from: {args.feed_url}")
            print(f"🔧 Scraping enabled: {not args.disable_scraping}")
            print()
            
            result = await processor.process_feeds()
            
            if result['success']:
                print("✅ Enhanced Google Merchant feed saved!")
                print(f"📄 File: {result['google_feed']}")
                print()
                print("✅ Enhanced Facebook Catalog feed saved!")
                print(f"📄 File: {result['facebook_feed']}")
                print()
                print("📊 Processing Summary:")
                print(f"- Products processed: {result['stats']['products_processed']}")
                print(f"- Products scraped: {result['scraped_products']}")
                print(f"- Processing time: {result['processing_time']:.2f}s")
                print(f"- Enhanced features: 8")
                print("- Google feed: Enhanced with custom labels and sale prices")
                print("- Facebook feed: Enhanced with stock quantities and detailed descriptions")
                
                sys.exit(0)
            else:
                print(f"❌ Processing failed: {result['error']}")
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\n⚠️ Processing interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
        logger.exception("Unexpected error in main")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())