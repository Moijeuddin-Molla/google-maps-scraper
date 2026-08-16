import csv
import os
from datetime import datetime, timezone

def ensure_csv_header(filepath):
    if not os.path.exists(filepath):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['business_name', 'phone', 'address', 'google_maps_url', 'scraped_at'])

def append_lead(filepath, lead_data):
    with open(filepath, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            lead_data.get('business_name', 'N/A'),
            lead_data.get('phone', 'N/A'),
            lead_data.get('address', 'N/A'),
            lead_data.get('google_maps_url', 'N/A'),
            datetime.now(timezone.utc).isoformat()
        ])

def get_processed_urls(filepath):
    if not os.path.exists(filepath):
        return set()
    processed = set()
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_url = row.get('google_maps_url', '')
            if raw_url:
                # Strip the volatile '?' tracking parameters to create a stable dedup key
                stable_url = raw_url.split('?')[0]
                processed.add(stable_url)
    return processed