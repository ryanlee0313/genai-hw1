import streamlit as st
import os
import uuid
from openai import OpenAI
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from tavily import TavilyClient

# 1. 初始化與環境變數
load_dotenv()

def get_secret(key):
    try: return st.secrets.get(key)
    except: return os.getenv(key)

KEYS = {
    "OpenAI": get_secret("OPENAI_API_KEY"),
    "Groq": get_secret("GROQ_API_KEY"),
    "Tavily": get_secret("TAVILY_API_KEY")
}
ENV_PASSWORD = get_secret("ADMIN_PASSWORD")

# --- 網頁配置 ---
st.set_page_config(page_title="AI Research Assistant", layout="wide", page_icon="🧠")

# --- 密碼保護 ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated and ENV_PASSWORD:
    st.title("🔐 系統存取保護")
    pwd_input = st.text_input("管理員密碼", type="password")
    if st.button("登入"):
        if pwd_input == ENV_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else: st.error("密碼錯誤")
    st.stop()

# --- 初始化 Session State ---
if "chat_sessions" not in st.session_state:
    initial_id = str(uuid.uuid4())
    st.session_state.chat_sessions = {initial_id: {"name": "新對話 1", "messages": []}}
    st.session_state.current_session_id = initial_id

# --- 側邊欄：功能面板 ---
with st.sidebar:
    st.title("🚀 控制中心")
    
    if st.button("➕ 新增新對話", use_container_width=True):
        new_id = str(uuid.uuid4())
        st.session_state.chat_sessions[new_id] = {"name": f"新對話 {len(st.session_state.chat_sessions)+1}", "messages": []}
        st.session_state.current_session_id = new_id
        st.rerun()

    # 1. 對話切換列表
    st.subheader("歷史對話")
    for sid, data in st.session_state.chat_sessions.items():
        if st.button(data["name"], key=sid, use_container_width=True, 
                     type="primary" if sid == st.session_state.current_session_id else "secondary"):
            st.session_state.current_session_id = sid
            st.rerun()

    st.divider()

    # 2. 模型與搜尋設定
    provider = st.selectbox("供應商", ["Groq (LPU)", "OpenAI"])
    model_id = st.selectbox("模型", ["llama-3.3-70b-versatile"] if provider == "Groq (LPU)" else ["gpt-4o", "gpt-4o-mini", "o3-mini"])
    
    enable_search = st.checkbox("🔍 開啟網頁搜尋 (Tavily)")
    
    # 3. 檔案上傳 (功能 1)
    st.subheader("📂 文件分析")
    uploaded_file = st.file_uploader("上傳 PDF 或 TXT", type=["pdf", "txt"])
    file_context = ""
    if uploaded_file:
        if uploaded_file.type == "application/pdf":
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                file_context += page.extract_text()
        else:
            file_context = uploaded_file.read().decode("utf-8")
        st.success("檔案已讀取！")

    st.divider()
    sys_prompt = st.text_area("System Prompt", value="你是一個專業助理。如果使用者有提供文件內容，請優先根據文件回答。")
    temp = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)

    # 4. 對話導出 (功能 2)
    st.subheader("📥 匯出紀錄")
    current_session = st.session_state.chat_sessions[st.session_state.current_session_id]
    if current_session["messages"]:
        chat_log = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in current_session["messages"]])
        st.download_button("💾 下載 .txt 檔", data=chat_log, file_name=f"{current_session['name']}.txt", use_container_width=True)

    if st.button("🗑️ 刪除此對話", use_container_width=True):
        if len(st.session_state.chat_sessions) > 1:
            del st.session_state.chat_sessions[st.session_state.current_session_id]
            st.session_state.current_session_id = list(st.session_state.chat_sessions.keys())[0]
            st.rerun()

# --- 主要聊天區 ---
st.title(f"💬 {current_session['name']}")

# 功能 5: 透過 CSS 優化程式碼高亮與介面
st.markdown("""
<style>
    .stChatMessage { border-radius: 10px; margin-bottom: 10px; }
    code { color: #ebdbb2; background-color: #282828 !important; padding: 2px 5px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

for m in current_session["messages"]:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("詢問任何事..."):
    current_session["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        
        # 功能 4: 網頁搜尋邏輯
        search_result = ""
        if enable_search and KEYS["Tavily"]:
            with st.status("正在搜尋網頁...", expanded=False):
                tavily = TavilyClient(api_key=KEYS["Tavily"])
                search_data = tavily.search(query=prompt, search_depth="advanced")
                search_result = "\n".join([f"來源: {r['url']}\n內容: {r['content']}" for r in search_data['results']])
                st.write("搜尋完成，正在整理資訊...")

        try:
            active_key = KEYS["Groq"] if provider == "Groq (LPU)" else KEYS["OpenAI"]
            base_url = "https://api.groq.com/openai/v1" if provider == "Groq (LPU)" else None
            client = OpenAI(api_key=active_key, base_url=base_url)

            # 組合上下文 (包含文件內容與搜尋結果)
            final_prompt = prompt
            if file_context:
                final_prompt = f"【參考文件內容】：\n{file_context[:5000]}\n\n---\n【使用者問題】：{prompt}"
            if search_result:
                final_prompt = f"【網頁搜尋結果】：\n{search_result}\n\n---\n{final_prompt}"

            history = [{"role": "system", "content": sys_prompt}] + \
                      [{"role": m["role"], "content": m["content"]} for m in current_session["messages"][-5:]]
            # 更新最後一則訊息包含搜尋與文件內容
            history[-1]["content"] = final_prompt

            stream = client.chat.completions.create(model=model_id, messages=history, temperature=temp, stream=True)
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    placeholder.markdown(full_response + "▌")

            placeholder.markdown(full_response)
            current_session["messages"].append({"role": "assistant", "content": full_response})
            if len(current_session["messages"]) <= 2:
                current_session["name"] = prompt[:10]
            st.rerun()

        except Exception as e:
            st.error(f"錯誤：{str(e)}")