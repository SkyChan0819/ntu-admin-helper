# 🎓 臺大校園行政小幫手【NTU Admin Helper】

**NTU Admin Helper** 是一個專為台灣大學師生設計的 AI 智能助手，基於 RAG (Retrieval-Augmented Generation) 技術，能夠精準回答關於 **教務處 (ACA)、學務處 (OSA)、圖書館 (LIB) 及總務處 (OGA)** 的各類行政流程與規章問題。

✨ **核心特色**：
- **Two-Stage Retrieval (雙階段檢索)**：獨家開發的檢索策略，先鎖定單位再找細節，有效解決跨文檔參照問題。
- **BGE-M3 & GPU 加速**：使用高效能的 BGE-M3 Embedding 模型，並支援 CUDA 自動加速。
- **Interactive Campus Map**：整合台大校園地圖 API，回答中提及地點時會自動繪製互動式地圖。
- **Smart Context Awareness**：將使用者身分（學院/學制）注入 System Prompt，提供客製化建議。

---

## 🚀 功能亮點 (Features)

### 1. 智慧問答與雙階段檢索
系統不僅是關鍵字比對，更採用 **Two-Stage Retrieval** 架構：
- **Stage 1 (Broad Search)**：掃描全域資料，識別相關行政單位（如：註冊組、課外組）。
- **Stage 2 (Targeted Retrieval)**：針對識別出的單位，深度挖掘其相關規章、地點與聯絡資訊。
這確保了當您問「我要申請休學」時，系統能精準關聯到註冊組的規定，而非其他單位的類似詞彙。

### 2. 用戶友善介面 (UI/UX)
- **⚡ 常見問題快選**：內建「😭好想停修」、「💰學生保險怎麼請」、「📄我要印成績單」、「📖圖書館到幾點」等快捷按鈕。
- **📍 地點可視化**：當 AI 發現地點資訊（如：行政大樓、總圖書館），會直接在地圖上標記給你看，且支援歷史紀錄保存。
- **📱 響應式側邊欄**：API Key 設定、身分選擇、系統說明皆整合於側邊欄，並採用彈出式視窗 (Dialog) 設計，保持介面清爽。

### 3. 技術優化
- **GPU Acceleration**：自動偵測環境，若有 NVIDIA GPU 則自動啟用 CUDA 加速 Embedding 計算。
- **Identity Injection**：根據您設定的學院（如醫學院）與學制（碩博/學士），AI 會優先提供適用的法規解釋。

---

## 🛠️ 專案結構

```text
📂 ntu-admin-helper/
├── 📄 app.py              # Streamlit 主程式 (Frontend & Controller)
├── 📄 rag_engine.py       # RAG 核心引擎 (Two-Stage Retrieval 邏輯)
├── 📄 map_service.py      # 地圖服務 (NTU Map API 整合)
├── 📄 processor.py        # 資料前處理與切塊 (Data Pipeline)
├── 📄 config.py           # 系統設定 (GPU 偵測、路徑設定)
├── 📄 indexer.py          # 索引建置工具 (Vector DB Builder)
├── 📂 data/               # 原始爬蟲資料與處理後 chunks
├── 📂 chroma_db/          # ChromaDB 向量資料庫實體
└── 📄 requirements.txt    # 專案依賴套件
```

---

## 💻 安裝與使用 (Installation & Usage)

### 1. 環境準備
建議使用 Python 3.10 以上版本。

```bash
# 1. Clone 專案
git clone https://github.com/your-repo/ntu-admin-helper.git
cd ntu-admin-helper

# 2. 安裝依賴
pip install -r requirements.txt
```

### 2. 建立索引 (First Setup)
初次使用前，需將資料向量化並寫入資料庫（若已提供 chroma_db 則可跳過）：

```bash
python indexer.py
```
*程式會自動偵測 GPU，若有 GPU 會大幅加速索引建立過程。*

### 3. 啟動應用程式
```bash
streamlit run app.py
```
啟動後瀏覽器會自動開啟，請在側邊欄輸入您的 **Google Gemini API Key** 即可開始對話！

---

## 🔍 技術細節

### RAG 流程
1. **Query Rewrite**：將使用者口語問題改寫為精確的檢索語句。
2. **Hybrid Search**：結合關鍵字搜尋與語意搜尋。
3. **Re-ranking**：對初步結果進行相關性排序，優先保留「單位資訊」與「流程說明」。
4. **Context Injection**：將篩選後的文本、使用者身分、地圖資訊一同送入 Gemini Pro 模型。
5. **Generation**：生成最終回答並附上來源連結。

### 聯絡我們
如有任何問題或建議，歡迎提出 Issue 或 Pull Request！

---
Built with ❤️ using **Streamlit**, **LangChain**, **ChromaDB**, and **Google Gemini**.
