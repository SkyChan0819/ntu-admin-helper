# 🏗️ 專案架構表 (Project Structure)

## 📁 檔案目錄結構 (Directory Structure)

```text
NTU-ADMIN-HELPER/
├── 📄 app.py*                 [核心] 前端入口 (Streamlit GUI) 與 主控制器
├── 📄 rag_engine.py*          [核心] RAG 檢索引擎 (Two-Stage Retrieval 邏輯)
├── 📄 map_service.py*         [核心] 地圖服務 (整合 NTU Map API)
├── 📄 processor.py            [工具] 資料處理器 (清洗、切塊、Metadata 提取)
├── 📄 indexer.py              [工具] 索引建置器 (Vector DB Indexing)
├── 📄 config.py               [設定] 全域參數 (API Key, GPU, 路徑)
├── 📄 requirements.txt        [設定] 專案依賴套件清單
├── 📄 list_models.py          [工具] Gemini 模型列表檢測工具
│
├── 📂 data/                   [資料] 資料倉儲
│   ├── 📂 raw/                (爬蟲原始 HTML/JSON)
│   └── 📄 processed_chunks.json (處理後的向量化前文本塊)
│
├── 📂 chroma_db/              [資料] 向量資料庫實體 (Vector DB)
│   ├── 📄 chroma.sqlite3      (ChromaDB SQLite 資料檔)
│   └── 📂 ...                 (ChromaDB 索引檔)
│
├── 📄 README.md               [文件] 專案說明文件
├── 📄 PROJECT_HISTORY.md      [文件] 專案開發歷程
└── 📄 PROJECT_STRUCTURE.md    [文件] 本檔案
```

---

## 🧩 系統模組架構 (Module Architecture)

| 模組分類 (Layer) | 檔案名稱 | 核心職責 (Responsibilities) | 關鍵技術 (Tech Stack) |
| :--- | :--- | :--- | :--- |
| **前端應用層**<br>(Frontend & Controller) | **`app.py`** | 1. **使用者介面**：聊天視窗、側邊欄、彈出視窗<br>2. **流程控制**：接收輸入 -> 呼叫 RAG -> 顯示結果<br>3. **狀態管理**：Session State (API Key, 地圖歷史) | Streamlit, Streamlit-Folium |
| **檢索核心層**<br>(RAG Engine) | **`rag_engine.py`** | 1. **Query Processing**：使用者意圖分析<br>2. **Two-Stage Retrieval**：第一階段(廣搜) -> 第二階段(精搜)<br>3. **Generation**：整合 Context 並呼叫 Gemini 生成回答 | Google Gemini Pro, ChromaDB |
| **外部服務層**<br>(External Services) | **`map_service.py`** | 1. **地點提取**：從文本中辨識建築物名稱<br>2. **座標查詢**：對接台大校園地圖 API<br>3. **地圖繪製**：產生含標記的互動式地圖 | Folium, Requests |
| **資料管線層**<br>(Data Pipeline) | **`processor.py`** | 1. **資料清洗**：去除雜訊、正規化文本<br>2. **智能切塊**：Recursive Chunking + Location Chunking<br>3. **Metadata 標註**：提取單位、標題、URL | LangChain Text Splitters |
| **基礎設施層**<br>(Infrastructure) | **`indexer.py`** | 1. **Embedding 計算**：將文本塊轉為向量<br>2. **向量儲存**：寫入 ChromaDB<br>3. **硬體加速**：自動偵測並調用 NVIDIA GPU | BAAI/bge-m3, PyTorch, ChromaDB |
| **配置設定層**<br>(Configuration) | **`config.py`** | 1. **環境變數管理**<br>2. **模型載入策略** (CPU vs GPU)<br>3. **路徑定義** | Python os, dotenv |

---

## 🔄 資料流向 (Data Flow)

1. **Preprocessing (離線處理)**：
   `Raw Data` -> `processor.py` -> `Chunks` -> `indexer.py` (GPU Embedding) -> `ChromaDB`

2. **Run-time (即時問答)**：
   `User API` -> `app.py` -> `rag_engine.py` -> `ChromaDB (Retrieval)` -> `Core Logic (Rerank)` -> `Gemini API (Generation)` -> `app.py` (Display)
   *(若含地點)* -> `map_service.py` -> `app.py` (Map Render)
