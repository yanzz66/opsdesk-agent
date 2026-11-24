
"""OpsDesk Agent - Administrator approval page."""

import os
from uuid import UUID

import requests
import streamlit as st


API_BASE_URL = os.getenv(
    "OPSDESK_API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


st.set_page_config(
    page_title="管理员审批 | OpsDesk Agent",
    page_icon="🛡️",
    layout="wide",
)


# -------- Session state --------

for name in (
    "admin_workflow",
    "admin_ticket",
    "admin_notice",
):
    if name not in st.session_state:
        st.session_state[name] = None


def clear_loaded():
    """Discard results when credentials or IDs change."""
    st.session_state.admin_workflow = None
    st.session_state.admin_ticket = None
    st.session_state.admin_notice = None


# -------- API client --------

def call_api(method, path, key, body=None):
    """Call an administrator-protected FastAPI endpoint."""

    response = requests.request(
        method=method,
        url=f"{API_BASE_URL}{path}",
        headers={
            "X-OpsDesk-Approver-Key": key,
        },
        json=body,
        timeout=(5, 120),
    )

    try:
        data = response.json()
    except ValueError:
        data = {}

    if not isinstance(data, dict):
        data = {}

    return response.status_code, data


def show_api_error(status):
    """Display safe, user-friendly API errors."""

    if status == 401:
        st.error("请先填写管理员 API Key。")
    elif status == 403:
        st.error("管理员 API Key 不正确。")
    elif status == 404:
        st.error("未找到对应的工作流或工单。")
    elif status == 409:
        st.warning("该工单已处理，不能重复审批。")
    elif status == 503:
        st.error(
            "后端服务暂时不可用。"
            "请检查 FastAPI 配置和终端日志。"
        )
    else:
        st.error(f"请求失败：HTTP {status}")


def valid_uuid(value):
    """Return a normalized UUID or None."""
    try:
        return str(UUID(value.strip()))
    except (ValueError, AttributeError):
        return None


# -------- Sidebar --------

with st.sidebar:

    st.title("🛠️ OpsDesk Agent")
    st.caption("企业 IT 智能服务助手")

    st.divider()

    st.subheader("管理员身份验证")

    approver_key = st.text_input(
        "管理员 API Key",
        type="password",
        key="opsdesk_admin_key",
        on_change=clear_loaded,
    )

    st.caption(
        "使用 FastAPI 服务端设置的"
        " OPSDESK_APPROVER_KEY。"
    )

    st.warning(
        "本页面仅用于本地演示，"
        "不要公开管理员密钥。"
    )


# -------- Main page --------

st.title("🛡️ 工单审批中心")

st.caption(
    "查询 LangGraph 审批状态，"
    "人工批准或拒绝工单。"
)

st.info(
    "管理员审批是实际业务写入的安全边界。"
    "未批准的工单不会正式创建。"
)


# -------- Workflow lookup --------

st.subheader("1. 查询待审批工单")

thread_input = st.text_input(
    "工作流编号（thread_id）",
    placeholder="粘贴员工提交工单后返回的 thread_id",
    key="opsdesk_admin_thread_id",
    on_change=clear_loaded,
)

if st.button(
    "🔎 查询工作流",
    use_container_width=True,
):

    thread_id = valid_uuid(thread_input)

    if not approver_key.strip():
        st.error("请先输入管理员 API Key。")

    elif thread_id is None:
        st.warning("请输入有效的 thread_id UUID。")

    else:
        try:
            with st.spinner("正在查询工作流..."):
                status, data = call_api(
                    "GET",
                    f"/api/tickets/workflows/{thread_id}",
                    approver_key,
                )

            if status == 200:
                st.session_state.admin_workflow = data
                st.session_state.admin_ticket = None
                st.success("工作流查询成功！")
            else:
                show_api_error(status)

        except requests.RequestException:
            st.error(
                "网络请求失败，请确认 FastAPI 正在运行。"
            )


# -------- Workflow details --------

workflow = st.session_state.admin_workflow

if workflow:

    st.divider()
    st.subheader("2. 审批详情")

    current_status = workflow.get(
        "status",
        "unknown",
    )

    draft = workflow.get("draft") or {}

    if current_status == "pending_approval":
        st.warning("⏳ 当前状态：等待人工审批")

    elif current_status == "open":
        st.success("✅ 当前状态：审批通过")

    elif current_status == "rejected":
        st.error("❌ 当前状态：审批已拒绝")

    else:
        st.info(f"当前状态：{current_status}")

    st.write(
        "**工单类别：**",
        draft.get("category", "未知"),
    )

    st.write(
        "**问题描述：**",
        draft.get("description", ""),
    )

    if draft.get("title"):
        st.write(
            "**工单标题：**",
            draft["title"],
        )

    if draft.get("issue_type"):
        st.write(
            "**问题类型：**",
            draft["issue_type"],
        )

    st.write("**请求编号（request_id）：**")
    st.code(draft.get("request_id", ""))


    # -------- Human decision --------

    if current_status == "pending_approval":

        st.divider()
        st.subheader("3. 人工审批决定")

        confirmed = st.checkbox(
            "我已核对工单描述，确认进行本次审批",
        )

        col1, col2 = st.columns(2)

        with col1:
            approve_clicked = st.button(
                "✅ 批准工单",
                type="primary",
                disabled=not confirmed,
                use_container_width=True,
            )

        with col2:
            reject_clicked = st.button(
                "❌ 拒绝工单",
                disabled=not confirmed,
                use_container_width=True,
            )

        if approve_clicked or reject_clicked:

            approved = approve_clicked
            thread_id = workflow["thread_id"]

            try:
                with st.spinner("正在提交审批结果..."):

                    status, data = call_api(
                        "POST",
                        (
                            "/api/tickets/workflows/"
                            f"{thread_id}/decision"
                        ),
                        approver_key,
                        body={"approved": approved},
                    )

                if status == 200:

                    st.session_state.admin_workflow = data

                    st.session_state.admin_ticket = None

                    st.session_state.admin_notice = (
                        "工单审批已通过。"
                        if approved
                        else "工单已拒绝。"
                    )

                    st.rerun()

                else:
                    show_api_error(status)

            except requests.RequestException:
                st.error(
                    "审批请求未能确认结果。"
                    "请先重新查询工作流状态，"
                    "不要立即重复提交。"
                )


    # -------- Approved ticket --------

    if current_status == "open":

        st.divider()
        st.subheader("3. 已创建的正式工单")

        ticket_id = workflow.get("ticket_id")

        if ticket_id:

            st.write("**工单编号（ticket_id）：**")
            st.code(ticket_id)

            if st.button(
                "📂 查询 SQLite 工单",
                use_container_width=True,
            ):

                try:
                    status, data = call_api(
                        "GET",
                        f"/api/tickets/{ticket_id}",
                        approver_key,
                    )

                    if status == 200:
                        st.session_state.admin_ticket = data
                    else:
                        show_api_error(status)

                except requests.RequestException:
                    st.error("无法连接工单查询服务。")

            if st.session_state.admin_ticket:

                ticket = st.session_state.admin_ticket

                st.success("已读取数据库工单记录。")

                st.write("**数据库工单信息：**")

                st.json(ticket)

        else:
            st.warning(
                "审批状态为 open，"
                "但没有返回 ticket_id，请检查后端。"
            )


    # -------- Rejection --------

    if current_status == "rejected":

        st.info(
            "该申请已拒绝，"
            "不会生成正式 ticket_id。"
        )

        if workflow.get("answer"):
            st.write(workflow["answer"])


# -------- Notice --------

if st.session_state.admin_notice:
    st.success(st.session_state.admin_notice)