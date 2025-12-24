from typing import List, Dict, Tuple
from urllib.parse import urljoin
import time
from .base import BaseScraper, sync_playwright

class ACAScraper(BaseScraper):
    def __init__(self):
        super().__init__(department="aca")
        self.listing_pages = [
            "https://www.aca.ntu.edu.tw/w/aca/FolksonomyCurrentStudent?folksonomyTypeId=21082908254338056&index=1",
            "https://www.aca.ntu.edu.tw/w/aca/FolksonomyCurrentStudent?folksonomyTypeId=21082908254338056&index=2",
        ]

    def fetch_links(self) -> List[Dict[str, str]]:
        """
        Discover links from ACA listing pages using Playwright (since they are dynamic).
        """
        discovered_links = []
        
        # ACA listing pages need playwright
        if not sync_playwright:
            print("[ACA] Playwright not available, cannot fetch dynamic link lists.")
            return []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for url in self.listing_pages:
                print(f"[ACA] Scanning listing page: {url}")
                try:
                    page = browser.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except:
                        pass
                    
                    time.sleep(self.wait_after_load) # Wait for JS

                    # Extract links with class 'title'
                    # JS: Array.from(document.querySelectorAll('a.title')).map(a => ({text: a.innerText, href: a.href}))
                    links_data = page.evaluate("""
                        () => Array.from(document.querySelectorAll('a.title')).map(a => ({
                            title: a.innerText.trim(),
                            href: a.getAttribute('href')
                        }))
                    """)
                    
                    for item in links_data:
                        title = item.get("title", "")
                        href = item.get("href", "")
                        
                        if not title or not href:
                            continue

                        # Construct full URL
                        if href.startswith("/"):
                            full_url = f"https://www.aca.ntu.edu.tw{href}"
                        elif href.startswith("http"):
                            full_url = href
                        else:
                            full_url = urljoin("https://www.aca.ntu.edu.tw/w/aca/", href)
                            
                        discovered_links.append({
                            "title": title,
                            "url": full_url,
                            "category": "Bachelor" # Default category for these pages
                        })
                        
                except Exception as e:
                    print(f"[Error] Failed to scrape listing page {url}: {e}")
                finally:
                    page.close()
            
            browser.close()

        # Remove duplicates based on URL
        unique_links = []
        seen_urls = set()
        for link in discovered_links:
            if link["url"] not in seen_urls:
                unique_links.append(link)
                seen_urls.add(link["url"])
                
        return unique_links
