"""
NTU Map Service Module
提供台大建築物地圖服務,包含座標查詢和地圖生成功能
"""

import requests
import re
from typing import Optional, List, Dict
import folium
from functools import lru_cache


class NTUMapService:
    """台大地圖服務類別"""
    
    API_URL = "https://map.ntu.edu.tw/ntuga/public/buildinfo.htm"
    DEFAULT_CENTER = (25.0173, 121.5397)  # 台大校園中心座標
    
    def __init__(self):
        """初始化地圖服務,載入並快取建築物資料"""
        self.buildings_data = self._load_buildings_data()
        self.name_to_building = self._create_name_mapping()
    
    def _load_buildings_data(self) -> List[Dict]:
        """
        從台大 API 載入建築物資料
        
        Returns:
            建築物資料列表
        """
        try:
            params = {
                "action": "getCentroidByBuildId",
                "proj": "EPSG:4326"
            }
            response = requests.get(self.API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            print(f"Warning: Failed to load building data from NTU API: {e}")
            return []
    
    def _create_name_mapping(self) -> Dict[str, Dict]:
        """
        建立建築物名稱到資料的映射
        支援中文名稱和英文名稱查詢
        
        Returns:
            名稱映射字典
        """
        mapping = {}
        for building in self.buildings_data:
            # 中文名稱
            if building.get("name"):
                name = building["name"]
                # 移除括號內容以支援模糊匹配
                base_name = re.sub(r'\s*\([^)]*\)', '', name).strip()
                mapping[name] = building
                if base_name != name:
                    mapping[base_name] = building
            
            # 英文名稱
            if building.get("name_en"):
                mapping[building["name_en"]] = building
        
        return mapping
    
    def extract_building_from_location(self, location_text: str) -> Optional[str]:
        """
        從位置文字中提取建築物名稱
        例如: "行政大樓 1樓 106室" -> "行政大樓"
        
        Args:
            location_text: 位置文字
            
        Returns:
            建築物名稱,如果無法提取則返回 None
        """
        if not location_text:
            return None
        
        # 常見的樓層和房間號模式
        # 移除 "X樓" 和 "XXX室" 等後綴
        building_name = re.sub(r'\s*\d+樓.*', '', location_text).strip()
        building_name = re.sub(r'\s*\([^)]*\)', '', building_name).strip()
        
        return building_name if building_name else None
    
    def get_building_coordinates(self, building_name: str) -> Optional[Dict]:
        """
        根據建築物名稱查詢座標資訊
        支援模糊匹配
        
        Args:
            building_name: 建築物名稱
            
        Returns:
            包含座標和名稱的字典,如果找不到則返回 None
            格式: {"name": str, "name_en": str, "lat": float, "lon": float}
        """
        if not building_name:
            return None
        
        # 直接匹配
        if building_name in self.name_to_building:
            building = self.name_to_building[building_name]
            return {
                "name": building.get("name"),
                "name_en": building.get("name_en"),
                "lat": float(building.get("lat", 0)),
                "lon": float(building.get("lon", 0)),
                "uid": building.get("uid")
            }
        
        # 模糊匹配 - 查找包含關鍵字的建築物
        building_name_clean = building_name.strip()
        for name, building in self.name_to_building.items():
            if building_name_clean in name or name in building_name_clean:
                return {
                    "name": building.get("name"),
                    "name_en": building.get("name_en"),
                    "lat": float(building.get("lat", 0)),
                    "lon": float(building.get("lon", 0)),
                    "uid": building.get("uid")
                }
        
        return None
    
    def create_map(
        self, 
        buildings: List[str], 
        center_on_first: bool = True,
        zoom_start: int = 16
    ) -> Optional[folium.Map]:
        """
        生成包含多個建築物標記的互動式地圖
        
        Args:
            buildings: 建築物名稱列表
            center_on_first: 是否以第一個建築物為中心
            zoom_start: 初始縮放級別
            
        Returns:
            Folium 地圖物件,如果沒有有效建築物則返回 None
        """
        if not buildings:
            return None
        
        # 收集所有有效的建築物座標
        building_coords = []
        for building_name in buildings:
            coords = self.get_building_coordinates(building_name)
            if coords:
                building_coords.append(coords)
        
        if not building_coords:
            return None
        
        # 決定地圖中心點
        if center_on_first:
            center = (building_coords[0]["lat"], building_coords[0]["lon"])
        else:
            # 計算所有建築物的中心點
            avg_lat = sum(b["lat"] for b in building_coords) / len(building_coords)
            avg_lon = sum(b["lon"] for b in building_coords) / len(building_coords)
            center = (avg_lat, avg_lon)
        
        # 如果有多個建築物,自動調整縮放以包含所有標記
        if len(building_coords) > 1:
            zoom_start = 15
        
        # 建立地圖
        m = folium.Map(
            location=center,
            zoom_start=zoom_start,
            tiles="OpenStreetMap"
        )
        
        # 添加建築物標記
        for building in building_coords:
            # 建立彈出視窗內容
            popup_html = f"""
            <div style="font-family: Arial, sans-serif; min-width: 150px;">
                <h4 style="margin: 0 0 5px 0; color: #002060;">{building['name']}</h4>
                <p style="margin: 0; color: #666; font-size: 12px;">{building['name_en'] or ''}</p>
                <p style="margin: 5px 0 0 0; font-size: 11px; color: #999;">
                    {building['lat']:.6f}, {building['lon']:.6f}
                </p>
            </div>
            """
            
            folium.Marker(
                location=[building["lat"], building["lon"]],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=building["name"],
                icon=folium.Icon(color="red", icon="info-sign")
            ).add_to(m)
        
        # 如果有多個建築物,調整視野以包含所有標記
        if len(building_coords) > 1:
            lats = [b["lat"] for b in building_coords]
            lons = [b["lon"] for b in building_coords]
            m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
        
        return m
    
    def extract_buildings_from_metadata(self, documents: List[Dict]) -> List[str]:
        """
        從檢索到的文件 metadata 中提取建築物名稱
        
        Args:
            documents: 包含 metadata 的文件列表
            
        Returns:
            建築物名稱列表
        """
        buildings = set()
        
        for doc in documents:
            metadata = doc.get("metadata", {})
            
            # 嘗試從不同的 metadata 欄位提取位置資訊
            # Add 'unit_name' and 'title' as fallback sources
            location_fields = ["location", "building", "address", "office", "unit_name", "title"]
            
            for field in location_fields:
                if field in metadata:
                    text_val = str(metadata[field])
                    # 1. Try extraction helper
                    building_name = self.extract_building_from_location(text_val)
                    if building_name and building_name in self.name_to_building:
                        buildings.add(building_name)
                    
                    # 2. Direct keyword check against known buildings (Robust fallback)
                    # If the text represents a known building (e.g. "行政大樓"), catch it.
                    for known_name in self.name_to_building.keys():
                        if len(known_name) > 2 and known_name in text_val:
                             buildings.add(known_name)
            
            # 也可以從內容中嘗試提取
            content = doc.get("content", "")
            if "位置：" in content or "位於" in content or "地點：" in content:
                # 簡單的位置提取邏輯
                for building_name in self.name_to_building.keys():
                    if building_name in content and len(building_name) > 2:
                        buildings.add(building_name)
        
        return list(buildings)


# 全域單例,避免重複載入資料
_map_service_instance = None

def get_map_service() -> NTUMapService:
    """
    取得地圖服務單例
    
    Returns:
        NTUMapService 實例
    """
    global _map_service_instance
    if _map_service_instance is None:
        _map_service_instance = NTUMapService()
    return _map_service_instance
