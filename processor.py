import os
import json
import re
from typing import List, Dict, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter

class DataProcessor:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        # Configurable chunking settings+
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=600,
            chunk_overlap=100,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]
        )
        
        # Define known building patterns for detection
        self.building_patterns = {
            "行政大樓": ["行政大樓", "Administration Building"],
            "敬賢樓": ["敬賢樓", "Jing-Xian Hall"],
            "總圖書館": ["總圖書館", "Main Library"],
            "共同教學館": ["共同教學館", "General Building"],
            "禮賢樓": ["禮賢樓", "Lixian Hall"],
            "展書樓": ["展書樓", "Jan Shu Hall"],
            "望樂樓": ["望樂樓", "Hall of Joy and Hope"]
        }

    def _detect_building(self, text: str) -> str:
        """Helper to detect building name from text using patterns."""
        for building_zh, patterns in self.building_patterns.items():
            for pattern in patterns:
                if pattern in text:
                    return building_zh
        return None

    def build_location_map(self, raw_items: List[Dict]) -> Dict[str, str]:
        """
        Build a map of 'Office Name' -> 'Full Location Description' from admin data.
        """
        location_map = {}
        print("Building location map from admin data...")
        
        for item in raw_items:
            # We trust 'admin' items to contain the authoritative location info
            if item.get("department") == "admin":
                content = item.get("scraped", {}).get("content", "")
                if not content:
                    continue
                    
                clean_content = self.clean_text_advanced(content, "admin")
                building = self._detect_building(clean_content)
                
                if building and ("## " in clean_content or "樓" in clean_content):
                    offices = self._extract_office_locations(clean_content, building)
                    for office in offices:
                        # Map: "註冊組" -> "行政大樓 1樓 106室"
                        key = office['name_zh']
                        loc_info = f"{office['building']} {office['floor']} {office['room']}室"
                        location_map[key] = loc_info
                        
        print(f"Location map built with {len(location_map)} offices.")
        return location_map

    def enrich_content_with_locations(self, content: str, location_map: Dict[str, str]) -> str:
        """
        Inject location information if an office name is mentioned in the text.
        """
        if not content:
            return ""
            
        enriched_content = content
        added_locations = []
        
        # Check for each office in the map
        for office_name, location in location_map.items():
            # Basic matching: if office name is in text, but location details might not be
            # Avoid matching if it's just a substring of another word, but simplistic check is ok for now
            if office_name in content:
                # Avoid adding if the location string is already extremely similar in the text
                # (Simple check: if building name is not near the office name)
                # For now, just append as a reference note works best for RAG
                
                # Deduplication check: don't add if we already resolved this office for this chunk
                if f"{office_name}位置：" not in str(added_locations):
                    added_locations.append(f"{office_name}位置：{location}")
        
        if added_locations:
            # Limit to top 5 relevant locations to avoid cluttering too much?
            # Or just append all matches. Let's append all but handle duplicates carefully.
            # Using a set to deduplicate
            unique_locs = sorted(list(set(added_locations)))
            
            enrichment_text = "\n\n【系統補充位置資訊】\n" + "\n".join(unique_locs)
            enriched_content += enrichment_text
            
        return enriched_content

    def clean_text_advanced(self, text: str, dept: str = "") -> str:
        """Advanced cleaning for RAG content."""
        if not text:
            return ""

        # 0. Idempotency: Remove existing enrichment blocks first
        if "【系統補充位置資訊】" in text:
            text = text.split("【系統補充位置資訊】")[0].strip()
        # 1. Dept Specific Pre-fixes
        if dept == "admin":
            text = text.replace("Admi nistration", "Administration")
            # Remove repeated footer chunks in admin
            text = text.split("Overseas Chinese and Mainland Chinese Students Advising Division\n列印成績單")[0]

        # 2. General Noise Removal
        noise_patterns = [
            "Administration Building - List of Offices",
            "Main Content",
            "地圖 MAP",
            "校園景觀 Campus View",
            "更多資訊",
            "學校地圖上的建物編號",
            "Building ID /",
            "單位清單 / Offices list"
        ]
        lines = text.split("\n")
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(pattern in line for pattern in noise_patterns):
                continue
            # Remove existing markdown headers to avoid duplication
            if line.startswith("##"):
                line = line.lstrip("#").strip()
            clean_lines.append(line)

        # 3. Structural Reformatting for Office Lists
        # Pattern: [Room Number] \n [Name Zh] \n [Name En]
        # Or [Name Zh] \n [Name En]
        final_lines = []
        i = 0
        while i < len(clean_lines):
            line = clean_lines[i]
            
            # Detect starting with Room Number (usually 3 digits or B1)
            is_room = line.isdigit() and len(line) <= 4 or (line.startswith("B") and line[1:].isdigit())
            
            if is_room and i + 2 < len(clean_lines):
                # Check if next lines look like names (not headers or rooms)
                next1 = clean_lines[i+1]
                next2 = clean_lines[i+2]
                if not (next1[0].isdigit() or "#" in next1 or "樓" in next1):
                    # Format as: - [Room] [Zh] ([En])
                    final_lines.append(f"- {line} {next1} ({next2})")
                    i += 3
                    continue
            
            # Formatting floor headers
            if "樓" in line and len(line) < 10:
                # Avoid duplicate ## if already present
                if not line.startswith("##"):
                    final_lines.append(f"## {line}")
                else:
                    final_lines.append(line)
            else:
                final_lines.append(line)
            i += 1

        result = "\n".join(final_lines)
        # Final safety cleanup for any leftover repetitive markers
        if "【系統補充位置資訊】" in result:
             result = result.split("【系統補充位置資訊】")[0].strip()
        return result

    def _extract_title(self, content: str) -> str:
        """Extract the first line as title."""
        if not content:
            return ""
        lines = content.split('\n')
        # Filter out empty lines to find the first real line
        for line in lines:
            if line.strip():
                return line.strip()
        return ""

    def _extract_unit_name_from_text(self, text: str) -> Optional[str]:
        """Extract a probable unit name from text."""
        if not text:
            return None
        unit_patterns = [
            r'(.{2,12}組)',
            r'(.{2,12}處)',
            r'(.{2,12}中心)',
            r'(.{2,12}部)',
            r'(.{2,12}室)',
            r'(.{2,12}館)',
            r'(.{2,12}系)',
            r'(.{2,12}所)',
            r'(.{2,12}院)',
            r'(.{2,12}課)',
        ]
        for pattern in unit_patterns:
            match = re.search(pattern, text)
            if match:
                unit = match.group(1).strip()
                if unit and not unit[0].isdigit():
                    return unit
        return None

    def _normalize_unit_id(self, unit_name: str) -> str:
        """Normalize unit name to a stable ID for cross-source matching."""
        if not unit_name:
            return ""
        normalized = re.sub(r'[\s\(\)（）\[\]【】\-–—_·•:：,，。．./\\]', '', unit_name)
        return normalized.lower()

    def _classify_chunk_type(self, text: str) -> str:
        """Lightweight chunk type classifier for query intent boosting."""
        if not text:
            return "general"
        lower_text = text.lower()
        phone_keywords = ["電話", "分機", "聯絡方式", "聯絡", "tel", "phone"]
        service_keywords = ["服務", "業務", "職掌", "辦理", "申請", "流程", "規定", "要件"]
        if any(keyword.lower() in lower_text for keyword in phone_keywords):
            return "phone"
        if any(keyword.lower() in lower_text for keyword in service_keywords):
            return "service"
        return "general"

    def _extract_office_locations(self, content: str, building_name: str) -> list:
        """
        Extract individual office locations from building content.
        Parses patterns like:
        - ## 1樓
        - - 101 訪客中心 (Visitor Center)
        
        Returns list of dicts with: building, floor, room, name_zh, name_en
        """
        offices = []
        current_floor = ""
        
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            
            # Detect floor headers (e.g., "## 1樓", "1樓", "2樓")
            floor_match = re.match(r'^(?:##\s*)?(\d+樓|B\d+)', line)
            if floor_match:
                current_floor = floor_match.group(1)
                continue
            
            # Detect office entries (e.g., "- 101 訪客中心 (Visitor Center)")
            # Pattern: - [room_number] [chinese_name] ([english_name])
            office_match = re.match(r'^-\s*(\d+|B\d+)\s+(.+?)(?:\s*\((.+?)\))?$', line)
            if office_match and current_floor:
                room = office_match.group(1)
                name_zh = office_match.group(2).strip()
                name_en = office_match.group(3).strip() if office_match.group(3) else ""
                
                offices.append({
                    "building": building_name,
                    "floor": current_floor,
                    "room": room,
                    "name_zh": name_zh,
                    "name_en": name_en
                })
        
        return offices

    def _create_location_chunks(self, offices: list, source_url: str, department: str) -> list:
        """
        Create individual location chunks for each office.
        Each chunk contains rich location information that can be easily retrieved.
        """
        location_chunks = []
        
        for office in offices:
            # Create a rich, searchable description
            content = f"""【{office['name_zh']}位置資訊】
{office['name_zh']}
英文名稱：{office['name_en']}
位置：{office['building']} {office['floor']} {office['room']}室
建築物：{office['building']}
樓層：{office['floor']}
房間號碼：{office['room']}

{office['name_zh']}位於{office['building']}{office['floor']}的{office['room']}室。
如需前往{office['name_zh']}，請至{office['building']}{office['floor']}找{office['room']}室。"""
            
            # Add English location info if available
            if office['name_en']:
                content += f"\n{office['name_en']} is located at Room {office['room']}, {office['floor']}, {office['building']}."
            
            location_chunks.append({
                "text": content,
                "metadata": {
                    "title": f"{office['name_zh']}位置",
                    "url": source_url,
                    "department": department,
                    "type": "location",
                    "unit_name": office["name_zh"],
                    "unit_id": self._normalize_unit_id(office["name_zh"]),
                    "building": office['building'],
                    "floor": office['floor'],
                    "room": office['room']
                }
            })
        
        return location_chunks

    def process(self, save_back_to_source: bool = False):
        """Main processing flow."""
        # 1. Load Data
        raw_items = self.load_json_files()
        print(f"Total raw items loaded: {len(raw_items)}")

        # 2. Build Location Map first (requires cleaning logic implicitly, but we do on fly)
        # However, to be robust, let's load raw, then building map from raw (cleaning internally), 
        # then proceed to main cleaning loop.
        self.location_map = self.build_location_map(raw_items)

        # 3. Filter & Clean & Enrich
        valid_items = []
        processed_data_by_dept = {} 

        for item in raw_items:
            dept = item.get("department", "unknown")
            scraped = item.get("scraped", {})
            if not scraped.get("success"):
                continue
            
            content = scraped.get("content", "").strip()
            if len(content) < 50:
                continue

            # Core Cleaning
            clean_content = self.clean_text_advanced(content, dept)
            
            # [NEW] Enrich content with location info
            # We allow self-reference (admin docs getting enriched) because 
            # sometimes the office list doesn't say "The Registrar is here", 
            # it just says "106 Registrar". Adding explicit "Registrar is at Admin Bldg 106" helps.
            # But let's verify if it creates too much noise. 
            # Ideally, enriching 'aca' (Academic Affairs) docs with 'admin' locations is the goal.
            clean_content = self.enrich_content_with_locations(clean_content, self.location_map)
            
            scraped["content"] = clean_content
            item["clean_content"] = clean_content
            valid_items.append(item)
            
            # Grouping for saving back
            filepath = item.get("_source_path")
            if filepath:
                if filepath not in processed_data_by_dept:
                    processed_data_by_dept[filepath] = []
                save_item = item.copy()
                save_item.pop("department", None)
                save_item.pop("_source_path", None)
                save_item.pop("clean_content", None)
                processed_data_by_dept[filepath].append(save_item)
        
        print(f"Valid items after filtering: {len(valid_items)}")

        # 4. Save Cleaned Source Files (If requested)
        if save_back_to_source:
            for filepath, data in processed_data_by_dept.items():
                print(f"Saving cleaned data back to {filepath}...")
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

        # 5. Chunking
        all_chunks = []
        location_chunks_count = 0
        
        for item in valid_items:
            text = item["clean_content"]
            title = item.get("title") or self._extract_title(text)
            unit_name = self._extract_unit_name_from_text(title) or self._extract_unit_name_from_text(text)
            unit_id = self._normalize_unit_id(unit_name) if unit_name else ""
            
            metadatas = {
                "title": title,
                "url": item.get("url", ""),
                "department": item.get("department", "unknown"),
                "type": self._classify_chunk_type(text)
            }
            if unit_name:
                metadatas["unit_name"] = unit_name
            if unit_id:
                metadatas["unit_id"] = unit_id
            
            # Check if this is a building office list and extract locations
            # Use the class-level patterns and helper
            detected_building = self._detect_building(text)
            
            # If building detected with floor/room patterns, create location chunks
            if detected_building and ("## " in text or "樓" in text) and "- " in text:
                offices = self._extract_office_locations(text, detected_building)
                if offices:
                    location_chunks = self._create_location_chunks(
                        offices, 
                        item.get("url", ""), 
                        item.get("department", "unknown")
                    )
                    all_chunks.extend(location_chunks)
                    location_chunks_count += len(location_chunks)
                    print(f"  - Created {len(location_chunks)} location chunks for {detected_building}")
            
            # Split text (still create regular chunks for full context)
            chunks = self.text_splitter.create_documents([text], metadatas=[metadatas])
            
            for chunk in chunks:
                # Prepend title to content for context injection
                chunk.page_content = f"【位於：{title}】\n{chunk.page_content}"
                
                all_chunks.append({
                    "text": chunk.page_content,
                    "metadata": chunk.metadata
                })

        print(f"Total chunks created: {len(all_chunks)} (including {location_chunks_count} location chunks)")
        
        # 5. Save Processed Data for Indexing
        output_path = "data/processed_chunks.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_chunks, f, ensure_ascii=False, indent=2)
        print(f"Processed chunks saved to {output_path}")

    def load_json_files(self) -> List[Dict]:
        """Load all .information.json files and track their source."""
        all_data = []
        for root, dirs, files in os.walk(self.data_dir):
            for file in files:
                if file.endswith(".information.json"):
                    filepath = os.path.join(root, file)
                    # Better department detection: 
                    # If the file is in data/admin/admin/..., dept should be 'admin'
                    path_parts = root.replace(self.data_dir, "").strip(os.path.sep).split(os.path.sep)
                    if not path_parts or path_parts[0] == "":
                        dept = "unknown"
                    else:
                        dept = path_parts[0]
                    # Helper to get the correct dept code
                    print(f"Loading data from {filepath}...")
                    
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            for item in data:
                                item["department"] = dept
                                item["_source_path"] = filepath
                            all_data.extend(data)
                    except Exception as e:
                        print(f"Error loading {filepath}: {e}")
        return all_data

if __name__ == "__main__":
    processor = DataProcessor()
    # Execute with save_back_to_source=True to fulfill the user's request to clean the JSON itself
    processor.process(save_back_to_source=True)
