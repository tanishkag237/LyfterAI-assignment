from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import httpx
from app.parser import HTMLContentParser
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def scrape_website(url: str) -> dict:
    """
    Main scraping function that tries static first, then falls back to JS rendering
    """
    
    result = {
        "url": url,
        "scrapedAt": datetime.utcnow().isoformat() + "Z",
        "meta": {},
        "sections": [],
        "interactions": {
            "clicks": [],
            "scrolls": 0,
            "pages": [url]
        },
        "errors": []
    }
    
    # Try static scraping first
    logger.info(f"Attempting static scrape for: {url}")
    try:
        html = await fetch_static(url)
        
        if is_content_sufficient(html):
            logger.info("Static content appears sufficient")
            parser = HTMLContentParser(html, url)
            result["meta"] = parser.extract_meta()
            result["sections"] = parser.extract_sections()
            return result
        else:
            logger.info("Static content insufficient, falling back to JS rendering")
    except Exception as e:
        logger.warning(f"Static scrape failed: {e}")
        result["errors"].append({
            "message": str(e),
            "phase": "static_fetch"
        })
    
    # Fallback to Playwright for JS rendering
    try:
        logger.info("Starting Playwright scrape")
        playwright_result = await scrape_with_playwright(url)
        
        # Merge results
        result["meta"] = playwright_result.get("meta", {})
        result["sections"] = playwright_result.get("sections", [])
        result["interactions"] = playwright_result.get("interactions", result["interactions"])
        result["errors"].extend(playwright_result.get("errors", []))
        
    except Exception as e:
        logger.error(f"Playwright scrape failed: {e}", exc_info=True)
        result["errors"].append({
            "message": str(e),
            "phase": "js_render"
        })
    
    return result


async def fetch_static(url: str) -> str:
    """Fetch HTML using httpx for static pages"""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                url,
                timeout=15.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as e:
        if e.response.status_code in [403, 401, 429]:
            raise Exception("Access denied. This site may be blocking automated access or requires authentication.")
        raise
    except httpx.ConnectTimeout:
        raise Exception("Connection timed out. The site may be blocking automated access.")
    except Exception as e:
        raise Exception(f"Failed to fetch page: {str(e)}")


def is_content_sufficient(html: str) -> bool:
    """
    Heuristic to check if static HTML has enough content
    Returns False if we should use JS rendering
    """
    # Check for common JS framework indicators
    js_frameworks = [
        'react',
        'vue',
        'angular',
        'next.js',
        '__NEXT_DATA__',
        'ng-app',
        'data-reactroot'
    ]
    
    html_lower = html.lower()
    
    # If it's a JS-heavy framework, use Playwright
    for framework in js_frameworks:
        if framework in html_lower:
            return False
    
    # Check if there's minimal actual content
    # Look for main content indicators
    if '<main' not in html_lower and '<article' not in html_lower:
        # Might be JS-rendered
        if '<div id="root"' in html_lower or '<div id="app"' in html_lower:
            return False
    
    # Check text content length (rough heuristic)
    # Remove scripts and styles
    import re
    text_only = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text_only = re.sub(r'<style[^>]*>.*?</style>', '', text_only, flags=re.DOTALL | re.IGNORECASE)
    text_only = re.sub(r'<[^>]+>', '', text_only)
    
    # If there's enough text content, consider it sufficient
    return len(text_only.strip()) > 500


async def scrape_with_playwright(url: str) -> dict:
    """
    Scrape with Playwright for JS-rendered content
    Includes click flows, scrolling, and pagination
    """
    result = {
        "meta": {},
        "sections": [],
        "interactions": {
            "clicks": [],
            "scrolls": 0,
            "pages": [url]
        },
        "errors": []
    }
    
    browser = None
    context = None
    page = None
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True
            )
            
            # Add extra headers
            await context.set_extra_http_headers({
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            page = await context.new_page()
            
            # Set longer timeout
            page.set_default_timeout(45000)  # 45 seconds
            
            try:
                # Navigate to page
                logger.info(f"Navigating to {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as nav_error:
                    error_msg = str(nav_error).lower()
                    if "net::err_aborted" in error_msg or "ns_binding_aborted" in error_msg:
                        raise Exception("Browser or page closed unexpectedly. This site may be blocking automated access or has protection mechanisms.")
                    raise
                
                # Wait a bit for initial JS execution
                await page.wait_for_timeout(3000)
                
                # Check if page is still alive
                if page.is_closed():
                    raise Exception("Browser or page closed unexpectedly. This site may be blocking automated access or has protection mechanisms.")
                
                # Dismiss cookie banners and overlays
                await dismiss_overlays(page, result)
                
                # Try clicking tabs
                await handle_tabs(page, result)
                
                # Try "Load more" buttons
                await handle_load_more(page, result)
                
                # Handle scrolling or pagination
                await handle_scroll_or_pagination(page, result, url)
                
                # Extract final HTML
                if not page.is_closed():
                    html = await page.content()
                    current_url = page.url
                    
                    # Parse the content
                    parser = HTMLContentParser(html, current_url)
                    result["meta"] = parser.extract_meta()
                    result["sections"] = parser.extract_sections()
                    
                    logger.info(f"Successfully scraped {len(result['sections'])} sections")
                else:
                    raise Exception("Browser or page closed unexpectedly. This site may be blocking automated access or has protection mechanisms.")
                
            except PlaywrightTimeout as e:
                logger.error(f"Timeout during scrape: {e}")
                error_msg = str(e).lower()
                if "navigation" in error_msg or "goto" in error_msg:
                    result["errors"].append({
                        "message": "Page timed out while loading. This site may be blocking automated access, requires authentication, or is very slow.",
                        "phase": "navigation"
                    })
                else:
                    result["errors"].append({
                        "message": f"Page timed out while loading. The site may be blocking automation or is very slow.",
                        "phase": "navigation"
                    })
                # Try to get partial content
                try:
                    if page and not page.is_closed():
                        html = await page.content()
                        parser = HTMLContentParser(html, url)
                        result["meta"] = parser.extract_meta()
                        result["sections"] = parser.extract_sections()
                except Exception as inner_e:
                    logger.error(f"Failed to get partial content: {inner_e}")
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error during Playwright scrape: {error_msg}", exc_info=True)
                
                # Provide more helpful error messages
                if "closed" in error_msg.lower():
                    result["errors"].append({
                        "message": "Browser or page closed unexpectedly. This site may be blocking automated access or has protection mechanisms.",
                        "phase": "scraping"
                    })
                else:
                    result["errors"].append({
                        "message": error_msg,
                        "phase": "scraping"
                    })
                    
                # Try to get whatever content we can
                try:
                    if page and not page.is_closed():
                        html = await page.content()
                        parser = HTMLContentParser(html, url)
                        result["meta"] = parser.extract_meta()
                        result["sections"] = parser.extract_sections()
                except:
                    pass
                    
            finally:
                # Safely close resources
                try:
                    if page and not page.is_closed():
                        await page.close()
                except:
                    pass
                    
                try:
                    if context:
                        await context.close()
                except:
                    pass
                    
                try:
                    if browser:
                        await browser.close()
                except:
                    pass
                
    except Exception as e:
        logger.error(f"Error initializing Playwright: {e}", exc_info=True)
        result["errors"].append({
            "message": f"Failed to initialize browser: {str(e)}",
            "phase": "initialization"
        })
    
    return result


async def dismiss_overlays(page, result: dict):
    """Dismiss cookie banners and other overlays"""
    overlay_selectors = [
        'button:has-text("Accept")',
        'button:has-text("Accept All")',
        'button:has-text("Accept all")',
        'button:has-text("I accept")',
        'button:has-text("Agree")',
        'button:has-text("OK")',
        'button:has-text("Got it")',
        'button:has-text("Close")',
        '[aria-label*="accept" i]',
        '[aria-label*="cookie" i] button',
        '[class*="cookie" i] button',
        '[id*="cookie" i] button',
        '[class*="consent" i] button',
        '[id*="consent" i] button',
        '.modal-close',
        '[aria-label="Close"]',
        '[data-testid*="accept" i]',
        '[data-testid*="cookie" i]'
    ]
    
    # Try multiple times as overlays can be lazy-loaded
    for attempt in range(2):
        for selector in overlay_selectors:
            try:
                button = page.locator(selector).first
                if await button.count() > 0 and await button.is_visible(timeout=1000):
                    await button.click(timeout=2000)
                    result["interactions"]["clicks"].append(f"overlay: {selector}")
                    await page.wait_for_timeout(1000)
                    logger.info(f"Dismissed overlay: {selector}")
                    return  # Exit after first successful dismissal
            except:
                pass
        
        # Wait a bit before trying again
        if attempt == 0:
            await page.wait_for_timeout(2000)


async def handle_tabs(page, result: dict):
    """Try to click through tabs to load more content"""
    tab_selectors = [
        '[role="tab"]',
        'button[aria-selected]',
        '.tab',
        '[data-tab]'
    ]
    
    for selector in tab_selectors:
        try:
            tabs = page.locator(selector)
            count = await tabs.count()
            
            if count > 1:
                logger.info(f"Found {count} tabs with selector: {selector}")
                # Click first 3 tabs
                for i in range(min(3, count)):
                    try:
                        await tabs.nth(i).click(timeout=3000)
                        result["interactions"]["clicks"].append(f"tab: {selector}[{i}]")
                        await page.wait_for_timeout(1000)
                    except:
                        pass
                break
        except:
            pass


async def handle_load_more(page, result: dict):
    """Click 'Load more' or 'Show more' buttons"""
    load_more_selectors = [
        'button:has-text("Load more")',
        'button:has-text("Show more")',
        'button:has-text("See more")',
        'a:has-text("Load more")',
        '[class*="load-more" i]',
        '[class*="show-more" i]'
    ]
    
    max_clicks = 3
    clicks = 0
    
    for selector in load_more_selectors:
        while clicks < max_clicks:
            try:
                button = page.locator(selector).first
                if await button.count() > 0 and await button.is_visible():
                    await button.click(timeout=3000)
                    result["interactions"]["clicks"].append(f"load-more: {selector}")
                    clicks += 1
                    await page.wait_for_timeout(2000)
                    logger.info(f"Clicked 'Load more' button ({clicks}/{max_clicks})")
                else:
                    break
            except:
                break


async def handle_scroll_or_pagination(page, result: dict, base_url: str):
    """
    Handle infinite scroll OR pagination links
    Aim for depth >= 3
    """
    # Always try infinite scroll first (more common for modern sites)
    await handle_infinite_scroll(page, result)
    
    # If scrolling didn't work well, try pagination
    if result["interactions"]["scrolls"] < 2:
        await handle_pagination(page, result, base_url)


async def handle_pagination(page, result: dict, base_url: str) -> bool:
    """
    Follow pagination links (depth >= 3)
    Returns True if pagination was handled
    """
    next_selectors = [
        'a:has-text("Next")',
        'a:has-text(">")',
        '[aria-label*="next" i]',
        'a[rel="next"]',
        '.pagination a:last-child',
        '.next'
    ]
    
    max_pages = 3
    pages_visited = 1
    
    for page_num in range(2, max_pages + 1):
        found_next = False
        
        for selector in next_selectors:
            try:
                next_link = page.locator(selector).first
                if await next_link.count() > 0 and await next_link.is_visible():
                    # Click the next link
                    await next_link.click(timeout=5000)
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    
                    new_url = page.url
                    result["interactions"]["pages"].append(new_url)
                    pages_visited += 1
                    found_next = True
                    
                    logger.info(f"Navigated to page {page_num}: {new_url}")
                    await page.wait_for_timeout(1000)
                    break
            except Exception as e:
                logger.debug(f"Pagination click failed for {selector}: {e}")
                continue
        
        if not found_next:
            break
    
    return pages_visited > 1


async def handle_infinite_scroll(page, result: dict):
    """Handle infinite scroll (scroll at least 3 times)"""
    max_scrolls = 5
    consecutive_no_change = 0
    max_no_change = 2  # Stop after 2 scrolls with no new content
    
    for i in range(max_scrolls):
        try:
            # Check if page is still alive
            if page.is_closed():
                break
            
            # Get current content markers (more reliable than just height)
            previous_height = await page.evaluate("document.body.scrollHeight")
            previous_content = await page.evaluate("document.body.innerText.length")
            
            # Scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            result["interactions"]["scrolls"] += 1
            
            # Wait for content to load
            await page.wait_for_timeout(2500)
            
            # Check if page is still alive
            if page.is_closed():
                break
            
            # Try to wait for network idle
            try:
                await page.wait_for_load_state("networkidle", timeout=4000)
            except:
                pass
            
            # Check if new content loaded (check both height and content length)
            if not page.is_closed():
                new_height = await page.evaluate("document.body.scrollHeight")
                new_content = await page.evaluate("document.body.innerText.length")
                
                height_changed = new_height > previous_height
                content_changed = new_content > previous_content
                
                # If either metric shows change, we got new content
                if height_changed or content_changed:
                    consecutive_no_change = 0
                else:
                    consecutive_no_change += 1
                    if consecutive_no_change >= max_no_change:
                        break
            else:
                break
                
        except Exception as e:
            break