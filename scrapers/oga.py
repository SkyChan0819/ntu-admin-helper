import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from .base import BaseScraper

class OGAScraper(BaseScraper):
    def __init__(self):
        super().__init__(department="oga")
        # Fixed list from original oga.scraper.py
        self.fixed_links = [
            {
                "title": "FAQ list (faq=131)",
                "url": "https://ga.ntu.edu.tw/property/main_ch/faqList.aspx?faq=131&uid=233&pid=233",
            },
            {
                "title": "Document detail 29761",
                "url": "https://ga.ntu.edu.tw/property/main_ch/docDetail.aspx?uid=335&pid=335&docid=29761&check=0",
            },
            {
                "title": "本組介紹",
                "url": "https://ga.ntu.edu.tw/property/main_ch/docDetail/331/229/242/%e6%9c%ac%e7%b5%84%e4%bb%8b%e7%b4%b9",
            },
        ]

    def fetch_links(self) -> List[Dict[str, str]]:
        # OGA uses a hardcoded list in the original script
        return self.fixed_links
