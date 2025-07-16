#!/usr/bin/env python3
"""
Test suite for FeedXML-MX v2.0
Tests both the scraper and feed processor functionality
"""

import os
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

from feed_processor_v2 import EnhancedFeedProcessor
from product_scraper import ScrapedProductData


class TestProductScraper(unittest.TestCase):
    """Test cases for the product scraper"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_url = "https://tienda.accu-chek.com.mx/Producto/3847"
        self.test_id = "3847"

    def test_scraped_product_data_creation(self):
        """Test ScrapedProductData creation and default values"""
        data = ScrapedProductData(product_id="123")

        self.assertEqual(data.product_id, "123")
        self.assertIsNone(data.sku)
        self.assertEqual(data.features, [])
        self.assertEqual(data.included_items, [])
        self.assertEqual(data.specifications, {})
        self.assertEqual(data.additional_images, [])
        self.assertIsNotNone(data.last_updated)

    def test_price_calculation(self):
        """Test discount percentage calculation"""
        data = ScrapedProductData(product_id="123", original_price=739.50, sale_price=628.58)

        # Should calculate ~15% discount
        self.assertAlmostEqual(data.discount_percentage, 15.0, places=0)
        expected_discount = round(((739.50 - 628.58) / 739.50) * 100)
        self.assertEqual(expected_discount, 15)


class TestEnhancedFeedProcessor(unittest.TestCase):
    """Test cases for the enhanced feed processor"""

    def setUp(self):
        """Set up test fixtures"""
        self.feed_url = "https://tienda.accu-chek.com.mx/Main/FeedXML"
        self.processor = EnhancedFeedProcessor(self.feed_url, enable_scraping=False)

        # Sample XML for testing
        self.sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
          <channel>
            <title>Test Feed</title>
            <item>
              <g:id>3847</g:id>
              <g:title>Test Product</g:title>
              <g:description>Test description</g:description>
              <g:link>https://tienda.accu-chek.com.mx/Producto/3847/test-product</g:link>
              <g:image_link>https://example.com/image.jpg</g:image_link>
              <g:price>628.58 MXN</g:price>
              <g:availability>in stock</g:availability>
              <g:condition>new</g:condition>
              <g:brand>Accu-Chek</g:brand>
              <g:gtin>1234567890</g:gtin>
            </item>
          </channel>
        </rss>"""

    def test_clean_url(self):
        """Test URL cleaning functionality"""
        test_cases = [
            (
                "https://tienda.accu-chek.com.mx/Main/Producto/3847/test-product-name",
                "https://tienda.accu-chek.com.mx/Main/Producto/3847/",
            ),
            (
                "https://tienda.accu-chek.com.mx/Main/Producto/1916/50-tiras-reactivas",
                "https://tienda.accu-chek.com.mx/Main/Producto/1916/",
            ),
            (
                "https://other-site.com/product/123",
                "https://other-site.com/product/123",  # Should remain unchanged
            ),
        ]

        for input_url, expected_output in test_cases:
            with self.subTest(input_url=input_url):
                result = self.processor.clean_url(input_url)
                self.assertEqual(result, expected_output)

    def test_price_formatting(self):
        """Test price formatting for different platforms"""
        test_price = "628.58 MXN"

        # Test Google formatting
        google_price = self.processor.format_price(test_price, "google")
        self.assertEqual(google_price, "628.58 MXN")

        # Test Facebook formatting
        facebook_price = self.processor.format_price(test_price, "facebook")
        self.assertEqual(facebook_price, "$628,58")

    def test_extract_product_urls(self):
        """Test extraction of product URLs from XML"""
        root = ET.fromstring(self.sample_xml)
        product_urls = self.processor.extract_product_urls(root)

        self.assertEqual(len(product_urls), 1)
        self.assertEqual(product_urls[0][0], "https://tienda.accu-chek.com.mx/Producto/3847/test-product")
        self.assertEqual(product_urls[0][1], "3847")

    def test_enhanced_data_integration(self):
        """Test integration of scraped data with feed processing"""
        # Mock scraped data
        scraped_data = ScrapedProductData(
            product_id="3847",
            sku="SKU-3847",
            original_price=739.50,
            sale_price=628.58,
            discount_percentage=15,
            stock_quantity=63,
            detailed_description="Enhanced description with detailed features",
        )

        self.processor.scraped_data = {"3847": scraped_data}

        # Get enhanced data
        enhanced_data = self.processor.get_enhanced_product_data(None, "3847")

        self.assertEqual(enhanced_data["original_price"], 739.50)
        self.assertEqual(enhanced_data["sale_price"], 628.58)
        self.assertEqual(enhanced_data["discount_percentage"], 15)
        self.assertEqual(enhanced_data["stock_quantity"], 63)
        self.assertEqual(enhanced_data["sku"], "SKU-3847")

    def test_google_feed_processing(self):
        """Test Google feed processing with enhancements"""
        root = ET.fromstring(self.sample_xml)

        # Add mock scraped data
        scraped_data = ScrapedProductData(product_id="3847", original_price=739.50, sale_price=628.58, sku="SKU-3847")
        self.processor.scraped_data = {"3847": scraped_data}

        # Process feed
        google_root = self.processor.process_feed_google(root)

        # Find the processed item
        item = google_root.find(".//item")
        self.assertIsNotNone(item)

        # Check for enhanced elements by converting to string
        xml_string = ET.tostring(google_root, encoding="unicode")

        # Check that enhancements are present
        self.assertIn("SKU-3847", xml_string, "SKU should be present in the XML")
        self.assertIn("491", xml_string, "Google product category should be present")
        self.assertIn("custom_label", xml_string, "Custom labels should be present")

    def test_facebook_feed_processing(self):
        """Test Facebook feed processing with enhancements"""
        root = ET.fromstring(self.sample_xml)

        # Add mock scraped data
        scraped_data = ScrapedProductData(
            product_id="3847",
            sale_price=628.58,
            stock_quantity=63,
            detailed_description="Enhanced Facebook description",
        )
        self.processor.scraped_data = {"3847": scraped_data}

        # Process feed
        facebook_root = self.processor.process_feed_facebook(root)

        # Find the processed item
        item = facebook_root.find(".//item")
        self.assertIsNotNone(item)

        # Check for Facebook-specific enhancements
        quantity_elem = item.find("quantity")
        self.assertIsNotNone(quantity_elem)
        self.assertEqual(quantity_elem.text, "63")

        # Check description enhancement
        desc_elem = item.find("description")
        self.assertIsNotNone(desc_elem)
        self.assertEqual(desc_elem.text, "Enhanced Facebook description.")


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete system"""

    def setUp(self):
        """Set up integration test fixtures"""
        self.feed_url = "https://tienda.accu-chek.com.mx/Main/FeedXML"

    @patch("requests.get")
    def test_feed_fetching(self, mock_get):
        """Test XML feed fetching"""
        # Mock the response
        mock_response = Mock()
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
          <channel>
            <title>Accu-Chek Mexico</title>
            <item>
              <g:id>3847</g:id>
              <g:title>Test Product</g:title>
            </item>
          </channel>
        </rss>"""
        mock_get.return_value = mock_response

        processor = EnhancedFeedProcessor(self.feed_url, enable_scraping=False)
        xml_content = processor.fetch_feed()

        self.assertIn("Test Product", xml_content)
        mock_get.assert_called_once_with(self.feed_url)

    def test_output_file_creation(self):
        """Test that output files are created with correct structure"""
        # Create a minimal processor for testing
        processor = EnhancedFeedProcessor(self.feed_url, enable_scraping=False)

        # Create test XML
        root = ET.fromstring(
            """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
          <channel>
            <title>Test</title>
            <item>
              <g:id>123</g:id>
              <g:title>Test</g:title>
            </item>
          </channel>
        </rss>"""
        )

        # Process and save
        google_root = processor.process_feed_google(root)

        # Create output directory if it doesn't exist
        os.makedirs("test_output", exist_ok=True)

        # Save test file
        output_file = processor.save_feed(google_root, "test_output/test_google.xml", "google")

        # Verify file exists and has content
        self.assertTrue(os.path.exists(output_file))

        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("<?xml version=", content)
            self.assertIn('xmlns:g="http://base.google.com/ns/1.0"', content)

        # Cleanup
        os.remove(output_file)
        os.rmdir("test_output")


def run_tests():
    """Run all tests"""
    print("🧪 Running FeedXML-MX v2.0 Test Suite")
    print("=" * 50)

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestProductScraper))
    suite.addTests(loader.loadTestsFromTestCase(TestEnhancedFeedProcessor))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("✅ All tests passed!")
    else:
        print(f"❌ {len(result.failures + result.errors)} test(s) failed")
        for failure in result.failures:
            print(f"FAIL: {failure[0]}")
        for error in result.errors:
            print(f"ERROR: {error[0]}")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
