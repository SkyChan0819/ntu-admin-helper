import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urljoin
from .base import BaseScraper

class OSAScraper(BaseScraper):
    def __init__(self):
        super().__init__(department="osa")
        self.base_url = "https://osa.ntu.edu.tw/services/{}"
        self.categories = [
            "financialaid",
            "campuslife",
            "healthcare",
            "accommodation",
            "activity",
            "careers",
            "others",
        ]

    def fetch_links(self) -> List[Dict[str, str]]:
        all_rows = []
        for cat in self.categories:
            url = self.base_url.format(cat)
            print(f"[OSA] Fetching category: {cat}")
            try:
                resp = requests.get(url, headers=self.headers, timeout=15)
                resp.encoding = "utf-8"
                soup = BeautifulSoup(resp.text, "html.parser")
                
                rows = self._parse_tables(soup, url, cat)
                all_rows.extend(rows)
            except Exception as e:
                print(f"[Error] Failed to fetch category {cat}: {e}")
                
        return all_rows

    def _parse_tables(self, soup: BeautifulSoup, page_url: str, category: str) -> List[Dict[str, str]]:
        rows = []
        for table in soup.find_all("table"):
            tr_elements = table.find_all("tr")
            if not tr_elements:
                continue
            
            # Skip header row usually
            for tr in tr_elements[1:]:
                cells = tr.find_all(["th", "td"])
                if len(cells) < 2:
                    continue
                
                item_name = cells[0].get_text(strip=True)
                unit = cells[1].get_text(strip=True)
                
                link_tag = cells[0].find("a") or cells[1].find("a")
                href = ""
                if link_tag and link_tag.get("href"):
                     href = urljoin(page_url, link_tag.get("href"))
                
                if not item_name and not unit and not href:
                    continue
                    
                rows.append({
                    "category": category,
                    "title": item_name,
                    "unit": unit,
                    "url": href
                })
        return rows
