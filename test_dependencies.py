#!/usr/bin/env python3
"""
Simple test to validate core dependencies
"""

def test_core_imports():
    """Test that all core dependencies can be imported"""
    try:
        import requests
        print("✅ requests")
        
        import playwright
        print("✅ playwright")
        
        import bs4
        print("✅ beautifulsoup4")
        
        import lxml
        print("✅ lxml")
        
        import pydantic
        print("✅ pydantic")
        
        import aiohttp
        print("✅ aiohttp")
        
        import aiofiles
        print("✅ aiofiles")
        
        import structlog
        print("✅ structlog")
        
        import psutil
        print("✅ psutil")
        
        print("\n🎉 All core dependencies imported successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

if __name__ == "__main__":
    test_core_imports()