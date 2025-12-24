import argparse
import sys
import os

# Ensure valid import path if running from subdir
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scrapers.aca import ACAScraper
from scrapers.osa import OSAScraper
from scrapers.lib import LibScraper
from scrapers.oga import OGAScraper
from scrapers.admin import AdminScraper

def main():
    parser = argparse.ArgumentParser(description="NTU Administrative Process Assistant - Scraper Manager")
    parser.add_argument("--dept", type=str, default="all", help="Target department (aca, osa, lib, oga, admin, or all)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to scrape (for testing)")
    args = parser.parse_args()

    scrapers = []
    
    # Register scrapers here
    if args.dept in ["aca", "all"]:
        scrapers.append(ACAScraper())
    
    if args.dept in ["osa", "all"]:
        scrapers.append(OSAScraper())
        
    if args.dept in ["lib", "all"]:
        scrapers.append(LibScraper())

    if args.dept in ["oga", "all"]:
        scrapers.append(OGAScraper())
    
    if args.dept in ["admin", "all"]:
        scrapers.append(AdminScraper())

    if not scrapers:
        print(f"No scrapers found for department: {args.dept}")
        return

    print(f"Starting scrapers for: {[s.department for s in scrapers]}")
    for scraper in scrapers:
        try:
            scraper.run(max_items=args.limit)
        except Exception as e:
            print(f"[CRITICAL] Scraper {scraper.department} failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
