
"""OpsDesk Agent - Streamlit frontend.

Stage 4.2.1: Enterprise knowledge question answering.
"""

import os

import requests
import streamlit as st


API_BASE_URL = os.getenv(
    "OPSDESK_API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


st.set_page_config(
    page_title="OpsDesk Agent",
    page_icon="🛠️",
    layout="wide",
)


def check_backend():
    """Check whether FastAPI is available."""

    try:
        response = requests.get(
            f"{API_BASE_URL}/health",
            timeout=5,
        )
        response.raise_for_status()

        return response.json().get("status") == "ok"

    except (requests.RequestException, ValueError):
        return False


def ask_knowledge(question, k=3):
    """Call the existing FastAPI RAG endpoint."""

    response = requests.post(
        f"{API_BASE_URL}/api/knowledge/ask",
        json={
            "question": question,
            "k": k,
        },
        timeout=(5, 240),
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"知识问答接口返回 HTTP {response.status_code}"
        )

    data = response.json()

    if not isinstance(data.get("answer"), str):
        raise ValueError("API 返回的回答格式不正确")

    return data


def show_sources(message):
    """Display cited documents and retrieved candidates."""

    cited_sources = message.get("cited_sources", [])
    sources = message.get("sources", [])

    if cited_sources:
        with st.expander("📚 回答引用来源"):
            for item in cited_sources:
                st.write(
                    f"{item['label']}  {item['source']}"
                )

    if sources:
        with st.expander("🔎 本次检索候选资料"):
            for item in sources:
                st.write(
                    f"{item['label']}  {item['source']}"
                )


# Initialize conversation history.
if "messages" not in st.session_state:
    st.session_state.messages = []


# Sidebar.
with st.sidebar:
    st.title("🛠️ OpsDesk Agent")

    st.caption("企业 IT 智能服务助手")

    st.divider()

    st.subheader("系统状态")

    backend_ready = check_backend()

    if backend_ready:
        st.success("FastAPI 服务已连接")
    else:
        st.error("FastAPI 服务未连接")

    st.caption(f"API: {API_BASE_URL}")

    st.divider()

    st.subheader("知识检索设置")

    top_k = st.slider(
        "检索文档数量",
        min_value=1,
        max_value=5,
        value=3,
    )

    st.divider()

    if st.button(
        "清空对话",
        use_container_width=True,
    ):
        st.session_state.messages = []
        st.rerun()


# Main content.
st.title("💬 企业 IT 智能知识助手")

st.caption(
    "基于 Qwen3 + BGE-M3 + Chroma 的本地 RAG 问答系统"
)

st.info(
    "你可以询问 VPN、账号锁定、Wi-Fi 等 IT 问题。"
    "所有企业资料均为演示知识库内容。"
)



# -------- Display conversation history --------

messages = st.session_state.messages

for message in messages:

    with st.chat_message(message["role"]):

        status = message.get("status")

        if status == "pending":
            st.info("⏳ 正在生成回答，尚未完成。")

        elif status == "error":
            st.error(message["content"])

        else:
            st.markdown(message["content"])

            if message["role"] == "assistant":
                show_sources(message)


# -------- Recover an older unfinished question --------

if messages and messages[-1]["role"] == "user":

    st.warning("检测到上一条问题没有保存 Agent 回答。")

    if st.button("🔄 补全上一条回答"):

        question = messages[-1]["content"]

        messages.append({
            "role": "assistant",
            "content": "",
            "status": "pending",
            "question": question,
            "k": top_k,
            "sources": [],
            "cited_sources": [],
        })

        st.rerun()


# -------- Chat input --------

pending = bool(
    messages
    and messages[-1].get("status") == "pending"
)

prompt = st.chat_input(
    "例如：公司 VPN 身份验证失败怎么办？",
    disabled=not backend_ready or pending,
)

if prompt is not None:

    question = prompt.strip()

    if not question:
        st.warning("请输入有效问题。")

    elif len(question) > 2000:
        st.warning("问题不能超过 2000 个字符。")

    else:

        # Save the question.
        messages.append({
            "role": "user",
            "content": question,
        })

        # Save a pending response BEFORE calling Qwen3.
        messages.append({
            "role": "assistant",
            "content": "",
            "status": "pending",
            "question": question,
            "k": top_k,
            "sources": [],
            "cited_sources": [],
        })

        st.rerun()


# -------- Process or recover pending response --------

if pending:

    if not backend_ready:

        st.warning(
            "后端暂时不可用，未完成的问题已保留。"
        )

        if st.button("重新检查连接"):
            st.rerun()

    else:

        pending_message = messages[-1]

        with st.spinner(
            "正在检索知识库并生成回答..."
        ):

            try:

                result = ask_knowledge(
                    pending_message["question"],
                    k=pending_message["k"],
                )

                completed_message = {
                    "role": "assistant",
                    "content": result["answer"],
                    "status": "done",
                    "sources": result.get(
                        "sources", []
                    ),
                    "cited_sources": result.get(
                        "cited_sources", []
                    ),
                }

            except (
                requests.RequestException,
                RuntimeError,
                ValueError,
            ) as exc:

                completed_message = {
                    "role": "assistant",
                    "content": (
                        "知识问答请求失败："
                        f"{type(exc).__name__}"
                    ),
                    "status": "error",
                    "question": pending_message["question"],
                    "k": pending_message["k"],
                    "sources": [],
                    "cited_sources": [],
                }

        # Save the response before rendering it.
        messages[-1] = completed_message

        st.rerun()


# -------- Retry a failed response --------

if (
    messages
    and messages[-1].get("status") == "error"
):

    if st.button("🔄 重试本次回答"):

        messages[-1]["status"] = "pending"
        messages[-1]["content"] = ""

        st.rerun()