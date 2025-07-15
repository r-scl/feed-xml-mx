#!/usr/bin/env python3
"""
Feed Validator for FeedXML-MX v2.0
Validates generated feeds against Google Merchant Center and Facebook Catalog requirements
"""

import xml.etree.ElementTree as ET
import json
import re
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """Represents a validation issue"""
    severity: str  # 'error', 'warning', 'info'
    field: str
    message: str
    product_id: str = None
    platform: str = None


class FeedValidator:
    """Validates product feeds for Google and Facebook"""
    
    def __init__(self):
        self.issues: List[ValidationIssue] = []
        self.namespaces = {
            'g': 'http://base.google.com/ns/1.0'
        }
        
        # Required fields for each platform
        self.google_required = [
            'id', 'title', 'description', 'link', 'image_link', 
            'price', 'availability', 'condition', 'brand'
        ]
        
        self.facebook_required = [
            'id', 'title', 'description', 'link', 'image_link',
            'price', 'availability', 'condition', 'brand'
        ]
        
        # Recommended fields
        self.google_recommended = [
            'gtin', 'mpn', 'google_product_category', 'custom_label_0'
        ]
        
        self.facebook_recommended = [
            'gtin', 'mpn', 'quantity', 'sale_price'
        ]
    
    def add_issue(self, severity: str, field: str, message: str, 
                  product_id: str = None, platform: str = None):
        """Add a validation issue"""
        issue = ValidationIssue(
            severity=severity,
            field=field,
            message=message,
            product_id=product_id,
            platform=platform
        )
        self.issues.append(issue)
    
    def validate_url(self, url: str) -> bool:
        """Validate URL format"""
        if not url:
            return False
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None
    
    def validate_price(self, price: str) -> bool:
        """Validate price format"""
        if not price:
            return False
        # Allow formats like "123.45 MXN", "$123.45", "123,45"
        price_patterns = [
            r'^\d+\.?\d*\s*MXN$',  # "123.45 MXN"
            r'^\$\d+[,.]?\d*$',    # "$123.45" or "$123,45"
            r'^\d+[,.]?\d*$'       # "123.45" or "123,45"
        ]
        return any(re.match(pattern, price) for pattern in price_patterns)
    
    def validate_availability(self, availability: str) -> bool:
        """Validate availability values"""
        valid_values = [
            'in stock', 'out of stock', 'preorder', 
            'available for order', 'discontinued', 'pending'
        ]
        return availability and availability.lower() in valid_values
    
    def validate_condition(self, condition: str) -> bool:
        """Validate condition values"""
        valid_values = ['new', 'refurbished', 'used']
        return condition and condition.lower() in valid_values
    
    def validate_google_item(self, item: ET.Element) -> List[ValidationIssue]:
        """Validate a single Google Merchant item"""
        issues = []
        product_id = None
        
        # Get product ID for context
        id_elem = item.find('.//g:id', self.namespaces)
        if id_elem is not None:
            product_id = id_elem.text
        
        # Check required fields
        for field in self.google_required:
            elem = item.find(f'.//g:{field}', self.namespaces)
            if elem is None or not elem.text:
                issues.append(ValidationIssue(
                    severity='error',
                    field=field,
                    message=f'Required field {field} is missing or empty',
                    product_id=product_id,
                    platform='google'
                ))
        
        # Validate specific field formats
        link_elem = item.find('.//g:link', self.namespaces)
        if link_elem is not None and link_elem.text:
            if not self.validate_url(link_elem.text):
                issues.append(ValidationIssue(
                    severity='error',
                    field='link',
                    message='Invalid URL format',
                    product_id=product_id,
                    platform='google'
                ))
        
        image_elem = item.find('.//g:image_link', self.namespaces)
        if image_elem is not None and image_elem.text:
            if not self.validate_url(image_elem.text):
                issues.append(ValidationIssue(
                    severity='error',
                    field='image_link',
                    message='Invalid image URL format',
                    product_id=product_id,
                    platform='google'
                ))
        
        price_elem = item.find('.//g:price', self.namespaces)
        if price_elem is not None and price_elem.text:
            if not self.validate_price(price_elem.text):
                issues.append(ValidationIssue(
                    severity='error',
                    field='price',
                    message='Invalid price format',
                    product_id=product_id,
                    platform='google'
                ))
        
        avail_elem = item.find('.//g:availability', self.namespaces)
        if avail_elem is not None and avail_elem.text:
            if not self.validate_availability(avail_elem.text):
                issues.append(ValidationIssue(
                    severity='error',
                    field='availability',
                    message='Invalid availability value',
                    product_id=product_id,
                    platform='google'
                ))
        
        cond_elem = item.find('.//g:condition', self.namespaces)
        if cond_elem is not None and cond_elem.text:
            if not self.validate_condition(cond_elem.text):
                issues.append(ValidationIssue(
                    severity='error',
                    field='condition',
                    message='Invalid condition value',
                    product_id=product_id,
                    platform='google'
                ))
        
        # Check recommended fields
        for field in self.google_recommended:
            elem = item.find(f'.//g:{field}', self.namespaces)
            if elem is None or not elem.text:
                issues.append(ValidationIssue(
                    severity='warning',
                    field=field,
                    message=f'Recommended field {field} is missing',
                    product_id=product_id,
                    platform='google'
                ))
        
        # Check title length (recommended max 150 characters)
        title_elem = item.find('.//g:title', self.namespaces)
        if title_elem is not None and title_elem.text:
            if len(title_elem.text) > 150:
                issues.append(ValidationIssue(
                    severity='warning',
                    field='title',
                    message=f'Title length ({len(title_elem.text)}) exceeds recommended 150 characters',
                    product_id=product_id,
                    platform='google'
                ))
        
        # Check description length (recommended max 5000 characters)
        desc_elem = item.find('.//g:description', self.namespaces)
        if desc_elem is not None and desc_elem.text:
            if len(desc_elem.text) > 5000:
                issues.append(ValidationIssue(
                    severity='warning',
                    field='description',
                    message=f'Description length ({len(desc_elem.text)}) exceeds recommended 5000 characters',
                    product_id=product_id,
                    platform='google'
                ))
        
        return issues
    
    def validate_facebook_item(self, item: ET.Element) -> List[ValidationIssue]:
        """Validate a single Facebook Catalog item"""
        issues = []
        product_id = None
        
        # Get product ID for context
        id_elem = item.find('id')
        if id_elem is not None:
            product_id = id_elem.text
        
        # Check required fields
        for field in self.facebook_required:
            elem = item.find(field)
            if elem is None or not elem.text:
                issues.append(ValidationIssue(
                    severity='error',
                    field=field,
                    message=f'Required field {field} is missing or empty',
                    product_id=product_id,
                    platform='facebook'
                ))
        
        # Validate specific field formats
        link_elem = item.find('link')
        if link_elem is not None and link_elem.text:
            if not self.validate_url(link_elem.text):
                issues.append(ValidationIssue(
                    severity='error',
                    field='link',
                    message='Invalid URL format',
                    product_id=product_id,
                    platform='facebook'
                ))
        
        image_elem = item.find('image_link')
        if image_elem is not None and image_elem.text:
            if not self.validate_url(image_elem.text):
                issues.append(ValidationIssue(
                    severity='error',
                    field='image_link',
                    message='Invalid image URL format',
                    product_id=product_id,
                    platform='facebook'
                ))
        
        price_elem = item.find('price')
        if price_elem is not None and price_elem.text:
            if not self.validate_price(price_elem.text):
                issues.append(ValidationIssue(
                    severity='error',
                    field='price',
                    message='Invalid price format',
                    product_id=product_id,
                    platform='facebook'
                ))
        
        # Check recommended fields
        for field in self.facebook_recommended:
            elem = item.find(field)
            if elem is None or not elem.text:
                issues.append(ValidationIssue(
                    severity='warning',
                    field=field,
                    message=f'Recommended field {field} is missing',
                    product_id=product_id,
                    platform='facebook'
                ))
        
        # Check title length (recommended max 200 characters for Facebook)
        title_elem = item.find('title')
        if title_elem is not None and title_elem.text:
            if len(title_elem.text) > 200:
                issues.append(ValidationIssue(
                    severity='warning',
                    field='title',
                    message=f'Title length ({len(title_elem.text)}) exceeds recommended 200 characters',
                    product_id=product_id,
                    platform='facebook'
                ))
        
        return issues
    
    def validate_google_feed(self, feed_path: str) -> Dict[str, Any]:
        """Validate Google Merchant Center feed"""
        logger.info(f"Validating Google feed: {feed_path}")
        
        try:
            tree = ET.parse(feed_path)
            root = tree.getroot()
            
            # Check root structure
            if root.tag != 'rss':
                self.add_issue('error', 'root', 'Root element should be <rss>', platform='google')
            
            channel = root.find('channel')
            if channel is None:
                self.add_issue('error', 'structure', 'Missing <channel> element', platform='google')
                return {'valid': False, 'issues': self.issues}
            
            # Validate each item
            items = channel.findall('item')
            for item in items:
                item_issues = self.validate_google_item(item)
                self.issues.extend(item_issues)
            
            # Count statistics
            total_items = len(items)
            error_count = len([i for i in self.issues if i.severity == 'error' and i.platform == 'google'])
            warning_count = len([i for i in self.issues if i.severity == 'warning' and i.platform == 'google'])
            
            return {
                'valid': error_count == 0,
                'total_items': total_items,
                'errors': error_count,
                'warnings': warning_count,
                'platform': 'google'
            }
            
        except ET.ParseError as e:
            self.add_issue('error', 'xml', f'XML parsing error: {e}', platform='google')
            return {'valid': False, 'issues': self.issues}
    
    def validate_facebook_feed(self, feed_path: str) -> Dict[str, Any]:
        """Validate Facebook Catalog feed"""
        logger.info(f"Validating Facebook feed: {feed_path}")
        
        try:
            tree = ET.parse(feed_path)
            root = tree.getroot()
            
            # Check root structure
            if root.tag != 'rss':
                self.add_issue('error', 'root', 'Root element should be <rss>', platform='facebook')
            
            channel = root.find('channel')
            if channel is None:
                self.add_issue('error', 'structure', 'Missing <channel> element', platform='facebook')
                return {'valid': False, 'issues': self.issues}
            
            # Validate each item
            items = channel.findall('item')
            for item in items:
                item_issues = self.validate_facebook_item(item)
                self.issues.extend(item_issues)
            
            # Count statistics
            total_items = len(items)
            error_count = len([i for i in self.issues if i.severity == 'error' and i.platform == 'facebook'])
            warning_count = len([i for i in self.issues if i.severity == 'warning' and i.platform == 'facebook'])
            
            return {
                'valid': error_count == 0,
                'total_items': total_items,
                'errors': error_count,
                'warnings': warning_count,
                'platform': 'facebook'
            }
            
        except ET.ParseError as e:
            self.add_issue('error', 'xml', f'XML parsing error: {e}', platform='facebook')
            return {'valid': False, 'issues': self.issues}
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate validation report"""
        errors = [i for i in self.issues if i.severity == 'error']
        warnings = [i for i in self.issues if i.severity == 'warning']
        infos = [i for i in self.issues if i.severity == 'info']
        
        # Group issues by platform
        google_issues = [i for i in self.issues if i.platform == 'google']
        facebook_issues = [i for i in self.issues if i.platform == 'facebook']
        
        return {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_issues': len(self.issues),
                'errors': len(errors),
                'warnings': len(warnings),
                'infos': len(infos),
                'valid': len(errors) == 0
            },
            'by_platform': {
                'google': {
                    'total': len(google_issues),
                    'errors': len([i for i in google_issues if i.severity == 'error']),
                    'warnings': len([i for i in google_issues if i.severity == 'warning'])
                },
                'facebook': {
                    'total': len(facebook_issues),
                    'errors': len([i for i in facebook_issues if i.severity == 'error']),
                    'warnings': len([i for i in facebook_issues if i.severity == 'warning'])
                }
            },
            'issues': [
                {
                    'severity': i.severity,
                    'field': i.field,
                    'message': i.message,
                    'product_id': i.product_id,
                    'platform': i.platform
                }
                for i in self.issues
            ]
        }
    
    def save_report(self, output_path: str = 'output/validation_report.json'):
        """Save validation report to file"""
        report = self.generate_report()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Validation report saved to {output_path}")
        return output_path


def main():
    """Main validation function"""
    import os
    
    print("🔍 FeedXML-MX v2.0 - Feed Validator")
    print("=" * 50)
    
    validator = FeedValidator()
    
    # Check for feed files
    google_feed_path = 'output/feed_google_v2.xml'
    facebook_feed_path = 'output/feed_facebook_v2.xml'
    
    # Fallback to v1 feeds if v2 don't exist
    if not os.path.exists(google_feed_path):
        google_feed_path = 'output/feed_google.xml'
    if not os.path.exists(facebook_feed_path):
        facebook_feed_path = 'output/feed_facebook.xml'
    
    results = {}
    
    # Validate Google feed
    if os.path.exists(google_feed_path):
        google_result = validator.validate_google_feed(google_feed_path)
        results['google'] = google_result
        
        print(f"\n📊 Google Merchant Feed Validation:")
        print(f"   Items: {google_result.get('total_items', 0)}")
        print(f"   Errors: {google_result.get('errors', 0)}")
        print(f"   Warnings: {google_result.get('warnings', 0)}")
        print(f"   Status: {'✅ Valid' if google_result.get('valid') else '❌ Invalid'}")
    else:
        print(f"\n❌ Google feed not found: {google_feed_path}")
    
    # Validate Facebook feed
    if os.path.exists(facebook_feed_path):
        facebook_result = validator.validate_facebook_feed(facebook_feed_path)
        results['facebook'] = facebook_result
        
        print(f"\n📊 Facebook Catalog Feed Validation:")
        print(f"   Items: {facebook_result.get('total_items', 0)}")
        print(f"   Errors: {facebook_result.get('errors', 0)}")
        print(f"   Warnings: {facebook_result.get('warnings', 0)}")
        print(f"   Status: {'✅ Valid' if facebook_result.get('valid') else '❌ Invalid'}")
    else:
        print(f"\n❌ Facebook feed not found: {facebook_feed_path}")
    
    # Generate and save report
    os.makedirs('output', exist_ok=True)
    report_path = validator.save_report()
    
    print(f"\n📄 Validation report saved: {report_path}")
    
    # Print summary of critical issues
    critical_issues = [i for i in validator.issues if i.severity == 'error']
    if critical_issues:
        print(f"\n⚠️  Critical Issues Found ({len(critical_issues)}):")
        for issue in critical_issues[:5]:  # Show first 5
            print(f"   • {issue.platform} - {issue.field}: {issue.message}")
        if len(critical_issues) > 5:
            print(f"   ... and {len(critical_issues) - 5} more (see report for details)")
    
    total_errors = sum(r.get('errors', 0) for r in results.values())
    return total_errors == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)