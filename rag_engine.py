# -*- coding: utf-8 -*-
"""
Enhanced RAG Engine with Two-Stage Retrieval
解決跨資料來源無法相互參照的問題
"""
import chromadb
from chromadb.config import Settings
import re
from typing import List, Dict, Tuple

# Import from unified config
from config import (
    get_chroma_client, 
    BGEEmbeddingFunction,
    CHROMA_DB_PATH,
    COLLECTION_NAME
)


class EnhancedRAGEngine:
    """
    Two-Stage Retrieval RAG Engine
    
    Stage 1: 找到相關的單位/主題
    Stage 2: 用單位名稱進行二次檢索，收集所有相關資訊
    """
    
    def __init__(self, db_path: str = None, collection_name: str = None, embedding_function=None):
        """
        Args:
            embedding_function: Optional embedding function or instance to pass to Chroma.
                If None, no embedding function will be provided and the heavy embedding
                model won't be instantiated at init time.
        """
        self.db_path = db_path or CHROMA_DB_PATH
        self.collection_name = collection_name or COLLECTION_NAME
        self.embedding_function = embedding_function
        self.collection = None
        self._initialize_collection()
    
    def _initialize_collection(self):
        """Initialize ChromaDB connection"""
        print(f"DEBUG: EnhancedRAGEngine._initialize_collection called. db_path={self.db_path}")
        client = get_chroma_client(self.db_path)
        print("DEBUG: Chroma Client retrieved.")

        # If an embedding function was supplied, try to use it. Otherwise omit
        # embedding_function to avoid instantiating heavy models during import/tests.
        ef = self.embedding_function
        print(f"DEBUG: Embedding function provided: {ef}")
        
        if ef is None:
            print("DEBUG: Getting collection without embedding function...")
            self.collection = client.get_collection(name=self.collection_name)
            print("DEBUG: Collection retrieved (no ef).")
            return

        # If a class was passed, instantiate it; if an instance/callable was passed,
        # try to use it directly.
        ef_instance = ef
        try:
            # If ef is a class/type, calling it will create an instance.
            if isinstance(ef, type):
                print("DEBUG: Instantiating embedding function class...")
                ef_instance = ef()
                print("DEBUG: Embedding function instantiated.")
        except Exception as e:
            print(f"DEBUG: Error instantiating EF, falling back to as-is: {e}")
            # Fall back to using ef as-is
            ef_instance = ef

        self.collection = client.get_collection(
            name=self.collection_name,
            embedding_function=ef_instance
        )
    
    def _extract_unit_names(self, text: str) -> List[str]:
        """
        從文本中提取單位名稱
        使用正則表達式匹配常見單位名稱模式，並進行過濾
        """
        # Stricter patterns: 2-6 chars usually sufficient for meaningful names
        # Avoid long matches that are likely sentences
        unit_patterns = [
            r'([^\s,，。、]{2,6}組)',    # XX組
            r'([^\s,，。、]{2,6}處)',    # XX處
            r'([^\s,，。、]{2,8}中心)',  # XX中心 (some are longer)
            r'([^\s,，。、]{2,6}部)',    # XX部
            r'([^\s,，。、]{2,6}室)',    # XX室
            r'([^\s,，。、]{2,6}館)',    # XX館
        ]
        
        # Stopwords to filter out
        exclude_terms = {'本組', '該組', '各組', '分組', '小組', '本部', '該部', '本處', '該處', '本中心', '辦公室', '會議室'}
        
        units = set()
        for pattern in unit_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Basic cleaning
                clean_match = match.strip()
                
                # Filter out numbers (room numbers)
                if clean_match and clean_match[0].isdigit():
                    continue
                    
                # Filter out stopwords
                if clean_match in exclude_terms:
                    continue
                    
                # Filter out likely verbs/sentences ending in key char
                if any(v in clean_match for v in ['由', '為', '至', '在', '向', '到']):
                    continue
                    
                units.add(clean_match)
        
        return list(units)
    
    def _is_location_query(self, query: str) -> bool:
        """判斷是否為位置查詢"""
        location_keywords = ['在哪', '位置', '地址', '怎麼去', '如何到', 'where', 'location', '幾樓']
        return any(keyword in query.lower() for keyword in location_keywords)

    def _get_query_intent(self, query: str) -> str:
        """Detect query intent to prioritize chunk types."""
        if self._is_location_query(query):
            return "location"
        lower_query = query.lower()
        phone_keywords = ['電話', '分機', '聯絡方式', '聯絡', 'tel', 'phone']
        service_keywords = ['服務', '業務', '職掌', '辦理', '申請', '流程', '規定', '要件']
        if any(keyword.lower() in lower_query for keyword in phone_keywords):
            return "phone"
        if any(keyword.lower() in lower_query for keyword in service_keywords):
            return "service"
        return "general"

    def _apply_type_boost(self, meta: Dict, dist: float, intent: str) -> float:
        """Apply a small distance boost based on query intent."""
        chunk_type = meta.get('type', 'general')
        if intent == "location" and chunk_type == "location":
            return max(0, dist - 0.2)
        if intent == "phone" and chunk_type == "phone":
            return max(0, dist - 0.15)
        if intent == "service" and chunk_type == "service":
            return max(0, dist - 0.1)
        return dist

    def _rerank_with_intent(self, docs, metas, dists, intent: str, top_k: int) -> Dict:
        """Rerank results using intent-aware boosts."""
        if not docs:
            return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}
        boosted = []
        for doc, meta, dist in zip(docs, metas, dists):
            boosted_dist = self._apply_type_boost(meta, dist, intent)
            boosted.append((doc, meta, boosted_dist))
        boosted.sort(key=lambda x: x[2])
        boosted = boosted[:top_k]
        docs, metas, dists = zip(*boosted) if boosted else ([], [], [])
        return {
            'documents': [list(docs)],
            'metadatas': [list(metas)],
            'distances': [list(dists)]
        }

    def _append_location_chunks(
        self,
        results: Dict,
        unit_ids: List[str],
        unit_names: List[str],
        max_per_unit: int = 2
    ) -> Dict:
        """Append location chunks for detected units to ensure location availability."""
        docs = list(results.get('documents', [[]])[0])
        metas = list(results.get('metadatas', [[]])[0])
        dists = list(results.get('distances', [[]])[0])
        seen = set(doc[:100] for doc in docs)

        def _append(doc, meta, dist):
            doc_id = doc[:100]
            if doc_id in seen:
                return
            seen.add(doc_id)
            docs.append(doc)
            metas.append(meta)
            dists.append(dist)

        for unit_id in unit_ids:
            try:
                where = {"$and": [{"unit_id": unit_id}, {"type": "location"}]}
                loc_results = self.collection.query(
                    query_texts=[unit_id],
                    n_results=max_per_unit,
                    where=where
                )
            except Exception:
                loc_results = self.collection.query(
                    query_texts=[unit_id],
                    n_results=max_per_unit
                )
            for doc, meta, dist in zip(
                loc_results['documents'][0],
                loc_results['metadatas'][0],
                loc_results['distances'][0]
            ):
                if meta.get('type') == 'location':
                    _append(doc, meta, dist)

        if not unit_ids:
            for unit_name in unit_names:
                loc_results = self.collection.query(
                    query_texts=[unit_name],
                    n_results=max_per_unit
                )
                for doc, meta, dist in zip(
                    loc_results['documents'][0],
                    loc_results['metadatas'][0],
                    loc_results['distances'][0]
                ):
                    if meta.get('type') == 'location':
                        _append(doc, meta, dist)

        results['documents'] = [docs]
        results['metadatas'] = [metas]
        results['distances'] = [dists]
        return results
    
    def retrieve_stage1(self, query: str, n_results: int = 5) -> Dict:
        """
        Stage 1: 初次檢索
        找到最相關的文檔
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        return results
    
    def retrieve_stage2(self, unit_names: List[str], unit_ids: List[str], query: str, n_results: int = 10) -> Dict:
        """
        Stage 2: 基於單位名稱的二次檢索
        收集該單位的所有相關資訊（位置、電話、服務等）
        """
        all_docs = []
        all_metas = []
        all_distances = []
        seen_ids = set()
        
        for unit_id in unit_ids:
            try:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where={"unit_id": unit_id}
                )
            except Exception:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n_results
                )
            for doc, meta, dist in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                doc_id = f"{meta.get('url', '')}_{meta.get('title', '')}_{doc[:80]}"
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    all_docs.append(doc)
                    all_metas.append(meta)
                    all_distances.append(dist)

        if not all_docs and unit_names:
            for unit_name in unit_names:
                # 為每個單位進行檢索
                search_query = f"{unit_name} {query}"
                results = self.collection.query(
                    query_texts=[search_query],
                    n_results=n_results
                )
                
                # 合併結果，去重
                for doc, meta, dist in zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                ):
                    doc_id = f"{meta.get('url', '')}_{meta.get('title', '')}_{doc[:80]}"
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        all_docs.append(doc)
                        all_metas.append(meta)
                        all_distances.append(dist)
        
        # 按距離排序
        sorted_results = sorted(
            zip(all_docs, all_metas, all_distances),
            key=lambda x: x[2]
        )
        
        # 限制返回數量
        top_n = min(len(sorted_results), n_results)
        sorted_results = sorted_results[:top_n]
        
        if sorted_results:
            docs, metas, dists = zip(*sorted_results)
        else:
            docs, metas, dists = [], [], []
        
        return {
            'documents': [list(docs)],
            'metadatas': [list(metas)],
            'distances': [list(dists)]
        }
    
    def retrieve_with_priority(self, query: str, intent: str = "general") -> Dict:
        """
        帶優先級的檢索
        如果是位置查詢，優先返回 location-type 的 chunks
        """
        # 先進行正常檢索，獲取更多結果
        results = self.collection.query(
            query_texts=[query],
            n_results=15  # 獲取更多結果用於重排序
        )
        return self._rerank_with_intent(
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0],
            intent=intent,
            top_k=5
        )
    
    def retrieve(self, query: str, use_two_stage: bool = True) -> Dict:
        """
        主檢索函數
        
        Args:
            query: 查詢文本
            use_two_stage: 是否使用 two-stage retrieval
        
        Returns:
            檢索結果
        """
        # 判斷查詢意圖
        intent = self._get_query_intent(query)
        
        if not use_two_stage:
            # 單階段檢索 + 位置優先級
            return self.retrieve_with_priority(query, intent=intent)
        
        # === Two-Stage Retrieval ===
        
        # Stage 1: 初次檢索
        stage1_results = self.retrieve_stage1(query, n_results=5)
        
        # 從 Stage 1 結果中提取單位名稱
        unit_names = set()
        unit_ids = set()
        for doc in stage1_results['documents'][0]:
            units = self._extract_unit_names(doc)
            unit_names.update(units)
        for meta in stage1_results['metadatas'][0]:
            unit_id = meta.get('unit_id')
            # [FIX] Filter corrupted unit_ids (some contain long text)
            if unit_id and len(unit_id) < 50 and '\n' not in unit_id:
                unit_ids.add(unit_id)
            
            unit_name = meta.get('unit_name')
            if unit_name:
                unit_names.add(unit_name)
        
        # 如果沒找到單位名稱，直接返回 Stage 1 結果
        if not unit_names and not unit_ids:
            return self.retrieve_with_priority(query, intent=intent)
        
        if unit_ids:
            # Debug log for valid IDs
            safe_ids = [uid for uid in list(unit_ids)[:5] if len(uid) < 50]
            print(f"[Two-Stage] 找到單位 ID: {', '.join(safe_ids)}")
        else:
            print(f"[Two-Stage] 找到單位: {', '.join(list(unit_names)[:5])}")
        
        # Stage 2: 基於單位的二次檢索
        stage2_results = self.retrieve_stage2(list(unit_names), list(unit_ids), query, n_results=10)
        stage2_results = self._rerank_with_intent(
            stage2_results['documents'][0],
            stage2_results['metadatas'][0],
            stage2_results['distances'][0],
            intent=intent,
            top_k=5
        )
        
        return self._append_location_chunks(stage2_results, list(unit_ids), list(unit_names))


if __name__ == "__main__":
    # 測試
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    engine = EnhancedRAGEngine()
    
    test_queries = [
        "課外活動指導組在哪裡",
        "註冊組在哪裡",
        "如何申請休學",
        "圖書館的開放時間"
    ]
    
    print("=" * 70)
    print("Enhanced RAG Engine 測試")
    print("=" * 70)
    
    for query in test_queries:
        print(f"\n查詢: {query}")
        print("-" * 70)
        
        results = engine.retrieve(query, use_two_stage=True)
        
        print(f"Top 3 結果:")
        for i, (doc, meta) in enumerate(zip(
            results['documents'][0][:3],
            results['metadatas'][0][:3]
        )):
            chunk_type = meta.get('type', 'regular')
            title = meta.get('title', 'N/A')
            print(f"  [{i+1}] [{chunk_type}] {title}")
            if chunk_type == 'location':
                print(f"      位置: {meta.get('building')} {meta.get('floor')} {meta.get('room')}")
            print(f"      預覽: {doc[:80]}...")
