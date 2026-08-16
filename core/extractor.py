import asyncio
import random
import re
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

async def human_pause(min_sec, max_sec):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def check_for_website(page, config):
    selectors = config['selectors']
    delays = config['delays']
    website_locator = page.locator(selectors['website_primary']).or_(page.locator(selectors['website_fallback']))
    try:
        await website_locator.first.wait_for(state="visible", timeout=delays['website_check_timeout_ms'])
        return True 
    except PlaywrightTimeoutError:
        return False 

async def extract_field(page, selector):
    try:
        locator = page.locator(selector).last
        await locator.wait_for(state="attached", timeout=2000)
        text = await locator.inner_text()
        return text.split('\n')[-1].strip() if text else "N/A"
    except Exception:
        return "N/A"

async def extract_rating(page, selector):
    """Extracts the numerical rating from the aria-label."""
    try:
        locator = page.locator(selector).first
        await locator.wait_for(state="attached", timeout=2000)
        label = await locator.get_attribute("aria-label")
        if label:
            # Uses regex to find the first decimal number in the label (e.g., "4.5")
            match = re.search(r"([0-9.]+)", label)
            if match:
                return float(match.group(1))
        return 0.0
    except Exception:
        return 0.0

async def scroll_feed(page, config):
    feed_selector = config['selectors']['feed_panel']
    card_selector = config['selectors']['business_card']
    feed = page.locator(feed_selector)
    await feed.wait_for(state="attached")
    box = await feed.bounding_box()
    
    if box:
        await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    
    previous_count = 0
    attempts = 0
    while attempts < config['limits']['scroll_attempts']:
        current_count = await page.locator(card_selector).count()
        if current_count >= config['limits']['max_results']:
            break
        if current_count > previous_count:
            previous_count = current_count
            attempts = 0 
        else:
            attempts += 1
        await page.mouse.wheel(0, random.uniform(600, 1100))
        await human_pause(config['delays']['min_pause_sec'], config['delays']['max_pause_sec'])
    
    return await page.locator(card_selector).element_handles()