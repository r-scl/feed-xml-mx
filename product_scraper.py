#!/usr/bin/env python3
"""
Web Scraper for Accu-Chek Mexico Product Data
Extracts detailed product information from individual product pages
"""

import asyncio
import re
import json
import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, asdict
from datetime import datetime

import requests
from playwright.async_api import async_playwright, Browser, Page
from bs4 import BeautifulSoup
from pydantic import BaseModel, ValidationError


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ScrapedProductData:
    """Data structure for scraped product information"""
    product_id: str
    sku: Optional[str] = None
    original_price: Optional[float] = None
    sale_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    promotion_text: Optional[str] = None
    stock_quantity: Optional[int] = None
    detailed_description: Optional[str] = None
    features: List[str] = None
    included_items: List[str] = None
    specifications: Dict[str, str] = None
    additional_images: List[str] = None
    last_updated: Optional[str] = None
    
    def __post_init__(self):
        if self.features is None:
            self.features = []
        if self.included_items is None:
            self.included_items = []
        if self.specifications is None:
            self.specifications = {}
        if self.additional_images is None:
            self.additional_images = []
        if self.last_updated is None:
            self.last_updated = datetime.now().isoformat()


class ProductScraper:
    """Web scraper for Accu-Chek Mexico product pages"""
    
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.base_url = "https://tienda.accu-chek.com.mx"
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.browser:
            await self.browser.close()
        await self.playwright.stop()
    
    async def create_page(self) -> Page:
        """Create a new browser page with optimized settings"""
        if not self.browser:
            raise RuntimeError("Browser not initialized")
            
        page = await self.browser.new_page()
        
        # Set viewport and user agent
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await page.set_extra_http_headers({
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.8"
        })
        
        # Block unnecessary resources for faster loading (but keep images for now to debug)
        # await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", 
        #                 lambda route: route.abort())
        
        return page
    
    def extract_price_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract price information from product page"""
        price_info = {
            'original_price': None,
            'sale_price': None,
            'discount_percentage': None,
            'promotion_text': None
        }
        
        try:
            # Extract all price values from the entire page
            page_text = soup.get_text()
            
            # Find all price patterns in the page
            price_matches = re.findall(r'\$?([\d,]+\.?\d*)\s*MXN?', page_text.replace(',', ''))
            
            # Convert to floats and filter out invalid prices
            valid_prices = []
            for price_str in price_matches:
                try:
                    price_val = float(price_str)
                    if 100 <= price_val <= 10000:  # Reasonable price range for medical products
                        valid_prices.append(price_val)
                except ValueError:
                    continue
            
            # Remove duplicates and sort
            unique_prices = sorted(list(set(valid_prices)), reverse=True)
            
            if len(unique_prices) >= 2:
                # Higher price is original, lower is sale price
                price_info['original_price'] = unique_prices[0]
                price_info['sale_price'] = unique_prices[1]
                
                # Calculate discount percentage
                if price_info['original_price'] and price_info['sale_price']:
                    discount = ((price_info['original_price'] - price_info['sale_price']) / price_info['original_price']) * 100
                    price_info['discount_percentage'] = round(discount)
                    
            elif len(unique_prices) == 1:
                price_info['sale_price'] = unique_prices[0]
            
            # Look for discount percentage pattern
            discount_patterns = [
                r'(\d+)%\s*descuento',
                r'(\d+)%\s*de\s*descuento',
                r'ahorra\s+(\d+)%'
            ]
            
            for pattern in discount_patterns:
                discount_match = re.search(pattern, page_text, re.IGNORECASE)
                if discount_match:
                    price_info['discount_percentage'] = int(discount_match.group(1))
                    break
            
            # Look for promotion text
            promo_patterns = [
                r'(tienda.*?\d+%.*?descuento)',
                r'(oferta.*?especial)',
                r'(promoción.*?limitada)'
            ]
            
            for pattern in promo_patterns:
                promo_match = re.search(pattern, page_text, re.IGNORECASE)
                if promo_match:
                    price_info['promotion_text'] = promo_match.group(1)
                    break
                
        except Exception as e:
            logger.warning(f"Error extracting price info: {e}")
            
        return price_info
    
    def extract_stock_info(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract stock quantity from product page"""
        try:
            # Look for JavaScript data or quantity input
            quantity_input = soup.find('input', class_='js-quantity')
            if quantity_input and quantity_input.get('max'):
                return int(quantity_input.get('max'))
            
            # Look for stock indicators in page text
            page_text = soup.get_text()
            stock_patterns = [
                r'(\d+)\s*disponibles?',
                r'(\d+)\s*unidades?\s*disponibles?',
                r'stock:\s*(\d+)',
                r'cantidad\s*disponible:\s*(\d+)',
                r'(\d+)\s*en\s*stock'
            ]
            
            for pattern in stock_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return int(match.group(1))
            
            # Look for JavaScript data objects that might contain stock info
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    # Look for JSON data with stock information
                    stock_match = re.search(r'"stock"\s*:\s*(\d+)', script.string)
                    if stock_match:
                        return int(stock_match.group(1))
                    
                    # Look for quantity data
                    qty_match = re.search(r'"quantity"\s*:\s*(\d+)', script.string)
                    if qty_match:
                        return int(qty_match.group(1))
                    
        except Exception as e:
            logger.warning(f"Error extracting stock info: {e}")
            
        return None
    
    def extract_product_details(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract detailed product information"""
        details = {
            'detailed_description': None,
            'features': [],
            'included_items': [],
            'specifications': {},
            'additional_images': []
        }
        
        try:
            # Extract detailed description
            desc_selectors = [
                '.product-description',
                '.description',
                '[class*="descripcion"]',
                '.product-details'
            ]
            
            for selector in desc_selectors:
                desc_element = soup.select_one(selector)
                if desc_element:
                    details['detailed_description'] = desc_element.get_text(strip=True)
                    break
            
            # Extract features (look for lists)
            feature_lists = soup.find_all(['ul', 'ol'])
            for ul in feature_lists:
                if any(keyword in ul.get_text().lower() 
                      for keyword in ['características', 'features', 'beneficios']):
                    features = [li.get_text(strip=True) for li in ul.find_all('li')]
                    details['features'].extend(features)
            
            # Extract included items
            included_keywords = ['incluye', 'contiene', 'kit incluye']
            for keyword in included_keywords:
                included_section = soup.find(text=re.compile(keyword, re.IGNORECASE))
                if included_section:
                    parent = included_section.parent
                    if parent:
                        # Look for following list
                        next_ul = parent.find_next('ul')
                        if next_ul:
                            items = [li.get_text(strip=True) for li in next_ul.find_all('li')]
                            details['included_items'].extend(items)
            
            # Extract additional images
            img_elements = soup.find_all('img')
            for img in img_elements:
                src = img.get('src') or img.get('data-src')
                if src and 'product' in src.lower():
                    full_url = urljoin(self.base_url, src)
                    if full_url not in details['additional_images']:
                        details['additional_images'].append(full_url)
                        
        except Exception as e:
            logger.warning(f"Error extracting product details: {e}")
            
        return details
    
    async def scrape_product_page(self, product_url: str, product_id: str) -> Optional[ScrapedProductData]:
        """Scrape a single product page for detailed information"""
        
        try:
            logger.info(f"Scraping product {product_id}: {product_url}")
            
            page = await self.create_page()
            
            # Navigate to product page
            await page.goto(product_url, timeout=self.timeout)
            await page.wait_for_load_state('networkidle')
            
            # Get page content
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract SKU from URL or page
            sku_match = re.search(r'/Producto/(\d+)', product_url)
            sku = sku_match.group(1) if sku_match else None
            
            # Extract price information
            price_info = self.extract_price_info(soup)
            
            # Extract stock information
            stock_quantity = self.extract_stock_info(soup)
            
            # Extract detailed product information
            product_details = self.extract_product_details(soup)
            
            # Create scraped data object
            scraped_data = ScrapedProductData(
                product_id=product_id,
                sku=sku,
                original_price=price_info.get('original_price'),
                sale_price=price_info.get('sale_price'),
                discount_percentage=price_info.get('discount_percentage'),
                promotion_text=price_info.get('promotion_text'),
                stock_quantity=stock_quantity,
                **product_details
            )
            
            await page.close()
            
            logger.info(f"Successfully scraped product {product_id}")
            return scraped_data
            
        except Exception as e:
            logger.error(f"Error scraping product {product_id}: {e}")
            return None
    
    async def scrape_multiple_products(self, product_urls: List[tuple]) -> Dict[str, ScrapedProductData]:
        """Scrape multiple product pages concurrently"""
        
        results = {}
        semaphore = asyncio.Semaphore(3)  # Limit concurrent requests
        
        async def scrape_with_semaphore(url, product_id):
            async with semaphore:
                return await self.scrape_product_page(url, product_id)
        
        # Create tasks for all products
        tasks = [scrape_with_semaphore(url, pid) for url, pid in product_urls]
        
        # Execute tasks
        scraped_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(scraped_results):
            product_id = product_urls[i][1]
            if isinstance(result, ScrapedProductData):
                results[product_id] = result
            elif isinstance(result, Exception):
                logger.error(f"Error scraping product {product_id}: {result}")
        
        return results


# Test function
async def test_scraper():
    """Test the scraper with a single product"""
    test_url = "https://tienda.accu-chek.com.mx/Producto/3847?medidores=1"
    test_id = "3847"
    
    async with ProductScraper(headless=False) as scraper:
        # First, let's inspect the page structure
        page = await scraper.create_page()
        await page.goto(test_url, timeout=scraper.timeout)
        await page.wait_for_load_state('networkidle')
        
        # Take a screenshot for debugging
        await page.screenshot(path="debug_page.png")
        
        # Get content and check for key elements
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        # Debug: Print page title and some key elements
        print(f"Page title: {soup.title.string if soup.title else 'No title'}")
        
        # Look for price elements
        print("\n=== Price Elements ===")
        price_elements = soup.find_all(text=re.compile(r'\$\d+'))
        for i, elem in enumerate(price_elements[:5]):  # First 5 price elements
            print(f"Price {i+1}: {elem.strip()}")
        
        # Look for any elements with 'price' in class
        price_divs = soup.find_all(['div', 'span'], class_=re.compile(r'price', re.I))
        print(f"\nFound {len(price_divs)} elements with 'price' in class")
        for div in price_divs[:3]:
            print(f"Price div: {div.get_text(strip=True)[:100]}")
        
        await page.close()
        
        # Now run the actual scraper
        result = await scraper.scrape_product_page(test_url, test_id)
        
        if result:
            print("\n✅ Scraping successful!")
            print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        else:
            print("❌ Scraping failed")


if __name__ == "__main__":
    asyncio.run(test_scraper())