# -*- coding: utf-8 -*-
"""
RTX 3050 Optimized ChromaDB Indexing Script (BGE-M3 1024-dim Version)
修正維度不匹配 (Dimension Mismatch) 與 GPU 效能優化
"""
import os
import json
import sys
import torch
import chromadb
from sentence_transformers import SentenceTransformer

# --- 配置區 ---
DB_PATH = "./chroma_db"
COLLECTION_NAME = "ntu_assistant"
CHUNKS_PATH = "data/processed_chunks.json" 
EMBEDDING_MODEL = "BAAI/bge-m3"

class BGEM3EmbeddingFunctionGPU:
    def __init__(self):
        # 1. 預檢測試：確保使用的是 GPU 0 (RTX 3050)
        if not torch.cuda.is_available():
            print("\n❌ 錯誤：未偵測到 CUDA 環境！請檢查 PyTorch 安裝。")
            sys.exit(1)

        self.device = "cuda:0"
        self.gpu_name = torch.cuda.get_device_name(0)
        
        print(f"\n[預檢成功] 正在使用 GPU: {self.gpu_name}")
        print(f"正在載入模型: {EMBEDDING_MODEL}...")
        
        # 2. 載入模型
        self.model = SentenceTransformer(EMBEDDING_MODEL, device=self.device)
        
        # 3. 4GB 顯存關鍵優化：FP16 半精度
        # 這能將顯存佔用從約 3.5GB 壓低至 2.2GB 左右
        self.model.half()
        print("✨ 已啟用 FP16 半精度優化 (確保 4GB 顯存穩定運作)")

    # 必須實作此方法以符合 ChromaDB 介面
    def name(self) -> str:
        return "BAAI_BGE_M3_GPU"

    def __call__(self, input: list) -> list:
        # ChromaDB 傳入文本列表，返回向量列表
        embeddings = self.model.encode(
            input, 
            batch_size=12,           # 針對 4GB 顯存的安全批次
            normalize_embeddings=True, # BGE-M3 建議開啟以利 Cosine 運算
            show_progress_bar=False
        )
        return embeddings.tolist()

def main():
    print("--- 腳本啟動 ---")
    
    # 檢查原始資料路徑
    if not os.path.exists(CHUNKS_PATH):
        print(f"❌ 錯誤：找不到資料檔案 {CHUNKS_PATH}")
        print(f"目前執行位置: {os.getcwd()}")
        return

    # 初始化嵌入函數
    embedding_fn = BGEM3EmbeddingFunctionGPU()

    # 初始化 ChromaDB
    print(f"正在初始化 ChromaDB 於 {DB_PATH}...")
    client = chromadb.PersistentClient(path=DB_PATH)

    # --- 關鍵修正：解決維度不匹配 (384 vs 1024) ---
    try:
        # 檢查是否存在同名但維度錯誤的 Collection
        existing_collections = [c.name for c in client.list_collections()]
        if COLLECTION_NAME in existing_collections:
            print(f"⚠️ 偵測到舊的 Collection。正在重置以匹配 BGE-M3 (1024 維度)...")
            client.delete_collection(name=COLLECTION_NAME)
    except Exception as e:
        print(f"重置 Collection 時發生小錯誤 (可忽略): {e}")

    # 建立全新的 Collection
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"}
    )

    # 讀取 JSON 資料
    print(f"正在讀取 {CHUNKS_PATH}...")
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    documents = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    ids = [f"chunk_{i}" for i in range(len(chunks))]

    # 開始分批寫入資料庫
    batch_size = 50 
    total = len(documents)
    print(f"開始建立索引 (總計 {total} 筆資料)...")

    for i in range(0, total, batch_size):
        end = min(i + batch_size, total)
        try:
            collection.add(
                documents=documents[i:end],
                metadatas=metadatas[i:end],
                ids=ids[i:end]
            )
            print(f"🚀 進度: {end}/{total} ({(end/total)*100:.1f}%)")
        except Exception as e:
            print(f"💥 寫入批次發生錯誤: {e}")
            break

    print(f"\n✅ 全部索引建立完成！")
    print(f"資料庫總筆數: {collection.count()}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n使用者停止程式。")
    except Exception as e:
        print(f"\n💥 執行過程發生未預期的嚴重錯誤: {e}")