from .base import BaseScraper
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any

class AdminScraper(BaseScraper):
    """
    Scraper for NTU Administrative Office Directory
    Target: https://homepage.ntu.edu.tw/~ntuga/admin/
    """
    
    def __init__(self, output_dir="data/admin"):
        super().__init__(department="admin", output_dir=output_dir)
        self.base_url = "https://homepage.ntu.edu.tw/~ntuga/admin"
    
    def fetch_links(self):
        """
        Return the list of pages to scrape
        """
        pages = [
            f"{self.base_url}/index.html",      # 行政大樓
            f"{self.base_url}/jinxian.html",    # 敬賢樓
            f"{self.base_url}/lixian.html",     # 禮賢樓
            f"{self.base_url}/others.html"      # 行政大樓周邊
        ]
        return pages
    
    def extract_with_requests(self, url: str) -> Dict[str, Any]:
        """
        Custom extraction ensuring we capture office Directory content from tables.
        The default BaseScraper logic might skip tables or select the wrong container.
        """
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 1. Attempt to find the main content block matches
            # There might be multiple 'maincontent' sections (e.g. Intro vs Table)
            main_sections = soup.find_all("section", class_="maincontent")
            
            if not main_sections:
                # Fallback to div.container
                container = soup.find("div", class_="container")
            else:
                # Create a wrapper div to hold all sections for easier processing
                container = soup.new_tag("div")
                for section in main_sections:
                    container.append(section)
            
            # If still nothing, use the whole body
            if not container:
                container = soup.find("body")

            if not container:
                return {"success": False, "error": "No content container found", "_length": 0}

            # 2. Extract Text with Structure Preservation
            # Remove scripts, styles
            for tag in container(["script", "style", "nav", "header", "footer"]):
                tag.decompose()

            content_parts = []
            
            # Get the page title if possible
            h1 = soup.find("h1")
            if h1:
                content_parts.append(f"# {h1.get_text(strip=True)}")
            
            # Extract content from container
            text = container.get_text(separator="\n", strip=True)
            content_parts.append(text)
            
            final_content = "\n\n".join(content_parts)

            # Get description
            desc = ""
            meta_desc = soup.find("meta", {"name": "description"})
            if meta_desc:
                desc = meta_desc.get("content", "").strip()

            return {
                "success": True,
                "description": desc,
                "content": final_content,
                "url": url,
                "_length": len(final_content)
            }
            
        except Exception as e:
             return {"success": False, "error": str(e), "_length": 0}

    def run(self, max_items=None):
        """
        Override run to add custom processing for admin directory
        max_items is ignored for this scraper (fixed number of pages)
        """
        links = self.fetch_links()
        results = []
        
        print(f"[{self.department.upper()}] Found {len(links)} pages to scrape")
        
        for url in links:
            print(f"[{self.department.upper()}] Scraping: {url}")
            
            # Extract content
            scraped_data = self.extract_with_requests(url)
            
            if scraped_data["success"]:
                # Build result
                result = {
                    "url": url,
                    "scraped": scraped_data
                }
                results.append(result)
            else:
                print(f"[{self.department.upper()}] Failed: {url}")
        
        # Save results using BaseScraper's _save_data method
        self._save_data(results, f"{self.department}.information")
        print(f"[{self.department.upper()}] Scraping complete. Saved {len(results)} pages.")
        
        return results
