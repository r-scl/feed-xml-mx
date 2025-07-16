#!/usr/bin/env python3
"""
Enhanced Web Scraper for Accu-Chek Mexico Product Data
Optimized for tienda.accu-chek.com.mx with specific selectors
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


class EnhancedProductScraper:
    """Enhanced web scraper optimized for Accu-Chek Mexico product pages"""
    
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
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        
        return page
    
    def extract_dataproj_info(self, page_content: str) -> Optional[Dict[str, Any]]:
        """Extract the dataProd JavaScript object from Accu-Chek pages"""
        try:
            # Look for dataProd object in JavaScript
            patterns = [
                r'let\s+dataProd\s*=\s*({[^;]+});',
                r'var\s+dataProd\s*=\s*({[^;]+});',
                r'dataProd\s*=\s*({[^;]+});'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, page_content, re.DOTALL)
                if match:
                    try:
                        json_str = match.group(1)
                        # Clean up the JSON string
                        json_str = re.sub(r'\/Date\((\d+)\)\/', r'"\1"', json_str)  # Fix .NET dates
                        data = json.loads(json_str)
                        logger.info(f"Found dataProd object with {len(data)} fields")
                        return data
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse dataProd JSON: {e}")
                        continue
                        
        except Exception as e:
            logger.warning(f"Error extracting dataProd: {e}")
        
        return None

    def extract_price_info(self, soup: BeautifulSoup, page_content: str) -> Dict[str, Any]:
        """Extract price information from Accu-Chek product page"""
        price_info = {
            'original_price': None,
            'sale_price': None,
            'discount_percentage': None,
            'promotion_text': None
        }
        
        try:
            # First try to get data from dataProd JavaScript object
            data_prod = self.extract_dataproj_info(page_content)
            if data_prod:
                # Extract price from dataProd
                if 'precioConIVA' in data_prod:
                    price_info['sale_price'] = float(data_prod['precioConIVA'])
                
                # Extract promotion information first (more specific)
                has_promotion = False
                if 'promociones' in data_prod and data_prod['promociones']:
                    promociones = data_prod['promociones']
                    if 'descuentosUnicos' in promociones and promociones['descuentosUnicos']:
                        promo = promociones['descuentosUnicos'][0]
                        if 'descripcion' in promo:
                            price_info['promotion_text'] = promo['descripcion']
                        if 'descuento' in promo and promo['descuento'] > 0:
                            discount_pct = promo['descuento']
                            price_info['discount_percentage'] = discount_pct
                            # Calculate original price from promotion discount
                            if price_info['sale_price']:
                                price_info['original_price'] = price_info['sale_price'] / (1 - discount_pct / 100)
                            has_promotion = True
                
                # Extract generic discount information (fallback)
                if not has_promotion and 'descuento' in data_prod and data_prod['descuento'] > 0:
                    discount_pct = data_prod['descuento']
                    price_info['discount_percentage'] = discount_pct
                    # Calculate original price
                    if price_info['sale_price']:
                        price_info['original_price'] = price_info['sale_price'] / (1 - discount_pct / 100)
                
                return price_info
            
            # Fallback to HTML extraction if dataProd not found
            # Look for prices in JSON-LD structured data first
            json_ld = soup.find('script', {'type': 'application/ld+json'})
            if json_ld:
                try:
                    data = json.loads(json_ld.string)
                    if 'offers' in data:
                        offer = data['offers']
                        if 'price' in offer:
                            price_info['sale_price'] = float(offer['price'])
                        if 'priceCurrency' in offer and offer['priceCurrency'] == 'MXN':
                            # Found structured price data
                            return price_info
                except (json.JSONDecodeError, KeyError):
                    pass
            
            # Look for prices in specific Accu-Chek selectors
            price_selectors = [
                '.precio-actual',
                '.price-current',
                '.product-price',
                '.precio',
                '[class*="precio"]',
                '[id*="precio"]',
                '.price'
            ]
            
            # Look for original price (usually crossed out)
            original_selectors = [
                '.precio-original',
                '.precio-antes',
                '.price-original',
                '.price-before',
                '[style*="line-through"]',
                '.strikethrough'
            ]
            
            # Extract original price
            for selector in original_selectors:
                elem = soup.select_one(selector)
                if elem:
                    price_text = elem.get_text(strip=True)
                    price_match = re.search(r'(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text.replace(',', ''))
                    if price_match:
                        price_info['original_price'] = float(price_match.group(1))
                        break
            
            # Extract current/sale price
            for selector in price_selectors:
                elem = soup.select_one(selector)
                if elem:
                    price_text = elem.get_text(strip=True)
                    # Look for Mexican peso prices
                    price_match = re.search(r'(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text.replace(',', ''))
                    if price_match:
                        price_info['sale_price'] = float(price_match.group(1))
                        break
            
            # If no sale price found, look in page content
            if not price_info['sale_price']:
                price_patterns = [
                    r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*MXN',
                    r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*MXN',
                    r'precio["\']?\s*:\s*["\']?(\d+(?:\.\d{2})?)',
                ]
                
                for pattern in price_patterns:
                    match = re.search(pattern, page_content, re.IGNORECASE)
                    if match:
                        price_info['sale_price'] = float(match.group(1).replace(',', ''))
                        break
            
            # Calculate discount if both prices available
            if price_info['original_price'] and price_info['sale_price']:
                if price_info['original_price'] > price_info['sale_price']:
                    discount = ((price_info['original_price'] - price_info['sale_price']) / price_info['original_price']) * 100
                    price_info['discount_percentage'] = round(discount)
                else:
                    # If sale price >= original price, treat original as sale price
                    price_info['original_price'] = None
            
            # Look for promotion text
            promo_selectors = [
                '.promocion',
                '.descuento',
                '.oferta',
                '.promotion',
                '.discount',
                '[class*="promo"]'
            ]
            
            for selector in promo_selectors:
                elem = soup.select_one(selector)
                if elem:
                    price_info['promotion_text'] = elem.get_text(strip=True)
                    break
                    
        except Exception as e:
            logger.warning(f"Error extracting price info: {e}")
        
        return price_info
    
    def extract_detailed_description(self, soup: BeautifulSoup, product_title: str, page_content: str) -> str:
        """Extract and enhance product description based on Accu-Chek product types"""
        
        # First try to get description from dataProd JavaScript object
        data_prod = self.extract_dataproj_info(page_content)
        base_description = ""
        
        if data_prod:
            # Use descripcionLarga if available, otherwise use descripcion
            if 'descripcionLarga' in data_prod and data_prod['descripcionLarga'].strip():
                base_description = data_prod['descripcionLarga'].strip()
            elif 'descripcion' in data_prod and data_prod['descripcion'].strip():
                base_description = data_prod['descripcion'].strip()
                # Add period to differentiate from title
                if not base_description.endswith('.'):
                    base_description += '.'
            
            # Add specifications if available
            if 'especificaciones' in data_prod and data_prod['especificaciones']:
                spec_text = []
                for spec in data_prod['especificaciones']:
                    if 'especificacion' in spec:
                        spec_text.append(spec['especificacion'])
                
                if spec_text:
                    base_description += f" Especificaciones: {' • '.join(spec_text[:3])}."  # Limit to 3 specs
        
        # Fallback to HTML extraction if dataProd not found
        if not base_description:
            desc_selectors = [
                '.product-description',
                '.descripcion-producto',
                '.product-info',
                '.producto-descripcion',
                '[class*="descripcion"]',
                '[id*="descripcion"]',
                '.product-details',
                '.content-description'
            ]
            
            for selector in desc_selectors:
                elem = soup.select_one(selector)
                if elem:
                    base_description = elem.get_text(strip=True)
                    if len(base_description) > 50:  # Ensure we get substantial content
                        break
        
        # Enhance based on product type
        title_lower = product_title.lower()
        
        enhanced_descriptions = {
            'tiras reactivas': {
                'intro': 'Tiras reactivas para medición precisa de glucosa en sangre.',
                'features': [
                    'Compatible con medidores Accu-Chek',
                    'Resultados rápidos y precisos',
                    'Fácil manejo y aplicación',
                    'Tecnología avanzada de biosensores'
                ]
            },
            'lancetas': {
                'intro': 'Lancetas estériles diseñadas para punción digital cómoda.',
                'features': [
                    'Diseño optimizado para minimizar el dolor',
                    'Estériles y de uso único',
                    'Compatible con dispositivos Accu-Chek Softclix',
                    'Muestra de sangre adecuada con mínima molestia'
                ]
            },
            'medidor': {
                'intro': 'Medidor de glucosa en sangre para monitoreo diabético diario.',
                'features': [
                    'Pantalla grande y fácil lectura',
                    'Memoria para almacenar resultados',
                    'Rápido tiempo de medición',
                    'Tecnología de precisión médica'
                ]
            },
            'glucómetro': {
                'intro': 'Glucómetro digital para control preciso de diabetes.',
                'features': [
                    'Mediciones en segundos',
                    'Pantalla digital clara',
                    'Almacenamiento de resultados',
                    'Fácil calibración automática'
                ]
            },
            'kit': {
                'intro': 'Kit completo para monitoreo de glucosa en sangre.',
                'features': [
                    'Todo lo necesario para comenzar',
                    'Incluye medidor y accesorios',
                    'Ideal para nuevos usuarios',
                    'Garantía y soporte técnico'
                ]
            },
            'pack': {
                'intro': 'Pack económico con múltiples productos para el cuidado diabético.',
                'features': [
                    'Ahorro significativo vs compra individual',
                    'Productos complementarios incluidos',
                    'Stock suficiente para uso prolongado',
                    'Calidad garantizada Accu-Chek'
                ]
            }
        }
        
        # Find matching product type
        enhanced_info = None
        for key, info in enhanced_descriptions.items():
            if key in title_lower:
                enhanced_info = info
                break
        
        if enhanced_info:
            enhanced = f"{enhanced_info['intro']} "
            if base_description and len(base_description) > 20:
                enhanced += f"{base_description} "
            enhanced += f"Características: {' • '.join(enhanced_info['features'])}."
        else:
            enhanced = base_description if base_description else f"Producto médico Accu-Chek de alta calidad. {product_title}."
        
        return enhanced
    
    def extract_product_images(self, soup: BeautifulSoup, page_content: str) -> List[str]:
        """Extract all product images from Accu-Chek pages"""
        images = []
        
        try:
            # Look for main product image
            main_img_selectors = [
                '.product-image img',
                '.imagen-producto img',
                '.main-image img',
                '#main-image img',
                '.product-photo img'
            ]
            
            # Look for gallery/additional images
            gallery_selectors = [
                '.product-gallery img',
                '.galeria-producto img',
                '.product-images img',
                '.image-gallery img',
                '.thumbnails img',
                '[class*="gallery"] img',
                '[class*="galeria"] img'
            ]
            
            all_selectors = main_img_selectors + gallery_selectors
            
            # Extract from img elements
            for selector in all_selectors:
                img_elements = soup.select(selector)
                for img in img_elements:
                    # Try different src attributes
                    src = (img.get('src') or 
                           img.get('data-src') or 
                           img.get('data-lazy-src') or
                           img.get('data-original'))
                    
                    if src and self._is_valid_product_image(src):
                        full_url = urljoin(self.base_url, src)
                        if full_url not in images:
                            images.append(full_url)
            
            # Look for images in JavaScript/JSON data
            img_patterns = [
                r'"(https://cdn\.gdar\.com\.mx/[^"]*\.(?:jpg|jpeg|png|webp))"',
                r"'(https://cdn\.gdar\.com\.mx/[^']*\.(?:jpg|jpeg|png|webp))'",
                r'src="([^"]*\.(?:jpg|jpeg|png|webp))"'
            ]
            
            for pattern in img_patterns:
                matches = re.findall(pattern, page_content, re.IGNORECASE)
                for match in matches:
                    if self._is_valid_product_image(match):
                        full_url = urljoin(self.base_url, match)
                        if full_url not in images:
                            images.append(full_url)
            
        except Exception as e:
            logger.warning(f"Error extracting images: {e}")
        
        return images[:10]  # Limit to 10 images
    
    def _is_valid_product_image(self, src: str) -> bool:
        """Validate if image is a valid product image"""
        if not src:
            return False
            
        # Invalid patterns
        invalid_patterns = [
            'logo', 'banner', 'icon', 'sprite', 'loading', 
            'placeholder', 'thumb', 'favicon', 'header',
            'footer', 'menu', 'nav', 'social'
        ]
        
        src_lower = src.lower()
        
        # Check for invalid patterns
        if any(pattern in src_lower for pattern in invalid_patterns):
            return False
        
        # Must be a valid image extension
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        if not any(ext in src_lower for ext in valid_extensions):
            return False
        
        # Prefer CDN images (Accu-Chek uses cdn.gdar.com.mx)
        if 'cdn.gdar.com.mx' in src_lower:
            return True
        
        # Check for product-related patterns
        product_patterns = ['product', 'producto', 'ecommerce', 'accu-chek']
        return any(pattern in src_lower for pattern in product_patterns)
    
    def extract_stock_info(self, soup: BeautifulSoup, page_content: str) -> Optional[int]:
        """Extract stock quantity information"""
        try:
            # First try to get stock from dataProd JavaScript object
            data_prod = self.extract_dataproj_info(page_content)
            if data_prod and 'disponibles' in data_prod:
                stock_qty = data_prod['disponibles']
                if isinstance(stock_qty, (int, float)):
                    return int(stock_qty)
            
            # Fallback to HTML extraction
            # Look for stock indicators in Spanish
            stock_selectors = [
                '[class*="stock"]',
                '[class*="disponible"]',
                '[class*="inventario"]',
                '[id*="stock"]'
            ]
            
            for selector in stock_selectors:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text().lower()
                    
                    # Look for "out of stock" indicators
                    if any(phrase in text for phrase in ['agotado', 'sin stock', 'no disponible']):
                        return 0
                    
                    # Look for quantity numbers
                    qty_match = re.search(r'(\d+)\s*(?:disponible|en stock|unidades)', text)
                    if qty_match:
                        return int(qty_match.group(1))
            
            # Look in page content for stock info
            stock_patterns = [
                r'stock["\']?\s*:\s*["\']?(\d+)',
                r'quantity["\']?\s*:\s*["\']?(\d+)',
                r'disponible["\']?\s*:\s*["\']?(\d+)'
            ]
            
            for pattern in stock_patterns:
                match = re.search(pattern, page_content, re.IGNORECASE)
                if match:
                    return int(match.group(1))
                    
        except Exception as e:
            logger.warning(f"Error extracting stock info: {e}")
        
        # Default to None (unknown stock)
        return None
    
    async def scrape_product(self, product_url: str, product_id: str) -> Optional[ScrapedProductData]:
        """Scrape a single product page with enhanced extraction"""
        try:
            logger.info(f"Scraping product {product_id}: {product_url}")
            
            page = await self.create_page()
            
            # Navigate to product page
            await page.goto(product_url, timeout=self.timeout)
            
            # Wait for content to load
            await page.wait_for_load_state('networkidle', timeout=10000)
            
            # Get page content
            page_content = await page.content()
            soup = BeautifulSoup(page_content, 'html.parser')
            
            # Extract product title
            title_selectors = [
                'h1.product-title',
                'h1.titulo-producto', 
                '.product-name',
                'h1',
                '.product-title'
            ]
            
            product_title = product_id  # fallback
            for selector in title_selectors:
                elem = soup.select_one(selector)
                if elem:
                    product_title = elem.get_text(strip=True)
                    break
            
            # Extract all enhanced data
            price_info = self.extract_price_info(soup, page_content)
            detailed_desc = self.extract_detailed_description(soup, product_title, page_content)
            images = self.extract_product_images(soup, page_content)
            stock_qty = self.extract_stock_info(soup, page_content)
            
            # Create enhanced product data
            scraped_data = ScrapedProductData(
                product_id=product_id,
                sku=product_id,  # Use product_id as SKU
                original_price=price_info['original_price'],
                sale_price=price_info['sale_price'],
                discount_percentage=price_info['discount_percentage'],
                promotion_text=price_info['promotion_text'],
                stock_quantity=stock_qty,
                detailed_description=detailed_desc,
                additional_images=images,
                last_updated=datetime.now().isoformat()
            )
            
            await page.close()
            
            logger.info(f"Successfully scraped product {product_id}")
            return scraped_data
            
        except Exception as e:
            logger.error(f"Error scraping product {product_id}: {e}")
            if 'page' in locals():
                await page.close()
            return None
    
    async def scrape_multiple_products(self, product_urls: List[tuple], max_concurrent: int = 3) -> Dict[str, ScrapedProductData]:
        """Scrape multiple products with concurrency control"""
        results = {}
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def scrape_with_semaphore(url_id_pair):
            async with semaphore:
                url, product_id = url_id_pair
                return await self.scrape_product(url, product_id)
        
        # Execute scraping tasks
        tasks = [scrape_with_semaphore((url, pid)) for url, pid in product_urls]
        scraped_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(scraped_results):
            if isinstance(result, Exception):
                logger.error(f"Exception in scraping task {i}: {result}")
                continue
            
            if result:
                results[result.product_id] = result
        
        logger.info(f"Successfully scraped {len(results)} out of {len(product_urls)} products")
        return results


# Alias for backward compatibility
ProductScraper = EnhancedProductScraper