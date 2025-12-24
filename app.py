import streamlit as st

# Fix for Streamlit Cloud (ChromaDB requires SQLite > 3.35)
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import chromadb
import google.generativeai as genai
import os
import time
import gc

# Import config with fallback
try:
    from config import GEMINI_API_KEY, GEMINI_MODEL, BGEEmbeddingFunction
except ImportError:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-pro"
    BGEEmbeddingFunction = None  # Handle missing import gracefully

from rag_engine import EnhancedRAGEngine  # Import new RAG engine
from map_service import get_map_service  # Import map service
from streamlit_folium import st_folium  # Import folium integration

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="臺大校園行政小幫手【NTU Admin Helper】",
    page_icon="🌴",
    layout="wide"
)

# --- INIT ---
DB_PATH = "./chroma_db"
COLLECTION_NAME = "ntu_assistant"

@st.cache_resource
def get_rag_engine():
    """Initialize Enhanced RAG Engine with Two-Stage Retrieval"""
    try:
        print("DEBUG: get_rag_engine() called. Initializing BGEEmbeddingFunction...")
        # Pass the specific embedding function to ensure dimension match (1024 for BGE-M3)
        ef = BGEEmbeddingFunction() if BGEEmbeddingFunction else None
        print(f"DEBUG: BGEEmbeddingFunction initialized: {ef is not None}")
        
        print(f"DEBUG: Initializing EnhancedRAGEngine with DB_PATH={DB_PATH}...")
        engine = EnhancedRAGEngine(
            db_path=DB_PATH, 
            collection_name=COLLECTION_NAME,
            embedding_function=ef
        )
        print("DEBUG: EnhancedRAGEngine initialized successfully.")
        return engine
    except Exception as e:
        print(f"ERROR: RAG Engine Initialization failed: {e}")
        st.error(f"RAG 引擎初始化失敗: {e}")
        return None

@st.cache_resource
def get_map_service_cached():
    """Initialize and cache map service"""
    return get_map_service()

def retrieve_documents(engine, query, use_two_stage=True):
    """Retrieve documents using Enhanced RAG Engine
    
    Args:
        engine: EnhancedRAGEngine instance
        query: User query
        use_two_stage: Whether to use two-stage retrieval (default: True)
    
    Returns:
        Retrieved documents with metadata
    """
    results = engine.retrieve(query, use_two_stage=use_two_stage)
    return results

def rewrite_query_with_context(api_key, model_name, messages, current_query):
    """Rewrite the query using recent dialogue context."""
    if not api_key:
        return current_query
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    recent = messages[-6:]  # last 3 turns (user+assistant)
    dialogue = []
    for msg in recent:
        role = "使用者" if msg["role"] == "user" else "助理"
        dialogue.append(f"{role}: {msg['content']}")
    dialogue_text = "\n".join(dialogue).strip()

    prompt = f"""請將使用者的問題改寫為**完整、可獨立檢索**的查詢句。
要求：
1. 必須結合最近對話上下文（包含助理回答），補全代詞與單位名稱。
2. 不要加入對話中不存在的新資訊。
3. 只輸出改寫後的查詢句，勿加註解。

【最近對話】
{dialogue_text}

【使用者最新問題】
{current_query}
"""
    try:
        response = model.generate_content(prompt)
        rewritten = response.text.strip()
        return rewritten if rewritten else current_query
    except Exception:
        return current_query

def generate_response(api_key, model_name, query, context_docs, user_identity=""):
    """Generate answer using Gemini Pro"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    
    # Build location hints from retrieved metadata
    location_lines = []
    seen_locations = set()
    for meta in context_docs.get('metadatas', [[]])[0]:
        if meta.get('type') == 'location':
            building = meta.get('building', '')
            floor = meta.get('floor', '')
            room = meta.get('room', '')
            unit = meta.get('unit_name') or meta.get('title', '')
            location_text = f"{building} {floor} {room}室".strip()
            if not location_text:
                continue
            line = f"- {unit}：{location_text}" if unit else f"- {location_text}"
            if line not in seen_locations:
                seen_locations.add(line)
                location_lines.append(line)

    # Prepare Context (limit to first 500 chars per doc to avoid token overflow)
    context_text = ""
    for idx, doc in enumerate(context_docs['documents'][0]):
        meta = context_docs['metadatas'][0][idx]
        title = meta.get('title', '無標題')
        url = meta.get('url', '#')
        # Truncate long documents
        doc_preview = doc[:500] + "..." if len(doc) > 500 else doc
        context_text += f"\n--- 資料來源 {idx+1}: [{title}]({url}) ---\n{doc_preview}\n"

    # Strict System Prompt
    location_hint = ""
    if location_lines:
        location_hint = "【辦理地點（若適用）】\n" + "\n".join(location_lines) + "\n\n"

    # Identity Context Injection
    identity_instruction = ""
    if user_identity:
        identity_instruction = f"""
【使用者身分資訊】
{user_identity}
請務必根據上述使用者身分（學院/學制），優先提供適用的規定或流程。若不同身分有不同規定，請明確指出。
"""

    prompt = f"""你是一個專業的「台大行政小助手」。請根據以下提供的【參考資料】來回答使用者的問題。

【回答守則】
1. 你的回答必須**嚴格基於**提供的參考資料。如果參考資料沒有提及，請直接說「抱歉，目前的資料庫中沒有相關資訊」。
2. 若參考資料中有辦理地點資訊，請在回答開頭以「辦理地點：」列出（可多筆）。
3. 回答請條理分明，使用點列式整理重點。
4. 語氣請保持親切、專業。
5. 請使用繁體中文回答。
{identity_instruction}

【參考資料】
{location_hint}
{context_text}

【使用者問題】
{query}
"""
    
    def _safe_get_text(resp):
        """Safely extract text from Gemini response without throwing."""
        try:
            return resp.text
        except Exception:
            pass
        try:
            if resp.candidates:
                content = resp.candidates[0].content
                if content and content.parts:
                    return "".join([part.text for part in content.parts if getattr(part, "text", None)])
        except Exception:
            pass
        return ""

    import time
    from google.api_core import exceptions

    if not api_key:
        return "⚠️ 請先在側邊欄輸入 Gemini API Key 以啟用 AI 回答功能。", context_docs
        
    # Retry logic for Quota Exceeded (429)
    max_retries = 3
    retry_delay = 5  # Initial delay
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            answer = _safe_get_text(response)
            if answer:
                if location_lines:
                    location_block = "辦理地點：\n" + "\n".join(location_lines) + "\n\n"
                    answer = location_block + answer
                return answer, context_docs
            # If answer is empty but no exception, return custom message or break to fail
            break 
        except exceptions.ResourceExhausted as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                st.warning(f"⚠️ 請求次數過多 (Quota Exceeded)，正在等待 {wait_time} 秒後重試... (嘗試 {attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                return f"抱歉，請求次數已達上限 ({str(e)})。請稍後再試或檢查您的 API Key 配額。", context_docs
        except Exception as e:
             # Other errors, fail immediately or handle appropriately
             error_msg = f"生成回答時發生錯誤: {str(e)}"
             return f"抱歉，系統遇到問題：{error_msg}\n\n請稍後再試或聯繫管理員。", context_docs
    
    return "抱歉，AI 模型未能生成回答。請嘗試重新提問或簡化問題。", context_docs

# --- UI LAYOUT ---
st.title("🎓 臺大校園行政小幫手【NTU Admin Helper】")
st.markdown("我是你的專屬助手，可以回答關於 **教務處 (ACA)、學務處 (OSA)、圖書館 (LIB)、總務處 (OGA)** 的各類行政問題！")

# --- Session State Config ---
if "user_api_key" not in st.session_state:
    st.session_state.user_api_key = GEMINI_API_KEY

@st.dialog("🔑 設定 Gemini API Key")
def api_key_dialog():
    st.write("請輸入您的 Google Gemini API Key 以啟用完整功能。")
    new_key = st.text_input(
        "API Key", 
        value=st.session_state.user_api_key, 
        type="password",
        help="從 Google AI Studio 獲取"
    )
    if st.button("確認儲存"):
        st.session_state.user_api_key = new_key
        st.rerun()

@st.dialog("ℹ️ 系統資訊與說明")
def system_info_dialog():
    st.header("💡 關於本系統")
    st.success("✨ BGE-M3 本地檢索：使用高效能向量模型，保障檢索準確度。")
    st.success("🔗 Two-Stage Retrieval：獨家雙階段檢索技術，先鎖定單位再找細節。")
    st.success("🤖 Gemini 智能回答：整合 Google Gemini Pro，提供流暢的語言生成。")

    st.divider()

    st.header("🛠️ 技術架構：Two-Stage Retrieval")
    st.info("""
    **Two-Stage Retrieval (雙階段檢索)** 是一種針對行政問答優化的策略：

    1.  **第一階段 (Stage 1)**：
        *   **目標**：快速掃描全域資料庫。
        *   **動作**：找出與問題最相關的 5 筆資料，並分析其中提到的「行政單位名稱」(如註冊組、課外組)。
        
    2.  **第二階段 (Stage 2)**：
        *   **目標**：深度挖掘特定單位的資訊。
        *   **動作**：強制鎖定第一階段找到的單位，額外檢索該單位的「地點」、「電話」、「詳細規章」。
        
    🎯 **優點**：解決了「跨文檔參照」的問題。例如當你問「註冊組在哪？」，系統能精準關聯到註冊組的位置資訊，而不會被其他單位的文章干擾。
    """)

    st.divider()

    st.header("📍 地圖服務")
    st.markdown("""
    本系統整合了 **台大校園地圖 API**。
    當您的問題包含「在哪裡」、「位置」等關鍵字時，系統會自動：
    1. 分析回答中提到的建築物 (如：行政大樓)。
    2. 抓取該建築物的經緯度。
    3. 在回答下方直接繪製互動式地圖。
    """)



# --- Chat Logic Function ---
def handle_query(query_text):
    """
    Handle user query: display message, retrieve context, generate answer, and update history.
    """
    # Use session state for context variables (safe access before sidebar render)
    college_opt = st.session_state.get("college_opt", "其他學院 (一般)")
    degree_opt = st.session_state.get("degree_opt", "學士班")
    model_name = st.session_state.get("model_name", GEMINI_MODEL)
    api_key_val = st.session_state.get("user_api_key", "")

    # 1. Display User Message
    with st.chat_message("user"):
        st.markdown(query_text)
    st.session_state.messages.append({"role": "user", "content": query_text})

    # 2. Assistant Logic
    with st.chat_message("assistant"):
        with st.spinner("正在智慧檢索中...(使用 Two-Stage Retrieval)"):
            engine = get_rag_engine()
            if engine:
                # Construct Context-Aware Query
                context_suffix = ""
                if college_opt == "醫學院/公共衛生學院":
                    context_suffix += " (醫學院/公衛學院規定)"
                
                context_suffix += f" ({degree_opt})"
                
                # Construct identity string for LLM
                user_identity_str = f"- 學院：{college_opt}\n- 學制：{degree_opt}"
                
                # 1. Rewrite with context (last 3 turns)
                rewritten_prompt = rewrite_query_with_context(
                    api_key_val,
                    model_name,
                    st.session_state.messages,
                    query_text
                )
                
                # Combine rewritten conversational query with filter context
                final_search_query = f"{rewritten_prompt} {context_suffix}"
                
                print(f"DEBUG: Final Search Query: {final_search_query}")
                print(f"DEBUG: User Identity: {user_identity_str}")
                
                # 2. Retrieve using Enhanced RAG Engine
                print("DEBUG: Starting retrieval...")
                results = retrieve_documents(engine, final_search_query, use_two_stage=True)
                print("DEBUG: Retrieval complete. Results found:", len(results.get('documents', [[]])[0]))
                
                # 3. Generate
                if api_key_val:
                    print(f"DEBUG: Generating response with model {model_name}...")
                    # Pass identity context
                    answer, sources = generate_response(
                        api_key_val, 
                        model_name, 
                        query_text, 
                        results,
                        user_identity=user_identity_str
                    )
                    print("DEBUG: Generation complete.")
                else:
                    answer = "⚠️ 請先在側邊欄輸入 Gemini API Key 以啟用 AI 回答功能"
                    sources = results
                
                # 4. Show Answer
                st.markdown(answer)
                
                # 5. Extract Map Data
                print("DEBUG MAP: Starting automatic map generation")
                map_service = get_map_service_cached()
                
                documents = []
                for idx in range(len(sources['documents'][0])):
                    documents.append({
                        'content': sources['documents'][0][idx],
                        'metadata': sources['metadatas'][0][idx]
                    })
                
                buildings_found = map_service.extract_buildings_from_metadata(documents)
                print(f"DEBUG MAP: Buildings extracted: {buildings_found}")
                
                # Display map IMMEDIATELY for this turn
                if buildings_found:
                    st.divider()
                    st.subheader("📍 相關位置地圖")
                    campus_map = map_service.create_map(buildings_found)
                    if campus_map:
                        # Use a special key to avoid conflicts
                        st_folium(campus_map, width=700, height=500, key=f"current_map_{int(time.time())}")
                        st.caption(f"顯示 {len(buildings_found)} 個建築物: {', '.join(buildings_found)}")
                    else:
                        st.info("💡 建築物座標資訊不完整，無法顯示地圖")
                
                # 6. Show Sources
                with st.expander("查看參考來源"):
                     for idx, meta in enumerate(sources['metadatas'][0]):
                        st.markdown(f"**{idx+1}. [{meta.get('title')}]({meta.get('url')})**")
                        st.caption(f"來自: {meta.get('department').upper()}")

                # Save to history INCLUDING buildings
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": answer,
                    "sources": sources,
                    "buildings": buildings_found
                })
                
                # Force Garbage Collection
                gc.collect()

# Sidebar
with st.sidebar:
    # 1. API Key (Popout Dialog)
    st.header("🔑 API 設定")
    
    if st.button("設定 Gemini API Key", use_container_width=True, icon="⚙️"):
        api_key_dialog()
            
    if st.session_state.user_api_key:
        st.markdown(
            """
            <div style='background-color: #d1e7dd; color: #0f5132; padding: 0.75rem 1rem; border-radius: 0.375rem; text-align: center; margin-bottom: 1rem; font-weight: bold;'>
                ✅ API Key 已啟用 ✅
            </div>
            """, 
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div style='background-color: #f8d7da; color: #842029; padding: 0.75rem 1rem; border-radius: 0.375rem; text-align: center; margin-bottom: 1rem; font-weight: bold;'>
                ❌ API Key 未設定 ❌
            </div>
            """,
            unsafe_allow_html=True
        )

    # Update global variable for downstream use
    user_api_key = st.session_state.user_api_key

    st.divider()

    # 2. Common Questions (Moved to Top)
    st.header("💡 常見問題快選")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("😭好想停修"):
            st.session_state.pending_query = "如何辦理停修課程？"
        if st.button("💰學生保險怎麼請"):
            st.session_state.pending_query = "如何申請學生團體保險理賠？"
    with col2:
        if st.button("📄我要印成績單"):
            st.session_state.pending_query = "如何申請中文成績單？"
        if st.button("📖圖書館到幾點"):
            st.session_state.pending_query = "總圖書館開放時間為何？"

    st.divider()

    # 3. Identity Settings
    st.header("👤 身分設定")
    college_option = st.selectbox(
        "學院別",
        ["其他學院 (一般)", "醫學院/公共衛生學院"],
        index=0,
        help="醫學院與公衛學院之教務規定可能有所不同",
        key="college_opt"
    )
    degree_option = st.selectbox(
        "學制別",
        ["學士班", "碩士班", "博士班"],
        index=0,
        key="degree_opt"
    )

    st.divider()

    # 4. Model Selection
    st.header("🤖 模型設定")
    user_model_name = st.text_input(
        "Gemini Model Name",
        value=GEMINI_MODEL,
        help="例如: gemini-1.5-flash, gemini-2.0-flash",
        key="model_name"
    )

    if st.button("列出可用模型"):
        if not user_api_key:
            st.error("請先輸入 API Key")
        else:
            try:
                genai.configure(api_key=user_api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                st.success(f"找到 {len(models)} 個可用模型:")
                st.write(models)
            except Exception as e:
                st.error(f"查詢失敗: {e}")

    st.divider()
    if st.button("ℹ️ 系統資訊", use_container_width=True):
        system_info_dialog()

    st.divider()
    
    # 5. Optimization Settings
    st.header("🚀 效能優化")
    if st.button("🗑️ 清除對話紀錄", use_container_width=True):
        st.session_state.messages = []
        st.experimental_rerun()
        
    show_history_maps = st.toggle(
        "顯示歷史地圖", 
        value=False, 
        help="開啟後會顯示歷史訊息中的互動地圖（較吃資源）。關閉可避免應用程式卡頓。"
    )

# Handle Sidebar Button Clicks (Main Area Output)
if "pending_query" in st.session_state and st.session_state.pending_query:
    handle_query(st.session_state.pending_query)
    st.session_state.pending_query = None  # Reset

# Chat Interface
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Chat History
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Restore Map from History
        if "buildings" in message and message["buildings"]:
            st.caption(f"📍 相關位置: {', '.join(message['buildings'])}")
            
            # Only render map if toggle is ON
            if show_history_maps:
                try:
                    map_service = get_map_service_cached()
                    historical_map = map_service.create_map(message["buildings"], center_on_first=True)
                    if historical_map:
                        st_folium(historical_map, width=700, height=400, key=f"history_map_{idx}")
                except Exception as e:
                    st.error(f"無法載入地圖: {e}")
            else:
                 st.caption("(已隱藏地圖以節省資源，請至側邊欄開啟「顯示歷史地圖」)")

        # Show specific sources if available
        if "sources" in message:
            with st.expander("查看參考來源"):
                for s_idx, meta in enumerate(message["sources"]['metadatas'][0]):
                    st.markdown(f"**{s_idx+1}. [{meta.get('title')}]({meta.get('url')})**")
                    st.caption(f"來自: {meta.get('department').upper()}")

# User Input
if prompt := st.chat_input("請輸入你的問題 (例如：休學要怎麼申請？)"):
    handle_query(prompt)


