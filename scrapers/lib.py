import re
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Any
from collections import Counter
from .base import BaseScraper

class LibScraper(BaseScraper):
    def __init__(self):
        super().__init__(department="lib")
        self.base_url_pattern = "https://www.lib.ntu.edu.tw/node/{}"
        self.start_id = 100
        self.end_id = 200  # 擴大範圍到 200
        self.node_115_url = "https://www.lib.ntu.edu.tw/node/115"

    def fetch_links_from_node_115(self) -> List[Dict[str, str]]:
        """從 Node 115 頁面提取所有內部連結"""
        print(f"[LIB] 正在從 Node 115 提取內部連結...")
        try:
            resp = requests.get(self.node_115_url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            links = []
            seen_urls = set()
            
            for a in soup.find_all("a", href=True):
                href = a["href"]
                full_url = urljoin(self.node_115_url, href)
                
                # 只保留台大圖書館的內部連結
                if "www.lib.ntu.edu.tw" in full_url:
                    # 移除 fragment (#) 和 query parameters (?) 以避免重複
                    parsed = urlparse(full_url)
                    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    
                    if clean_url not in seen_urls and clean_url != self.node_115_url:
                        seen_urls.add(clean_url)
                        text = a.get_text(strip=True)
                        links.append({
                            "title": text if text else "No Title",
                            "url": clean_url,
                            "source": "node_115"
                        })
            
            print(f"[LIB] 從 Node 115 發現 {len(links)} 個唯一內部連結")
            return links
        except Exception as e:
            print(f"[LIB] 從 Node 115 提取連結時發生錯誤: {e}")
            return []

    def fetch_links(self) -> List[Dict[str, str]]:
        links = []
        
        # 1. Node 100-200
        for idx in range(self.start_id, self.end_id + 1):
            links.append({
                "no": idx, 
                "url": self.base_url_pattern.format(idx),
                "title": f"Node {idx}",
                "source": "node_range"
            })
        
        # 2. Node 115 的內部連結
        node_115_links = self.fetch_links_from_node_115()
        links.extend(node_115_links)
        
        print(f"[LIB] 總共產生 {len(links)} 個連結 (Node範圍: {self.end_id - self.start_id + 1}, Node115連結: {len(node_115_links)})")
        return links

    def split_blocks(self, text: str) -> List[str]:
        """Split long text into short blocks so duplicated boilerplate can be filtered."""
        if not text:
            return []
        # Split by punctuation or newlines
        parts = re.split(r"(?<=[。！？!?])\s+|\n+", text)
        return [p.strip() for p in parts if p and p.strip()]

    def run(self, max_items: int = None):
        """
        Override run to include the specific 'boilerplate removal' logic from the original lib scraper.
        """
        print(f"[{self.department.upper()}] 開始執行爬蟲 (含去重邏輯)...")
        
        links = self.fetch_links()
        if max_items:
            links = links[:max_items]

        # Save links
        self._save_data(links, f"{self.department}.service_link")

        results = []
        for idx, item in enumerate(links, 1):
            url = item.get("url", "")
            print(f"[{idx}/{len(links)}] {url}")
            
            scraped = self.scrape_single(url)
            
            # Additional Lib specific extraction: Blocks
            content = scraped.get("content", "")
            scraped["blocks"] = self.split_blocks(content)
            
            item["scraped"] = scraped
            results.append(item)
            
            # Lib scraper had random sleep
            time.sleep(random.uniform(0.5, 1.5))

        # --- Unique Content Logic (Step 2.5 in original) ---
        print(f"[{self.department.upper()}] 正在移除重複的樣板文字...")
        block_counter = Counter()
        for item in results:
            blocks = item.get("scraped", {}).get("blocks", [])
            for block in blocks:
                if len(block) >= 8:
                    block_counter[block] += 1
        
        for item in results:
            scraped = item.get("scraped", {})
            blocks = scraped.get("blocks", [])
            # Keep blocks that appear only once (unique to this page)
            unique_blocks = [b for b in blocks if len(b) >= 8 and block_counter[b] == 1]
            unique_text = "\n".join(unique_blocks) if unique_blocks else ""
            
            scraped["content_unique"] = unique_text
            # Use unique text as main content if available, else fallback
            if unique_text:
                scraped["content"] = unique_text
            
            # Clean up temp field
            scraped.pop("blocks", None)
            item["scraped"] = scraped

        # Save final results
        self._save_data(results, f"{self.department}.information")
        print(f"[{self.department.upper()}] 完成！檔案已儲存至 {self.base_output_path}")
