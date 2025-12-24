# -*- coding: utf-8 -*-
"""
Configuration and Utilities for NTU Administrative Assistant
台大行政小助手設定檔與工具函數
"""
import os
import chromadb
from chromadb.config import Settings
# Delay import of SentenceTransformer until actually needed to avoid
# requiring the heavy dependency at module import time.
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # For type hints only; avoid importing at runtime.
    from sentence_transformers import SentenceTransformer

# ========== 設定參數 ==========

# Gemini API Key (可透過環境變數或直接設定)
# 請在此輸入您的 API Key 或設定環境變數 GEMINI_API_KEY
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ChromaDB 設定
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "ntu_assistant"

# BGE-M3 模型設定 (1024 維度)
EMBEDDING_MODEL = "BAAI/bge-m3"  # BGE-M3 model for 1024-dim embeddings (matches ChromaDB)

# Gemini 模型設定 (嘗試使用 Flash Latest 版本以獲得更好的配額)
GEMINI_MODEL = "gemini-flash-latest"


# ========== ChromaDB 工具函數 ==========

def get_chroma_client(db_path: str = None) -> chromadb.PersistentClient:
    """
    取得 ChromaDB 客戶端實例
    
    Args:
        db_path: 資料庫路徑，預設使用 CHROMA_DB_PATH
        
    Returns:
        ChromaDB PersistentClient 實例
    """
    if db_path is None:
        db_path = CHROMA_DB_PATH
    
    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(anonymized_telemetry=False)
    )
    return client


# ========== Embedding 模型快取 ==========

@lru_cache(maxsize=1)
def get_embedding_model() -> "SentenceTransformer":
    """
    取得 BGE-M3 embedding 模型（全域快取）
    
    Returns:
        SentenceTransformer 模型實例
    """
    # Import inside function to avoid import-time dependency requirement
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "cpu"
        
    print(f"Loading embedding model: {EMBEDDING_MODEL} on {device}...")
    from sentence_transformers import SentenceTransformer
    # Initialize model with detected device
    model = SentenceTransformer(EMBEDDING_MODEL, device=device)
    print(f"Embedding model loaded successfully ({device})!")
    return model


class BGEEmbeddingFunction:
    """BGE-M3 Embedding Function for ChromaDB

    Chromadb expects the embedding function to provide a callable
    `name()` method (not a string attribute). Also requires
    `embed_query` and `embed_documents` methods for ChromaDB 0.4+.
    """

    def name(self) -> str:
        return "bge-m3"

    def __init__(self):
        self.model = get_embedding_model()

    def __call__(self, input: list) -> list:
        embeddings = self.model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()
    
    def embed_query(self, input) -> list:
        """Embed query (required by ChromaDB 0.4+)
        
        ChromaDB may pass either a single string or a list of strings.
        """
        # Handle both string and list inputs
        if isinstance(input, str):
            texts = [input]
        else:
            texts = input
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        # Return single embedding if single input, otherwise list
        if isinstance(input, str):
            return embeddings[0].tolist()
        return embeddings.tolist()
    
    def embed_documents(self, input: list) -> list:
        """Embed a list of documents (required by ChromaDB 0.4+)"""
        embeddings = self.model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()

