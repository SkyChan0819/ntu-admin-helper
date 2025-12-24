import os
import json
import csv
import time
import requests
from typing import List, Dict, Optional, Tuple, Any
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Try importing playwright, but allow running without it (requests only mode)
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

class BaseScraper:
    def __init__(self, department: str, output_dir: str = "data"):
        self.department = department
        self.output_dir = output_dir
        # Output will be in data/{department}/
        self.base_output_path = os.path.join(output_dir, department)
        
        # Ensure output directory exists
        os.makedirs(self.base_output_path, exist_ok=True)
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        }
        self.wait_after_load = 2.0  # Seconds to wait for dynamic content

    def fetch_links(self) -> List[Dict[str, str]]:
        """
        Abstract method to be implemented by child classes.
        Should return a list of dicts. 
        Example structure: 
        [
            {"title": "Service 1", "url": "http://...", "category": "optional"},
            ...
        ]
        """
        raise NotImplementedError("Subclasses must implement fetch_links")

    def clean_text(self, text: str) -> str:
        """Normalize whitespace."""
        return " ".join(text.split())

    def pick_main_text_from_soup(self, soup: BeautifulSoup) -> str:
        """
        Extract the main content from the page, filtering out navigation, headers, footers, etc.
        """
        # 1. Remove noise elements (styles, scripts, forms, etc.)
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "iframe"]):
            tag.decompose()

        # 2. Remove common layout containers by class name
        # Expanded list based on user feedback about "headings" and unrelated content
        noise_classes = [
            "breadcrumb", "breadcrumbs", "menu", "navbar", "sidebar", 
            "header", "footer", "search", "widget", "related", "share", 
            "language", "accessibility", "cookie", "banner"
        ]
        for cls in noise_classes:
            for tag in soup.select(f".{cls}"):
                tag.decompose()

        # 3. Prioritize specific content containers
        # These are common selectors found in NTU websites (aca, osa, etc.)
        candidates_priority = [
            ".content_txt",
            ".ContentPlaceHolder_txt",
            "div[class*='ContentPlaceHolder']",
            ".card-box",      # ACA style
            ".card-text",     # ACA style
            "#pc-article",    # OSA style
            ".list-content",  # OSA style
            ".article-font",  # OSA style
            ".page-article",  # OGA style
            ".faq_section",   # OGA style
            ".faq_list",      # OGA style
            "main",
            "[role='main']",
            "article",
            "div.mainContent",
            "div#main",
            ".parallax-text-content",
            ".tr", 
        ]

        # Try to find the best candidate container
        best_text = ""
        for sel in candidates_priority:
            for tag in soup.select(sel):
                text = self.clean_text(tag.get_text(separator=" ", strip=True))
                # Simple heuristic: meaningful content is usually between 50 and 20000 chars
                # and we want the *longest* valid candidate usually
                if 50 < len(text) < 30000:
                    if len(text) > len(best_text):
                        best_text = text
        
        if best_text:
            return best_text

        # 4. Fallback: Find the longest div that doesn't look like navigation
        longest_text = ""
        for div in soup.find_all("div"):
            # Check classes to avoid
            cls = " ".join(div.get("class", [])).lower()
            if any(skip in cls for skip in ["nav", "menu", "header", "footer", "breadcrumb", "sidebar", "noprint", "button", "hidden"]):
                continue
            
            text = self.clean_text(div.get_text(separator=" ", strip=True))
            if 50 < len(text) < 30000 and len(text) > len(longest_text):
                longest_text = text

        return longest_text

    def extract_with_requests(self, url: str) -> Dict[str, Any]:
        """Attempt to extract content using static Requests."""
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.encoding = resp.apparent_encoding  # Handle encoding automatically
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract Description from Meta tags
            desc = ""
            meta_desc = soup.find("meta", {"name": "description"})
            if meta_desc and meta_desc.get("content"):
                desc = meta_desc.get("content").strip()
            
            if not desc:
                og_desc = soup.find("meta", {"property": "og:description"})
                if og_desc and og_desc.get("content"):
                    desc = og_desc.get("content").strip()

            content = self.pick_main_text_from_soup(soup)

            return {
                "success": True,
                "description": desc,
                "content": content,
                "url": url,
                "_length": len(content)
            }
        except Exception as e:
            return {"success": False, "error": str(e), "_length": 0}

    def extract_with_playwright(self, url: str) -> Dict[str, Any]:
        """Attempt to extract content using Playwright (headless browser)."""
        if not sync_playwright:
            return {"success": False, "error": "Playwright not installed", "_length": 0}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Block resources to speed up
                page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda route: route.abort())

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    # Helper for network idle
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except:
                        pass
                    
                    time.sleep(self.wait_after_load)
                except Exception as e:
                    browser.close()
                    return {"success": False, "error": f"Navigation failed: {str(e)}", "_length": 0}

                # Evaluate JS to clean DOM before text extraction if possible
                # (Re-using soup logic mostly, but we can do some JS cleanup here)
                try:
                    page.evaluate("""() => {
                        const noise = document.querySelectorAll('script, style, noscript, header, footer, nav, aside, form, .breadcrumb, .menu, .navbar');
                        noise.forEach(el => el.remove());
                    }""")
                except:
                    pass

                # Get HTML and parse with Soup (Robust & Consistent with requests method)
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                content = self.pick_main_text_from_soup(soup)
                
                browser.close()

                return {
                    "success": True,
                    "description": "", # Harder to get meta from JS rendered sometimes, but soup has it if present
                    "content": content,
                    "url": url,
                    "_length": len(content)
                }

        except Exception as e:
            return {"success": False, "error": str(e), "_length": 0}

    def scrape_single(self, url: str) -> Dict[str, Any]:
        """
        Main strategy:
        1. Try Requests.
        2. If Requests returns little content (< 50 chars), try Playwright.
        """
        # 1. Try Requests
        req_result = self.extract_with_requests(url)
        if req_result["success"] and req_result["_length"] >= 50:
            req_result.pop("_length")
            return req_result

        # 2. Try Playwright
        print(f"  [Info] Static content low for {url}, switching to Playwright...")
        play_result = self.extract_with_playwright(url)
        
        # Prefer Playwright result if successful and has content
        if play_result["success"] and play_result["_length"] >= 50:
            play_result.pop("_length")
            return play_result

        # Fallback to whatever had more content
        req_len = req_result.pop("_length", 0)
        play_len = play_result.pop("_length", 0)

        if play_len > req_len:
            return play_result
        return req_result

    def run(self, max_items: Optional[int] = None):
        """
        Main execution flow.
        """
        print(f"[{self.department.upper()}] 開始執行爬蟲...")
        
        # Step 1: Discover Links
        try:
            links = self.fetch_links()
        except Exception as e:
            print(f"[{self.department.upper()}] 取得連結失敗: {e}")
            return

        print(f"[{self.department.upper()}] 共發現 {len(links)} 個項目")
        
        # Save links immediately
        self._save_data(links, f"{self.department}.service_link")

        # Step 2: Scrape Content
        if max_items:
            links = links[:max_items]
            print(f"[{self.department.upper()}] 測試模式：僅爬取前 {max_items} 筆")

        results = []
        for idx, item in enumerate(links, 1):
            title = item.get("title", 'No Title')
            url = item.get("url", '')
            
            print(f"[{idx}/{len(links)}] {title}")
            if not url:
                item["scraped"] = {"success": False, "error": "No URL provided"}
            else:
                item["scraped"] = self.scrape_single(url)
            
            results.append(item)
            time.sleep(1) # Polite delay

        # Step 3: Save final results
        self._save_data(results, f"{self.department}.information")
        print(f"[{self.department.upper()}] 全部完成！檔案已儲存至 {self.base_output_path}")

    def _save_data(self, data: List[Dict], filename_base: str):
        # Save JSON
        json_path = os.path.join(self.base_output_path, f"{filename_base}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Save CSV (Flattening structure)
        csv_path = os.path.join(self.base_output_path, f"{filename_base}.csv")
        if not data:
            return

        # Determine fields. If it's the full result, flatten 'scraped'
        flat_data = []
        for d in data:
            flat_item = d.copy()
            if "scraped" in flat_item:
                scraped = flat_item.pop("scraped")
                flat_item["description"] = scraped.get("description", "")
                flat_item["content"] = scraped.get("content", "")
                flat_item["success"] = scraped.get("success", False)
                # Remove large/internal fields if necessary
            flat_data.append(flat_item)

        if flat_data:
            keys = flat_data[0].keys()
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(flat_data)
