#!/usr/bin/env python3
"""
Simple test to validate core dependencies
"""

def test_core_imports():
    """Test that all core dependencies can be imported"""
    failed_imports = []
    
    # Test core dependencies
    deps = [
        ("requests", "requests"),
        ("playwright", "playwright"),
        ("bs4", "beautifulsoup4"),
        ("lxml", "lxml"),
        ("pydantic", "pydantic"),
        ("aiohttp", "aiohttp"),
        ("aiofiles", "aiofiles"),
    ]
    
    for module, name in deps:
        try:
            __import__(module)
            print(f"✅ {name}")
        except ImportError as e:
            print(f"❌ {name}: {e}")
            failed_imports.append(name)
    
    # Test optional dependencies
    optional_deps = [
        ("structlog", "structlog"),
        ("psutil", "psutil"),
    ]
    
    for module, name in optional_deps:
        try:
            __import__(module)
            print(f"✅ {name} (optional)")
        except ImportError:
            print(f"⚠️ {name} (optional, not available)")
    
    if failed_imports:
        print(f"\n❌ Failed to import: {', '.join(failed_imports)}")
        return False
    else:
        print("\n🎉 All required dependencies imported successfully!")
        return True

if __name__ == "__main__":
    test_core_imports()