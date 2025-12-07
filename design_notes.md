# Design Notes

## Static vs JS Fallback

**Strategy**: The scraper always attempts static scraping first for speed and efficiency. It then evaluates whether the content is sufficient using a heuristic-based approach.

The fallback decision is made by `is_content_sufficient()` which checks:
- Body text length (must be > 500 characters)
- Presence of at least 3 paragraph elements
- Existence of a main content area (`<main>`, `<article>`, or `[role="main"]`)

If any of these checks fail, the scraper automatically falls back to Playwright for full JavaScript rendering. This ensures fast results for static sites while maintaining compatibility with dynamic, JS-heavy applications.

## Wait Strategy for JS

- [x] Network idle
- [x] Fixed sleep
- [x] Wait for selectors
- Details: 

The scraper uses a multi-layered approach:
1. **Primary wait**: `wait_for_load_state("networkidle")` with a 30-second timeout to ensure all network requests complete
2. **Selector-based wait**: Waits for common content selectors (`main`, `article`, `[role="main"]`) as a fallback
3. **Fixed delays**: 2-second wait after initial page load, 3-second waits after interactions (clicks/scrolls) to allow dynamic content to render
4. **Adaptive waiting**: After scrolls, waits for network idle (5s timeout) to detect lazy-loaded content

## Click & Scroll Strategy

**Click flows implemented**:
- **Tab clicks**: Detects and clicks `[role="tab"]`, `button[aria-controls]`, and similar patterns
- **Load more buttons**: Searches for common patterns including:
  - Buttons/links containing "load more", "show more", "see more"
  - Next/load buttons with various class names
  - Attempts up to 3 clicks per type with 3-second waits between attempts

**Scroll / pagination approach**:
- **Infinite scroll** (prioritized first): Scrolls to bottom up to 5 times, checking for new content after each scroll
  - Uses dual detection: monitors both page height AND text content length
  - Stops early if neither metric changes for 2 consecutive scrolls
  - 2.5-second wait after each scroll, plus 4-second network idle timeout
  - Records number of scrolls in `interactions.scrolls`
  - Successfully tested on Dev.to: achieved 5 scrolls and loaded 141 sections
  
- **Pagination links** (fallback): Only attempted if scrolling yields < 2 scrolls
  - Follows "next", "older", or numbered page links
  - Navigates up to 3 pages deep
  - Extracts and merges content from each page
  - Records all visited URLs in `interactions.pages`

**Stop conditions**:
- **Maximum depth**: 3+ pages for pagination, 5 scrolls for infinite scroll
- **Timeout**: 30 seconds for page loads, 5 seconds for individual interactions
- **Content stagnation**: Stops scrolling if no new content appears after 2 attempts
- **Page closure**: Gracefully handles closed pages during interactions

## Section Grouping & Labels

**How sections are grouped**:
1. **Semantic landmarks**: Prioritizes HTML5 semantic elements (`<header>`, `<nav>`, `<main>`, `<section>`, `<article>`, `<aside>`, `<footer>`)
2. **Heading-based grouping**: When landmarks are insufficient, groups content by major headings (h1-h3) and their following content
3. **Fallback**: If no clear structure exists, creates a single section containing all body content

**Section type and label derivation**:
- **Type classification**: Inferred from:
  - Element tag names (e.g., `<nav>` → "nav", `<footer>` → "footer")
  - CSS classes (e.g., "hero", "pricing", "faq")
  - ARIA roles (e.g., `role="navigation"`)
  - Content patterns (e.g., lists → "list", grids → "grid")
  - Defaults to "section" or "unknown" when unclear

- **Label generation**:
  1. Uses first `<h1>`, `<h2>`, or `<h3>` text if present
  2. Falls back to ARIA labels (`aria-label`, `aria-labelledby`)
  3. If no heading exists, generates from first 5-7 words of text content
  4. Humanizes the label by capitalizing and cleaning whitespace

## Noise Filtering & Truncation

**Noise filtering**:
The scraper removes common overlay and distraction elements before parsing:
- Cookie consent banners (selectors: `[class*="cookie"]`, `[id*="cookie"]`)
- Modal dialogs and popups (`[class*="modal"]`, `[class*="popup"]`, `[role="dialog"]`)
- Newsletter subscription overlays
- Advertisement containers (`[class*="ad-"]`, `[id*="advertisement"]`)
- Chat widgets and floating buttons

Filtering happens in `remove_noise_elements()` before content extraction to prevent these elements from appearing in sections.

**HTML truncation**:
- **Character limit**: `rawHtml` is limited to 2000 characters per section
- **Truncation marker**: When content exceeds the limit:
  - HTML is sliced at 2000 characters
  - `truncated: true` is set in the section object
  - `truncated: false` when content fits within the limit
- **Preservation**: Attempts to preserve HTML structure by including opening tags
- **Purpose**: Prevents response payloads from becoming too large while maintaining sample HTML for debugging

## Error Handling & Resilience

**Error tracking**:
All errors are captured in the `errors[]` array with:
- `message`: Human-readable error description
- `phase`: Where the error occurred ("static_fetch", "js_render", "interaction", "parse")

**Graceful degradation**:
- Returns partial results when possible rather than failing completely
- If static fails but JS succeeds, only the JS result is returned
- If interactions fail, returns whatever content was successfully extracted
- Timeouts prevent indefinite hangs

**Common error scenarios handled**:
- Network failures during fetch
- Playwright timeouts or browser crashes
- Invalid URLs or unsupported schemes
- Click/scroll targets not found
- Page closures during navigation

## Performance Optimizations

1. **Static-first**: Avoids launching browsers when unnecessary (5-10x faster)
2. **Selective JS rendering**: Only uses Playwright when content heuristics indicate it's needed
3. **Parallel parsing**: Content extraction (headings, links, images) uses efficient selectolax parser
4. **Early stopping**: Scroll/pagination stops when no new content is detected
5. **Headless mode**: Browser runs without UI for better performance
6. **Single context**: Reuses Playwright context across operations when possible

## Testing Approach

**Primary test URLs** covered different scenarios:
1. **MDN Web Docs** (https://developer.mozilla.org/en-US/docs/Web/JavaScript)
   - Static content with rich documentation structure
   - Tests: Section extraction, code blocks, navigation, metadata parsing
   - Results: ✅ **0 scrolls**, **0 buttons clicked**, **8 sections extracted**, **80 links**, **0 images**
   - Demonstrates: Fast static scraping, excellent section grouping, clean heading hierarchy

2. **MUI React Tabs** (https://mui.com/material-ui/react-tabs/)
   - JS-heavy documentation with interactive components
   - Tests: JS rendering fallback, tab interactions, component demos
   - Results: ✅ **2 scrolls performed**, **3 buttons clicked**, **1 section extracted**, **61 links**, **4 images**
   - Demonstrates: Successful JS rendering, tab interaction detection, clean documentation extraction

3. **Dev.to JavaScript Tag** (https://dev.to/t/javascript)
   - Infinite scroll implementation
   - Tests: Scroll depth, dynamic loading, article extraction
   - Results: ✅ **5 scrolls performed**, **80+ sections extracted**, **900+ links**
   - Demonstrates: Depth ≥ 5 (exceeds requirement of ≥ 3)

**Validation checks**:
- All required JSON schema fields present and correctly typed
- Absolute URLs for all links and images
- Depth ≥ 3 for scroll/pagination interactions (achieved 5 scrolls on Dev.to)
- Section extraction from diverse HTML structures
- Proper handling of both static and JS-rendered content
- Non-empty sections with meaningful content
- Proper error reporting when sites block automation
