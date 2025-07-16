#!/usr/bin/env python3
"""
Enhanced data models with Pydantic v2 and strict validation
Following 2025 best practices for type safety and performance
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Dict, List, Optional, Union
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
    ConfigDict,
    ValidationError,
    computed_field
)
from pydantic.types import PositiveInt, PositiveFloat, NonNegativeInt


class ScrapedProductData(BaseModel):
    """Enhanced product data model with strict validation"""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=False,
        extra='forbid',
        frozen=False,  # Allow updates for caching
        cache_strings=True,  # Performance optimization
    )
    
    # Core identification
    product_id: Annotated[str, Field(min_length=1, max_length=50, pattern=r'^\d+$')]
    sku: Optional[Annotated[str, Field(min_length=1, max_length=50)]] = None
    
    # Pricing with Decimal for precision
    original_price: Optional[PositiveFloat] = None
    sale_price: Optional[PositiveFloat] = None
    discount_percentage: Optional[Annotated[int, Field(ge=0, le=100)]] = None
    promotion_text: Optional[Annotated[str, Field(max_length=500)]] = None
    
    # Inventory
    stock_quantity: Optional[NonNegativeInt] = None
    
    # Content
    detailed_description: Optional[Annotated[str, Field(max_length=5000)]] = None
    features: List[Annotated[str, Field(max_length=200)]] = Field(default_factory=list)
    included_items: List[Annotated[str, Field(max_length=200)]] = Field(default_factory=list)
    specifications: Dict[str, str] = Field(default_factory=dict)
    
    # Media
    additional_images: List[HttpUrl] = Field(default_factory=list)
    
    # Metadata
    last_updated: datetime = Field(default_factory=datetime.now)
    
    @field_validator('additional_images')
    @classmethod
    def validate_image_urls(cls, urls: List[str]) -> List[HttpUrl]:
        """Validate and limit number of additional images"""
        if len(urls) > 10:  # Limit to 10 additional images
            urls = urls[:10]
        return urls
    
    @model_validator(mode='after')
    def validate_pricing_consistency(self) -> 'ScrapedProductData':
        """Ensure pricing data consistency"""
        if self.original_price and self.sale_price:
            if self.sale_price > self.original_price:
                raise ValueError("Sale price cannot exceed original price")
            
            # Calculate discount if not provided
            if not self.discount_percentage:
                discount = ((self.original_price - self.sale_price) / self.original_price) * 100
                self.discount_percentage = round(discount)
        
        return self
    
    @computed_field
    @property
    def effective_price(self) -> Optional[float]:
        """Get the effective selling price"""
        return self.sale_price or self.original_price
    
    @computed_field
    @property
    def has_discount(self) -> bool:
        """Check if product has active discount"""
        return bool(self.original_price and self.sale_price and self.sale_price < self.original_price)


class ProductFeed(BaseModel):
    """Base model for product feed items"""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid',
    )
    
    id: Annotated[str, Field(min_length=1, max_length=50)]
    title: Annotated[str, Field(min_length=1, max_length=150)]
    description: Annotated[str, Field(min_length=1, max_length=5000)]
    link: HttpUrl
    image_link: HttpUrl
    availability: Annotated[str, Field(pattern=r'^(in stock|out of stock|preorder|backorder)$')]
    condition: Annotated[str, Field(pattern=r'^(new|refurbished|used)$')] = 'new'
    price: Annotated[str, Field(pattern=r'^\$?[\d,]+\.?\d*\s*(MXN|USD)?$')]
    brand: Annotated[str, Field(min_length=1, max_length=70)] = 'Roche'
    gtin: Optional[Annotated[str, Field(min_length=8, max_length=14, pattern=r'^\d+$')]] = None
    mpn: Optional[Annotated[str, Field(min_length=1, max_length=70)]] = None
    
    @field_validator('link', 'image_link')
    @classmethod
    def validate_urls_domain(cls, url: HttpUrl) -> HttpUrl:
        """Ensure URLs are from the expected domain"""
        parsed = urlparse(str(url))
        allowed_domains = ['tienda.accu-chek.com.mx', 'cdn.gdar.com.mx']
        if parsed.netloc not in allowed_domains:
            raise ValueError(f"URL domain {parsed.netloc} not in allowed domains: {allowed_domains}")
        return url


class GoogleMerchantFeed(ProductFeed):
    """Google Merchant Center specific feed model"""
    
    # Google-specific fields with namespace
    google_product_category: Optional[str] = Field(alias='g:google_product_category', default=None)
    product_type: Optional[str] = Field(alias='g:product_type', default=None)
    custom_label_0: Optional[str] = Field(alias='g:custom_label_0', default=None)
    custom_label_1: Optional[str] = Field(alias='g:custom_label_1', default=None)
    sale_price: Optional[str] = Field(alias='g:sale_price', default=None)
    sale_price_effective_date: Optional[str] = Field(alias='g:sale_price_effective_date', default=None)
    additional_image_link: List[HttpUrl] = Field(alias='g:additional_image_link', default_factory=list)
    
    model_config = ConfigDict(
        populate_by_name=True,  # Allow both field names and aliases
        str_strip_whitespace=True,
    )


class FacebookCatalogFeed(ProductFeed):
    """Facebook Catalog specific feed model"""
    
    # Facebook-specific fields (no namespace)
    quantity: Optional[NonNegativeInt] = None
    sale_price: Optional[str] = None
    additional_image_link: List[HttpUrl] = Field(default_factory=list)
    
    @field_validator('additional_image_link')
    @classmethod
    def limit_facebook_images(cls, urls: List[HttpUrl]) -> List[HttpUrl]:
        """Facebook supports up to 20 additional images"""
        return urls[:20] if len(urls) > 20 else urls


class FeedMetadata(BaseModel):
    """Metadata for feed generation process"""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
    )
    
    version: Annotated[str, Field(pattern=r'^\d+\.\d+$')] = '2.0'
    last_update: datetime = Field(default_factory=datetime.now)
    source_url: HttpUrl
    scraping_enabled: bool = True
    products_scraped: NonNegativeInt = 0
    google_feed: Annotated[str, Field(pattern=r'^[\w/.-]+\.xml$')]
    facebook_feed: Annotated[str, Field(pattern=r'^[\w/.-]+\.xml$')]
    enhancements: List[str] = Field(default_factory=list)
    
    @field_validator('enhancements')
    @classmethod
    def validate_enhancements_list(cls, enhancements: List[str]) -> List[str]:
        """Ensure enhancements are unique and non-empty"""
        return list(dict.fromkeys(filter(None, enhancements)))  # Remove duplicates and empty strings


class ScrapingConfig(BaseModel):
    """Configuration for scraping operations"""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid',
    )
    
    max_concurrent_requests: Annotated[int, Field(ge=1, le=10)] = 3
    request_timeout: Annotated[int, Field(ge=10000, le=60000)] = 30000  # milliseconds
    headless_browser: bool = True
    retry_attempts: Annotated[int, Field(ge=0, le=5)] = 2
    delay_between_requests: Annotated[float, Field(ge=0.5, le=10.0)] = 1.0  # seconds
    user_agent: str = "Mozilla/5.0 (compatible; FeedXML-MX/2.0; +https://github.com/example/feedxml-mx)"
    
    @field_validator('user_agent')
    @classmethod
    def validate_user_agent(cls, ua: str) -> str:
        """Ensure user agent is appropriate length"""
        if len(ua) > 200:
            raise ValueError("User agent too long")
        return ua


class ValidationResult(BaseModel):
    """Result of feed validation"""
    
    model_config = ConfigDict(validate_assignment=True)
    
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    products_validated: NonNegativeInt = 0
    validation_time: Optional[datetime] = Field(default_factory=datetime.now)
    
    @computed_field
    @property
    def has_errors(self) -> bool:
        """Check if validation has errors"""
        return len(self.errors) > 0
    
    @computed_field
    @property
    def has_warnings(self) -> bool:
        """Check if validation has warnings"""
        return len(self.warnings) > 0