# Universal Website Scraper

**Lyftr AI — Full-stack Assignment Submission**

A full-stack web scraping application that handles both static and JavaScript-rendered websites with intelligent fallback strategies, click flows, and pagination support.

## Overview

This is an MVP universal website scraper that:
- Scrapes both static and JS-rendered content
- Performs click flows (tabs, "Load more" buttons)
- Supports scroll/pagination to depth ≥ 3
- Returns section-aware JSON following the specified schema
- Provides a frontend to input URLs and view/download JSON results

## Tech Stack

- **Language**: Python 3.13 (compatible with 3.10+)
- **Backend**: FastAPI
- **HTML Parsing**: 
  - Static: `httpx` + `selectolax`
  - JS: `playwright`
- **Frontend**: Jinja2 template (rendered by backend)
- **Server**: uvicorn

## Setup and Run

### Quick Start

```bash
chmod +x run.sh
./run.sh
```

This will:
1. Create/activate a virtual environment
2. Install all dependencies from `requirements.txt`
3. Install Playwright Chromium browser
4. Start the server on `http://localhost:8000`

### Manual Setup (if needed)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Project Structure

```
lyfterAI/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application & endpoints
│   ├── scraper.py       # Core scraping logic (static + JS)
│   ├── parser.py        # HTML parsing & section extraction
│   └── template/
│       └── index.html   # Frontend UI
├── run.sh               # Setup and run script
├── requirements.txt     # Python dependencies
├── capabilities.json    # Feature implementation checklist
├── design_notes.md      # Design decisions and strategies
└── README.md           # This file
```

## API Endpoints

### GET /healthz
Health check endpoint.

**Response:**
```json
{
  "status": "ok"
}
```

### POST /scrape
Scrape a website and return structured JSON.

**Request:**
```json
{
  "url": "https://example.com"
}
```

**Response:**
```json
{
  "result": {
    "url": "https://example.com",
    "scrapedAt": "2025-12-07T00:00:00Z",
    "meta": {
      "title": "Page Title",
      "description": "Meta description",
      "language": "en",
      "canonical": "https://example.com"
    },
    "sections": [...],
    "interactions": {
      "clicks": ["selector1", "selector2"],
      "scrolls": 3,
      "pages": ["url1", "url2", "url3"]
    },
    "errors": []
  }
}
```

**Example Response Screenshot:**

![Scraping Results Example](1.png)
![Scraping Results Example](2.png)

### GET /
Serves the frontend interface for interactive scraping.

## Test URLs

The following URLs were used for primary testing:

1. **https://developer.mozilla.org/en-US/docs/Web/JavaScript**
   - Type: Primarily static content with rich documentation
   - Tests: Static HTML parsing, section extraction, code blocks, navigation
   - Features: Multiple sections with headings, code examples, lists, and comprehensive documentation structure

2. **https://mui.com/material-ui/react-tabs/**
   - Type: JS-heavy documentation with interactive tab components
   - Tests: JS rendering, tab interactions, component demos
   - Features: Interactive React components, tab navigation, requires JavaScript to render properly

3. **https://dev.to/t/javascript**
   - Type: JS-rendered with infinite scroll
   - Tests: Infinite scroll handling, dynamic content loading, scroll depth ≥ 5
   - Features: Loads more articles as you scroll, achieved 141 sections and 5 scrolls, demonstrates deep pagination

## Features

### Implemented Capabilities

✅ **Static Scraping**
- Fetches HTML with `httpx`
- Parses with `selectolax` for performance
- Extracts metadata, sections, links, images, lists, tables

✅ **JS Rendering**
- Automatic fallback to Playwright when static content is insufficient
- Waits for network idle and key selectors
- Handles dynamic content loading

✅ **Click Flows**
- Tab clicks: `[role="tab"]`, `button[aria-controls]`
- Load more buttons: Various selectors for common patterns
- Records all click attempts in `interactions.clicks`

✅ **Scroll & Pagination**
- Infinite scroll: Scrolls up to 5 times with content detection
- Pagination links: Follows "next" links up to 3+ pages
- Records depth in `interactions.scrolls` and `interactions.pages`

✅ **Section Extraction**
- Groups content by semantic HTML landmarks
- Generates intelligent labels from headings or first words
- Classifies sections by type (hero, nav, footer, etc.)

✅ **Noise Filtering**
- Filters cookie banners, modals, and overlays
- Removes common noise elements before parsing

✅ **HTML Truncation**
- Limits `rawHtml` to 2000 characters per section
- Sets `truncated: true` when content is cut

## Key Implementation Details

### Static vs JS Fallback Strategy
1. Always attempt static scraping first (faster, less resource-intensive)
2. Check if content is sufficient using heuristics:
   - Body text length > 500 characters
   - At least 3 paragraphs present
   - Main content area exists
3. If insufficient, automatically fall back to Playwright for JS rendering

### Wait Strategy for JS
- Primary: `wait_for_load_state("networkidle")` with 30s timeout
- Fallback: Wait for common selectors (`main`, `article`, `[role="main"]`)
- Additional: Fixed 2s wait after page load for dynamic content
- Post-interaction: 3s wait after clicks/scrolls for content to load

### Section Grouping
- Uses semantic HTML5 landmarks: `<header>`, `<nav>`, `<main>`, `<section>`, `<article>`, `<footer>`
- Falls back to heading-based grouping (h1-h3) when landmarks are insufficient
- Each section gets a unique ID and appropriate type classification

### Error Handling
- Graceful degradation: Returns partial data when possible
- Comprehensive error tracking in `errors[]` array
- Timeouts prevent infinite hanging (30s for page load, 5s for interactions)

## Codebase Overview

### `app/main.py`
FastAPI application with:
- Health check endpoint (`/healthz`)
- Scraping endpoint (`/scrape`)
- Frontend serving (`/`)
- Request validation with custom error handling
- CORS middleware for cross-origin requests

### `app/scraper.py`
Core scraping engine:
- `scrape_website()`: Main orchestrator
- `fetch_static()`: Static HTML fetching with httpx
- `is_content_sufficient()`: Heuristic for JS fallback decision
- `scrape_with_playwright()`: Full Playwright automation
- `handle_click_flows()`: Tab and button clicking
- `handle_infinite_scroll()`: Scroll detection and loading
- `handle_pagination()`: Next link navigation

### `app/parser.py`
HTML parsing and structure extraction:
- `HTMLContentParser`: Main parser class
- `extract_meta()`: Metadata extraction (title, description, etc.)
- `extract_sections()`: Section grouping and classification
- `_parse_section()`: Individual section content extraction
- `_extract_content()`: Headings, text, links, images, lists, tables
- `_classify_section_type()`: Type inference from HTML structure
- `_generate_label()`: Smart label generation

### `app/template/index.html`
Frontend interface:
- URL input form with validation
- Real-time scraping with loading states
- Expandable section viewer with syntax highlighting
- JSON download functionality
- Dark mode toggle
- Responsive design

## Known Limitations

1. **Rate Limiting**: No built-in rate limiting; aggressive use may trigger site defenses
2. **CAPTCHA**: Cannot bypass CAPTCHA or advanced bot detection
3. **Authentication**: Does not handle login-required content
4. **Bot Protection**: Sites with anti-scraping protection may block or return limited content:
   - LinkedIn, Facebook, Twitter/X - Aggressive bot 
5. **Large Pages**: Very large pages (>10MB) may cause memory issues
6. **Complex SPAs**: Some heavily React/Vue apps may not fully render
7. **Same-Origin**: Optimized for single-domain scraping; cross-domain links are recorded but not followed
8. **Dynamic Interactions**: Only handles common patterns (tabs, load more, scroll); custom interactions may be missed

## Dependencies

See `requirements.txt` for full list. Key dependencies:
- `fastapi==0.115.5` - Web framework
- `uvicorn==0.32.1` - ASGI server
- `httpx==0.27.2` - HTTP client
- `selectolax==0.3.24` - Fast HTML parser
- `playwright==1.49.1` - Browser automation
- `jinja2==3.1.4` - Template engine

## Environment

- Tested on: macOS 15.0 (ARM64)
- Python: 3.13.5 (compatible with 3.10+)
- Browser: Chromium via Playwright

## Design Philosophy

This scraper prioritizes:
1. **Speed**: Static-first approach for fast results
2. **Robustness**: Automatic JS fallback when needed
3. **Completeness**: Deep navigation with scroll/pagination
4. **Structure**: Semantic section extraction
5. **Usability**: Clean frontend with immediate feedback

See `design_notes.md` for detailed design decisions.
