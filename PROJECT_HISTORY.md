# 📜 臺大校園行政小幫手開發歷程 (Project History)

本文件記錄了「臺大校園行政小幫手」從無到有的完整開發歷程，包含各階段的開發目標、遇到的挑戰以及解決方案。

## 📅 Phase 1: 基礎建設與爬蟲 (Initial Infrastructure)
**目標**：建立專案架構並獲取台大四大處室（教務處、學務處、圖書館、總務處）的原始資料。

- **架構設計**：決定採用 Python + Streamlit + RAG 的架構。
- **爬蟲開發** (`scrapers/`)：
    - 設計 `BaseScraper` 類別以統一爬蟲行為。
    - 針對各處室網頁結構（靜態 HTML、動態 AJAX）分別實作爬取邏輯。
    - 解決了 OGA (總務處) 網頁編碼與 Form 表單提交的問題。
    - 解決了 LIB (圖書館) 爬取範圍與內容解析的問題。
- **資料儲存**：將爬取結果統一儲存為 JSON 格式於 `data/` 目錄。

## 📅 Phase 2: 資料處理與索引 (Data Processing & Indexing)
**目標**：將非結構化的網頁資料轉化為 RAG 系統可用的向量索引。

- **資料清洗 (`processor.py`)**：
    - 去除 HTML 標籤、多餘空白與無意義字元。
    - 設計 Metadata 結構（包含 title, url, department, unit_name）。
- **切塊策略 (Chunking)**：
    - 使用 `RecursiveCharacterTextSplitter` 進行長文本切割。
    - **關鍵突破**：實作「Location Chunk」機制，特別針對含有地點資訊的文本建立獨立 Chunk，以提升地點回答的準確度。
- **向量化 (Embedding)**：
    - 選用 **BAAI/bge-m3** 作為 Embedding 模型，支援多語言與長文本。
    - 使用 **ChromaDB** 建立本地向量資料庫。

## 📅 Phase 3: RAG 引擎核心開發 (Core RAG Engine)
**目標**：打造能夠精準回答問題的檢索生成引擎。

- **RAG 架構實作 (`rag_engine.py`)**：
    - 整合 Gemini Pro API 作為生成模型。
    - 實作基本的檢索 (Retrieve) -> 增強 (Augment) -> 生成 (Generate) 流程。
- **雙階段檢索 (Two-Stage Retrieval)**：
    - **挑戰**：單純語意搜尋常無法區分不同單位的類似規定（例如多個單位都有「辦公室」）。
    - **解決方案**：開發 Two-Stage 機制。Stage 1 先找出相關「單位」，Stage 2 再鎖定該單位檢索細節。
- **GPU 加速支援**：
    - 修改 `config.py` 與 `indexer.py`，加入 CUDA 自動偵測功能，大幅縮短索引建立與檢索時間。

## 📅 Phase 4: 地圖服務整合 (Map Integration)
**目標**：在文字回答之外，提供直觀的地理位置資訊。

- **API 整合 (`map_service.py`)**：
    - 對接台大校園地圖 API。
    - 實作 `extract_buildings_from_metadata`，自動從檢索到的文件中提取建築物名稱。
- **前端顯示**：
    - 使用 `streamlit-folium` 將地圖嵌入聊天介面。
    - **優化**：解決了 Streamlit Rerun 導致地圖消失的問題（透過 `st.session_state` 保存地圖狀態）。

## 📅 Phase 5: UI/UX 全面優化 (Frontend Polish)
**目標**：打造現代化、親切且易用的使用者介面。

- **視覺改造**：
    - 更改 App 標題為「臺大校園行政小幫手【NTU Admin Helper】」。
    - 設定 Favicon 為 🌴 (Palm Tree)。
    - 設計自定義 CSS 來美化 API Key 狀態顯示 (置中、色塊)。
- **側邊欄重構**：
    - 導入 `st.dialog` (彈出視窗)，將 API Key 輸入與系統說明隱藏於按鈕後，釋放版面空間。
    - 重新排列元件順序：API 設定 -> 常見問題 -> 身分設定 -> 模型設定 -> 系統資訊。
- **快捷互動**：
    - 設計「😭好想停修」、「💰學生保險怎麼請」等生動的快捷按鈕，一鍵帶入查詢。
- **身分注入**：
    - 在側邊欄加入學院與學制選單，並將此資訊注入 System Prompt，讓 AI 回答更具針對性。

## 📅 Phase 6: 最終測試與交付 (Final Cleanup)
**目標**：確保系統穩定並移除開發痕跡。

- **全系統測試**：驗證 RAG 準確度、地圖顯示、UI 互動流程。
- **檔案清理**：
    - 移除所有 `debug_*.py`, `test*.py` 等 10+ 個暫存檔。
    - 移除舊版 indexer 腳本，保留單一入口 `indexer.py`。
- **文件產出**：
    - 更新 `README.md`。
    - 產出 `PROJECT_HISTORY.md` (本文件)。

---
*專案開發至此圓滿完成，感謝您的使用與測試！* 🎓
