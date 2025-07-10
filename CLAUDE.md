# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FeedXML-MX is a Python-based XML feed processor for Accu-Chek Mexico's e-commerce platform. It fetches product data from `https://tienda.accu-chek.com.mx/Main/FeedXML` and generates two optimized feeds:
- Google Merchant Center feed with `g:` namespace
- Facebook Catalog feed with flat structure

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run feed processor locally
python feed_processor.py

# Output files will be generated in:
# - output/feed_google.xml
# - output/feed_facebook.xml
# - output/metadata.json
```

## Architecture & Key Components

### Core Processing Logic
The `FeedProcessor` class in `feed_processor.py` handles all transformations:
- **URL Cleaning**: Strips product titles from URLs (e.g., `/Main/Producto/1916/50-Tiras-Reactivas...` → `/Main/Producto/1916/`)
- **Platform-specific formatting**: 
  - Google feeds maintain XML namespaces (`g:`)
  - Facebook feeds use flat structure without namespaces
- **Description enhancement**: Facebook gets detailed descriptions based on product type (tiras reactivas, lancetas, kits)

### Feed Differences
When modifying feeds, maintain these platform-specific requirements:
- **Google**: Simple descriptions with period, namespace prefixes required
- **Facebook**: Enhanced descriptions with product details, no namespaces, strict field requirements

## GitHub Actions Automation

The workflow (`.github/workflows/generate-feeds.yml`) runs:
- Daily at 2 AM Mexico time (cron: `0 8 * * *`)
- On pushes to `main` branch
- Manual triggers via workflow_dispatch

When updating the workflow, ensure:
- Use `actions/upload-artifact@v4` (not v3 - deprecated)
- Python version matches local development (currently 3.10)
- GitHub Pages deployment is optional (controlled by conditional)
- Workflow has proper permissions set (`contents: write`, `pages: write`, `id-token: write`)

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