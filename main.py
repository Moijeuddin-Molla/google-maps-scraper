import asyncio
import yaml
import sys
import logging
import time
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from data.storage import ensure_csv_header, append_lead, get_processed_urls
from core.extractor import human_pause, check_for_website, extract_field, extract_rating, scroll_feed

log_filename = f"logs/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def run_scraper():
    start_time = time.time()
    with open("config/settings.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    query = config['queries'][0] 
    csv_path = config['output']['csv_path']
    delays = config['delays']
    selectors = config['selectors']
    filters = config['filters']
    max_results = config['limits']['max_results']
    
    ensure_csv_header(csv_path)
    processed_urls = get_processed_urls(csv_path)
    logger.info(f"Checkpoint loaded: {len(processed_urls)} leads already processed.")
    
    metrics = {'candidates_seen': 0, 'leads_captured': 0, 'failures': 0, 'skipped_filters': 0}
    circuit_breaker_errors = 0
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(viewport={"width": 1440, "height": 900}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
        await Stealth().apply_stealth_async(context)
        page = await context.new_page()

        try:
            await page.goto("https://www.google.com/maps?hl=en")
            await human_pause(delays['min_pause_sec'], delays['max_pause_sec'])
            
            await page.fill('input[name="q"]', query)
            await page.press('input[name="q"]', 'Enter')
            logger.info(f"Searching for: '{query}'...")
            
            await page.wait_for_selector(selectors['feed_panel'], timeout=15000)
            await human_pause(delays['min_pause_sec'], delays['max_pause_sec'])
            
            cards = await scroll_feed(page, config)
            logger.info(f"Feed scroll complete. Found {len(cards)} total cards.")
            
            for i, card in enumerate(cards):
                if circuit_breaker_errors >= 5:
                    logger.error("Circuit breaker triggered! Halting run.")
                    break
                if i >= max_results:
                    break

                metrics['candidates_seen'] += 1
                try:
                    await card.scroll_into_view_if_needed()
                    await card.click()
                    await human_pause(delays['min_pause_sec'], delays['max_pause_sec'])
                    
                    current_url = page.url
                    stable_url = current_url.split('?')[0]
                    if stable_url in processed_urls:
                        continue # Silently skip duplicates to keep logs clean

                    has_website = await check_for_website(page, config)
                    rating = await extract_rating(page, selectors['rating'])
                    
                    # --- NEW FILTER LOGIC ---
                    skip = False
                    if filters['target_website_status'] == "no_website" and has_website:
                        skip = True
                    elif filters['target_website_status'] == "has_website" and not has_website:
                        skip = True
                        
                    if rating < filters['min_rating']:
                        skip = True
                        
                    if skip:
                        logger.info(f"Card {i+1} skipped due to filter settings (Rating: {rating}, Has Web: {has_website}).")
                        processed_urls.add(stable_url)
                        metrics['skipped_filters'] += 1
                        continue
                    # -------------------------
                        
                    logger.info(f"Card {i+1} matched filters! Extracting...")
                    lead_data = {
                        'business_name': await extract_field(page, selectors['business_name']),
                        'phone': await extract_field(page, selectors['phone']),
                        'address': await extract_field(page, selectors['address']),
                        'google_maps_url': current_url 
                    }
                    
                    if not lead_data['business_name'] or lead_data['business_name'] == 'N/A':
                        circuit_breaker_errors += 1
                        continue
                        
                    if lead_data['phone'] != 'N/A' and len(lead_data['phone']) < 6:
                        lead_data['phone'] = 'N/A'

                    logger.info(f"Captured: {lead_data['business_name']} ({rating} stars)")
                    append_lead(csv_path, lead_data)
                    processed_urls.add(stable_url)
                    metrics['leads_captured'] += 1
                    circuit_breaker_errors = 0
                    
                except Exception as e:
                    logger.error(f"Error processing card {i+1}: {str(e)}")
                    circuit_breaker_errors += 1
                    metrics['failures'] += 1
        
        except KeyboardInterrupt:
            logger.warning("Run manually interrupted! Progress saved.")
        finally:
            await browser.close()
            logger.info(f"\n=== RUN SUMMARY ===\nQuery: {query}\nLeads Captured: {metrics['leads_captured']}\nSkipped (Filters): {metrics['skipped_filters']}\nFailures: {metrics['failures']}\nTime: {time.time() - start_time:.2f}s\n===================")

if __name__ == "__main__":
    try:
        asyncio.run(run_scraper())
    except KeyboardInterrupt:
        sys.exit(0)