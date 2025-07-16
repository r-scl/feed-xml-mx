# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FeedXML-MX is a Python-based XML feed processor for Accu-Chek Mexico's e-commerce platform. It fetches product data from `https://tienda.accu-chek.com.mx/Main/FeedXML` and generates two optimized feeds:
- Google Merchant Center feed with `g:` namespace
- Facebook Catalog feed with flat structure

The project includes two versions:
- `feed_processor.py`: Basic feed processor that transforms the original XML
- `feed_processor_v2.py`: Enhanced version with Playwright-based web scraping for additional product details

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for v2)
playwright install chromium

# Run basic feed processor
python feed_processor.py

# Run enhanced feed processor with web scraping
python feed_processor_v2.py

# Output files will be generated in:
# - output/feed_google.xml
# - output/feed_facebook.xml
# - output/metadata.json
# - output/product_details.json (v2 only)
```

## Architecture & Key Components

### Core Processing Logic
The `FeedProcessor` class handles all transformations:
- **URL Cleaning**: Strips product titles from URLs (e.g., `/Main/Producto/1916/50-Tiras-Reactivas...` → `/Main/Producto/1916/`)
- **Platform-specific formatting**: 
  - Google feeds maintain XML namespaces (`g:`)
  - Facebook feeds use flat structure without namespaces
- **Price formatting**: 
  - Google: `380.50 MXN` format
  - Facebook: `$380,50` format (European style with comma as decimal separator)

### Enhanced Version (v2)
The `feed_processor_v2.py` adds:
- **Web scraping**: Uses Playwright to fetch additional product details from product pages
- **Enhanced descriptions**: Extracts `dataProd` JSON from product pages for richer metadata
- **Error page detection**: Identifies and excludes products with 404/error pages
- **Additional images**: Scrapes up to 5 product images per item
- **Detailed logging**: Comprehensive progress tracking and error reporting

### Feed Differences
When modifying feeds, maintain these platform-specific requirements:
- **Google**: Simple descriptions with period, namespace prefixes required
- **Facebook**: Enhanced descriptions with product details, no namespaces, strict field requirements

## GitHub Actions Automation

The workflow (`.github/workflows/generate-feeds.yml`) runs:
- Daily at 2 AM Mexico time (cron: `0 8 * * *`)
- On pushes to `main` branch
- Manual triggers via workflow_dispatch with optional `enable_scraping` parameter

When updating the workflow, ensure:
- Use `actions/upload-artifact@v4` (not v3 - deprecated)
- Python version matches local development (currently 3.10)
- Playwright browsers are installed for v2 processor
- GitHub Pages deployment is optional (controlled by conditional)
- Workflow has proper permissions set (`contents: write`, `pages: write`, `id-token: write`)
- 30-minute timeout for web scraping operations

### GitHub Pages Setup
If deployment fails with permission errors:
1. Ensure the workflow has the required permissions (already configured)
2. Enable GitHub Pages in repository Settings > Pages
3. Select "Deploy from a branch" and choose `gh-pages` branch
4. The workflow will create this branch automatically on first successful run

## Development Notes

- The project fetches live data from Accu-Chek's server - ensure the source URL remains accessible
- All generated files go to `output/` directory (gitignored)
- Price formatting must maintain 2 decimal places for both platforms
- Facebook requires specific fields: id, title, description, availability, condition, price, link, image_link, brand, gtin
- Web scraping (v2) respects 1-second delays between requests to avoid overwhelming the server
- Error pages are detected by checking for "Error 404" in page title or missing product data
- The `ENABLE_SCRAPING` environment variable controls whether to perform web scraping (default: true in GitHub Actions)

## Dependencies

- `requests`: HTTP requests for XML feed fetching
- `playwright`: Web scraping for enhanced product details (v2)
- `beautifulsoup4`: HTML parsing for scraped content
- `lxml`: XML parsing with namespace support
- `pydantic`: Data validation for structured product data