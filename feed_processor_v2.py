#!/usr/bin/env python3
"""
FeedXML-MX v2.0 - Enhanced Feed Processor with Web Scraping
Combines XML feed data with scraped product information for complete feeds
"""

import xml.etree.ElementTree as ET
import requests
import re
import json
import os
import asyncio
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse
from typing import Dict, List, Optional, Any
import logging

try:
    from product_scraper_enhanced import EnhancedProductScraper as ProductScraper, ScrapedProductData
except ImportError:
    from product_scraper import ProductScraper, ScrapedProductData

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedFeedProcessor:
    """Enhanced feed processor with web scraping capabilities"""
    
    def __init__(self, feed_url: str, enable_scraping: bool = True, max_concurrent_scrapes: int = 3):
        self.feed_url = feed_url
        self.enable_scraping = enable_scraping
        self.max_concurrent_scrapes = max_concurrent_scrapes
        self.namespaces = {
            'g': 'http://base.google.com/ns/1.0'
        }
        self.scraped_data: Dict[str, ScrapedProductData] = {}
        
    def fetch_feed(self):
        """Download the original XML feed"""
        logger.info(f"Fetching XML feed from: {self.feed_url}")
        response = requests.get(self.feed_url)
        response.raise_for_status()
        return response.text
    
    def extract_product_urls(self, root) -> List[tuple]:
        """Extract product URLs and IDs from XML feed"""
        product_urls = []
        channel = root.find('channel')
        items = channel.findall('item')
        
        for item in items:
            # Get product ID and URL
            id_elem = item.find('.//g:id', self.namespaces)
            link_elem = item.find('.//g:link', self.namespaces)
            
            if id_elem is not None and link_elem is not None:
                product_id = id_elem.text
                product_url = link_elem.text
                product_urls.append((product_url, product_id))
        
        logger.info(f"Found {len(product_urls)} products to potentially scrape")
        return product_urls
    
    async def scrape_product_data(self, product_urls: List[tuple]) -> Dict[str, ScrapedProductData]:
        """Scrape additional data from product pages"""
        if not self.enable_scraping:
            logger.info("Scraping disabled, using XML data only")
            return {}
        
        logger.info(f"Starting scraping of {len(product_urls)} products...")
        
        async with ProductScraper(headless=True) as scraper:
            scraped_data = await scraper.scrape_multiple_products(product_urls)
        
        logger.info(f"Successfully scraped {len(scraped_data)} products")
        return scraped_data
    
    def clean_url(self, url):
        """Clean URLs by removing product title suffixes"""
        match = re.match(r'(https://tienda\.accu-chek\.com\.mx/Main/Producto/\d+/).*', url)
        if match:
            return match.group(1)
        return url
    
    def format_price(self, price, platform='both'):
        """Format price according to platform requirements"""
        price_match = re.match(r'(\d+\.?\d*)\s*MXN', price)
        if price_match:
            price_value = float(price_match.group(1))
            if platform == 'facebook':
                # Facebook requires: "9.99 USD" format - no currency symbols, space + ISO code
                return f"{price_value:.2f} MXN"
            else:
                return f"{price_value:.2f} MXN"
        return price
    
    def get_enhanced_product_data(self, item, product_id: str) -> Dict[str, Any]:
        """Get enhanced product data combining XML and scraped data"""
        enhanced_data = {}
        
        # Get scraped data if available
        scraped = self.scraped_data.get(product_id)
        
        if scraped:
            enhanced_data.update({
                'original_price': scraped.original_price,
                'sale_price': scraped.sale_price,
                'discount_percentage': scraped.discount_percentage,
                'promotion_text': scraped.promotion_text,
                'stock_quantity': scraped.stock_quantity,
                'sku': scraped.sku,
                'detailed_description': scraped.detailed_description,
                'features': scraped.features,
                'included_items': scraped.included_items,
                'additional_images': scraped.additional_images
            })
        
        return enhanced_data
    
    def add_custom_labels(self, item, title: str, enhanced_data: Dict) -> None:
        """Add custom labels for campaign segmentation"""
        # Label by product type
        if 'kit' in title.lower() or 'promo pack' in title.lower():
            ET.SubElement(item, 'g:custom_label_0').text = 'kit_producto'
        elif 'tiras reactivas' in title.lower():
            ET.SubElement(item, 'g:custom_label_0').text = 'tiras_reactivas'
        elif 'lancetas' in title.lower():
            ET.SubElement(item, 'g:custom_label_0').text = 'lancetas'
        elif 'glucómetro' in title.lower() or 'medidor' in title.lower():
            ET.SubElement(item, 'g:custom_label_0').text = 'glucometro'
        
        # Label by price range (using sale price if available)
        price = enhanced_data.get('sale_price')
        if price:
            if price > 1000:
                ET.SubElement(item, 'g:custom_label_1').text = 'premium'
            elif price > 500:
                ET.SubElement(item, 'g:custom_label_1').text = 'mid_range'
            else:
                ET.SubElement(item, 'g:custom_label_1').text = 'economico'
        
        # Label promotions
        if enhanced_data.get('discount_percentage'):
            ET.SubElement(item, 'g:custom_label_2').text = 'en_promocion'
        
        # Label by availability
        if enhanced_data.get('stock_quantity'):
            if enhanced_data['stock_quantity'] > 50:
                ET.SubElement(item, 'g:custom_label_3').text = 'alto_stock'
            elif enhanced_data['stock_quantity'] > 10:
                ET.SubElement(item, 'g:custom_label_3').text = 'stock_medio'
            else:
                ET.SubElement(item, 'g:custom_label_3').text = 'stock_bajo'
    
    def process_feed_google(self, root):
        """Process feed for Google Merchant Center with enhancements"""
        google_root = ET.fromstring(ET.tostring(root))
        channel = google_root.find('channel')
        items = channel.findall('item')
        
        # Create list to track items to remove
        items_to_remove = []
        
        for item in items:
            # Get product ID
            id_elem = item.find('.//g:id', self.namespaces)
            if id_elem is None:
                items_to_remove.append(item)
                continue
                
            product_id = id_elem.text
            
            # Check if product should be excluded (failed to scrape or error page)
            if self.enable_scraping and product_id not in self.scraped_data:
                logger.info(f"Excluding product {product_id} from Google feed - failed to scrape or error page")
                items_to_remove.append(item)
                continue
                
            enhanced_data = self.get_enhanced_product_data(item, product_id)
            
            # Clean URL
            link_elem = item.find('.//g:link', self.namespaces)
            if link_elem is not None and link_elem.text:
                link_elem.text = self.clean_url(link_elem.text)
            
            # Enhanced pricing with sale price support
            price_elem = item.find('.//g:price', self.namespaces)
            if price_elem is not None and price_elem.text:
                # Check if product has a real discount
                if enhanced_data.get('original_price') and enhanced_data.get('sale_price') and enhanced_data['original_price'] > enhanced_data['sale_price']:
                    # Product has a discount - use original price as main price
                    price_elem.text = f"{enhanced_data['original_price']:.2f} MXN"
                    # Add sale price element
                    sale_price_elem = ET.SubElement(item, 'g:sale_price')
                    sale_price_elem.text = f"{enhanced_data['sale_price']:.2f} MXN"
                    # Add sale price effective date (today only)
                    sale_date_elem = ET.SubElement(item, 'g:sale_price_effective_date')
                    today = datetime.now()
                    # Using simplified format without timezone (Google will use Mexico timezone)
                    sale_date_elem.text = f"{today.strftime('%Y-%m-%d')}/{today.strftime('%Y-%m-%d')}"
                elif enhanced_data.get('sale_price'):
                    # Product has no discount - use sale price as the regular price
                    price_elem.text = f"{enhanced_data['sale_price']:.2f} MXN"
                else:
                    # No enhanced pricing - format existing price from XML
                    price_elem.text = self.format_price(price_elem.text, 'google')
            
            # Add enhanced availability with stock quantity
            availability_elem = item.find('.//g:availability', self.namespaces)
            if availability_elem is not None and enhanced_data.get('stock_quantity') is not None:
                if enhanced_data['stock_quantity'] > 0:
                    availability_elem.text = 'in stock'
                else:
                    availability_elem.text = 'out of stock'
            
            # Add MPn (SKU) if available
            if enhanced_data.get('sku'):
                mpn_elem = ET.SubElement(item, 'g:mpn')
                mpn_elem.text = enhanced_data['sku']
            
            # Add Google product category for diabetes care products
            google_category_elem = ET.SubElement(item, 'g:google_product_category')
            google_category_elem.text = '491'  # Health & Beauty > Health Care > Diabetes Care
            
            # Add custom labels for campaign optimization
            title_elem = item.find('.//g:title', self.namespaces)
            if title_elem is not None:
                self.add_custom_labels(item, title_elem.text, enhanced_data)
            
            # Enhanced description
            desc_elem = item.find('.//g:description', self.namespaces)
            if desc_elem is not None and enhanced_data.get('detailed_description'):
                # Use detailed description but keep it concise for Google
                detailed_desc = enhanced_data['detailed_description'][:500]
                if not detailed_desc.endswith('.'):
                    detailed_desc += '.'
                desc_elem.text = detailed_desc
            
            # Add additional images if available (Google supports up to 10)
            if enhanced_data.get('additional_images'):
                main_image = item.find('.//g:image_link', self.namespaces)
                main_image_url = main_image.text if main_image is not None else ""
                
                for img_url in enhanced_data['additional_images'][:10]:
                    # Don't duplicate the main image
                    if img_url != main_image_url:
                        img_elem = ET.SubElement(item, 'g:additional_image_link')
                        img_elem.text = img_url
        
        # Remove items that failed validation or scraping
        for item in items_to_remove:
            channel.remove(item)
        
        logger.info(f"Google feed: excluded {len(items_to_remove)} invalid products, included {len(items) - len(items_to_remove)} valid products")
        
        return google_root
    
    def process_feed_facebook(self, root):
        """Process feed for Facebook Catalog with enhancements"""
        fb_root = ET.Element('rss', version='2.0')
        fb_channel = ET.SubElement(fb_root, 'channel')
        
        # Channel information
        channel = root.find('channel')
        ET.SubElement(fb_channel, 'title').text = 'Tienda Accuchek Mexico'
        ET.SubElement(fb_channel, 'link').text = 'https://tienda.accu-chek.com.mx'
        ET.SubElement(fb_channel, 'description').text = 'Productos Accu-Chek para el cuidado de la diabetes'
        
        # Process items
        items = channel.findall('item')
        valid_products = 0
        excluded_products = 0
        
        for item in items:
            # Get product ID
            id_elem = item.find('.//g:id', self.namespaces)
            if id_elem is None:
                excluded_products += 1
                continue
                
            product_id = id_elem.text
            
            # Check if product should be excluded (failed to scrape or error page)
            if self.enable_scraping and product_id not in self.scraped_data:
                logger.info(f"Excluding product {product_id} from Facebook feed - failed to scrape or error page")
                excluded_products += 1
                continue
            
            # Create Facebook item only for valid products
            fb_item = ET.SubElement(fb_channel, 'item')
            valid_products += 1
                
            enhanced_data = self.get_enhanced_product_data(item, product_id)
            
            # Required fields for Facebook
            ET.SubElement(fb_item, 'id').text = product_id
            
            # Title
            title_elem = item.find('.//g:title', self.namespaces)
            if title_elem is not None:
                ET.SubElement(fb_item, 'title').text = title_elem.text
            
            # Enhanced description for Facebook
            desc_text = ""
            if enhanced_data.get('detailed_description'):
                desc_text = enhanced_data['detailed_description']
            else:
                title_elem = item.find('.//g:title', self.namespaces)
                if title_elem is not None:
                    desc_text = title_elem.text
            
            if not desc_text.endswith('.'):
                desc_text += '.'
            ET.SubElement(fb_item, 'description').text = desc_text
            
            # URL
            link_elem = item.find('.//g:link', self.namespaces)
            if link_elem is not None:
                ET.SubElement(fb_item, 'link').text = self.clean_url(link_elem.text)
            
            # Image
            image_elem = item.find('.//g:image_link', self.namespaces)
            if image_elem is not None:
                ET.SubElement(fb_item, 'image_link').text = image_elem.text
            
            # Enhanced availability with stock (Facebook standard values - required field)
            avail_elem = item.find('.//g:availability', self.namespaces)
            if avail_elem is not None:
                if enhanced_data.get('stock_quantity') is not None:
                    if enhanced_data['stock_quantity'] > 0:
                        ET.SubElement(fb_item, 'availability').text = 'in stock'
                        # Add quantity for Facebook checkout
                        ET.SubElement(fb_item, 'quantity').text = str(enhanced_data['stock_quantity'])
                    else:
                        ET.SubElement(fb_item, 'availability').text = 'out of stock'
                else:
                    # Map common availability values to Facebook standard
                    original_availability = avail_elem.text.lower()
                    if original_availability in ['in stock', 'available']:
                        ET.SubElement(fb_item, 'availability').text = 'in stock'
                    elif original_availability in ['out of stock', 'unavailable']:
                        ET.SubElement(fb_item, 'availability').text = 'out of stock'
                    else:
                        ET.SubElement(fb_item, 'availability').text = 'in stock'  # Default
            else:
                # Ensure availability is always present (required field)
                ET.SubElement(fb_item, 'availability').text = 'in stock'  # Default
            
            # Condition (Facebook requires specific values)
            cond_elem = item.find('.//g:condition', self.namespaces)
            if cond_elem is not None:
                # Map to Facebook standard values: new, refurbished, used
                original_condition = cond_elem.text.lower()
                if 'new' in original_condition or 'nuevo' in original_condition:
                    ET.SubElement(fb_item, 'condition').text = 'new'
                elif 'refurbished' in original_condition or 'reacondicionado' in original_condition:
                    ET.SubElement(fb_item, 'condition').text = 'refurbished'
                elif 'used' in original_condition or 'usado' in original_condition:
                    ET.SubElement(fb_item, 'condition').text = 'used'
                else:
                    ET.SubElement(fb_item, 'condition').text = 'new'  # Default for medical products
            else:
                ET.SubElement(fb_item, 'condition').text = 'new'  # Default for medical products
            
            # Enhanced pricing following Facebook specifications
            if enhanced_data.get('original_price') and enhanced_data.get('sale_price') and enhanced_data['original_price'] > enhanced_data['sale_price']:
                # Product has a discount - price is the regular price, sale_price is the discounted price
                ET.SubElement(fb_item, 'price').text = f"{enhanced_data['original_price']:.2f} MXN"
                ET.SubElement(fb_item, 'sale_price').text = f"{enhanced_data['sale_price']:.2f} MXN"
            elif enhanced_data.get('sale_price'):
                # Product has no discount - use sale price as main price only
                ET.SubElement(fb_item, 'price').text = f"{enhanced_data['sale_price']:.2f} MXN"
            else:
                # No enhanced pricing - use original XML price
                price_elem = item.find('.//g:price', self.namespaces)
                if price_elem is not None:
                    ET.SubElement(fb_item, 'price').text = self.format_price(price_elem.text, 'facebook')
            
            # Brand (required field)
            brand_elem = item.find('.//g:brand', self.namespaces)
            if brand_elem is not None and brand_elem.text:
                ET.SubElement(fb_item, 'brand').text = brand_elem.text
            else:
                ET.SubElement(fb_item, 'brand').text = 'Accu-Chek'  # Default brand
            
            # GTIN
            gtin_elem = item.find('.//g:gtin', self.namespaces)
            if gtin_elem is not None:
                ET.SubElement(fb_item, 'gtin').text = gtin_elem.text
            
            # Add MPN if available from scraping
            if enhanced_data.get('sku'):
                ET.SubElement(fb_item, 'mpn').text = enhanced_data['sku']
            
            # Add additional images if available (Facebook supports up to 10)
            if enhanced_data.get('additional_images'):
                main_image_url = image_elem.text if image_elem is not None else ""
                
                for img_url in enhanced_data['additional_images'][:10]:
                    # Don't duplicate the main image
                    if img_url != main_image_url:
                        ET.SubElement(fb_item, 'additional_image_link').text = img_url
        
        logger.info(f"Facebook feed: excluded {excluded_products} invalid products, included {valid_products} valid products")
        
        return fb_root
    
    async def process_feeds(self):
        """Main processing function with scraping integration"""
        logger.info("Starting enhanced feed processing...")
        
        # Get original XML feed
        xml_content = self.fetch_feed()
        root = ET.fromstring(xml_content)
        
        # Extract product URLs for scraping
        product_urls = self.extract_product_urls(root)
        
        # Scrape additional product data
        if self.enable_scraping:
            self.scraped_data = await self.scrape_product_data(product_urls)
        
        # Process feeds with enhanced data
        logger.info("Processing Google Merchant feed...")
        google_root = self.process_feed_google(root)
        
        logger.info("Processing Facebook Catalog feed...")
        facebook_root = self.process_feed_facebook(root)
        
        return google_root, facebook_root
    
    def save_feed(self, root, output_file, platform='google'):
        """Save processed feed to file"""
        if platform == 'google':
            ET.register_namespace('g', 'http://base.google.com/ns/1.0')
        
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        
        # Format the file
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if '<?xml' not in content:
            formatted_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + content
        else:
            formatted_content = content
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
        
        return output_file
    
    def save_scraped_data(self, output_file='output/scraped_data.json'):
        """Save scraped data for analysis and caching"""
        scraped_dict = {}
        for product_id, data in self.scraped_data.items():
            scraped_dict[product_id] = {
                'product_id': data.product_id,
                'sku': data.sku,
                'original_price': data.original_price,
                'sale_price': data.sale_price,
                'discount_percentage': data.discount_percentage,
                'promotion_text': data.promotion_text,
                'stock_quantity': data.stock_quantity,
                'last_updated': data.last_updated
            }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(scraped_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Scraped data saved to {output_file}")


async def main():
    """Main execution function"""
    feed_url = 'https://tienda.accu-chek.com.mx/Main/FeedXML'
    
    # Check for environment variable to control scraping
    enable_scraping = os.getenv('ENABLE_SCRAPING', 'true').lower() == 'true'
    
    print("🚀 FeedXML-MX v2.0 - Enhanced Feed Processor")
    print(f"📡 Fetching feed from: {feed_url}")
    print(f"🔧 Scraping enabled: {enable_scraping}")
    
    # Create processor with configurable scraping
    processor = EnhancedFeedProcessor(
        feed_url=feed_url,
        enable_scraping=enable_scraping,
        max_concurrent_scrapes=3
    )
    
    try:
        # Process feeds with enhanced data
        google_root, facebook_root = await processor.process_feeds()
        
        # Create output directory
        os.makedirs('output', exist_ok=True)
        
        # Save enhanced feeds
        google_file = processor.save_feed(google_root, 'output/feed_google_v2.xml', 'google')
        print(f"\n✅ Enhanced Google Merchant feed saved!")
        print(f"📄 File: {google_file}")
        
        facebook_file = processor.save_feed(facebook_root, 'output/feed_facebook_v2.xml', 'facebook')
        print(f"\n✅ Enhanced Facebook Catalog feed saved!")
        print(f"📄 File: {facebook_file}")
        
        # Save scraped data
        processor.save_scraped_data()
        
        # Save metadata
        metadata = {
            'version': '2.0',
            'last_update': datetime.now().isoformat(),
            'source_url': feed_url,
            'scraping_enabled': processor.enable_scraping,
            'products_scraped': len(processor.scraped_data),
            'google_feed': google_file,
            'facebook_feed': facebook_file,
            'enhancements': [
                'Sale price detection',
                'Stock quantity tracking',
                'Custom labels for campaigns',
                'Enhanced descriptions',
                'Google product categories',
                'MPN/SKU support'
            ]
        }
        
        with open('output/metadata_v2.json', 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        print(f"\n📊 Processing Summary:")
        print(f"- Products scraped: {len(processor.scraped_data)}")
        print(f"- Enhanced features: {len(metadata['enhancements'])}")
        print(f"- Google feed: Enhanced with custom labels and sale prices")
        print(f"- Facebook feed: Enhanced with stock quantities and detailed descriptions")
        
    except Exception as e:
        logger.error(f"Error processing feeds: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())