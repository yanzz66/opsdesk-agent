
"""OpsDesk Agent - Employee ticket submission page."""

import os

import requests
import streamlit as st


API_BASE_URL = os.getenv(
    "OPSDESK_API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


st.set_page_config(
    page_title="工单申请 | OpsDesk Agent",
    page_icon="📋",
    layout="wide",
)


# Preserve the submitted ticket during Streamlit reruns.
if "submitted_ticket" not in st.session_state:
    st.session_state.submitted_ticket = None


def check_backend():
    """Check whether FastAPI is reachable."""

    try:
        response = requests.get(
            f"{API_BASE_URL}/health",
            timeout=5,
        )

        return (
            response.status_code == 200
            and response.json().get("status") == "ok"
        )

    except (requests.RequestException, ValueError):
        return False


def create_ticket(description, user_key):
    """Submit a new ticket through FastAPI."""

    return requests.post(
        f"{API_BASE_URL}/api/tickets",
        json={
            "description": description,
        },
        headers={
            "X-OpsDesk-User-Key": user_key,
        },
        timeout=(5, 240),
    )


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

    st.divider()

    st.subheader("员工身份验证")

    user_key = st.text_input(
        "员工 API Key",
        type="password",
        key="opsdesk_ticket_user_key",
        help="输入 FastAPI 服务端配置的员工演示密钥",
    )

    st.caption(
        "密钥用于本地演示。"
        "不要在截图中展示真实密钥。"
    )


# Main page.
st.title("📋 IT 服务工单申请")

st.caption(
    "描述遇到的 IT 问题，"
    "提交后由管理员审核。"
)

st.info(
    "提交申请不会立即创建正式工单。"
    "只有管理员批准后，才会写入 SQLite 数据库。"
)


if st.session_state.submitted_ticket is None:

    with st.form("ticket_submit_form"):

        description = st.text_area(
            "请描述遇到的问题",
            placeholder=(
                "例如：公司 VPN 无法登录，"
                "一直提示身份验证失败。"
            ),
            max_chars=1900,
            height=160,
        )

        submitted = st.form_submit_button(
            "🚀 提交工单申请",
            type="primary",
            use_container_width=True,
        )

    if submitted:

        description = description.strip()

        if not description:
            st.warning("请先填写工单描述。")

        elif not user_key.strip():
            st.warning(
                "请先在左侧输入员工 API Key。"
            )

        elif not backend_ready:
            st.error(
                "FastAPI 服务未连接，暂时无法提交。"
            )

        else:

            try:
                with st.spinner("正在创建待审批工单..."):
                    response = create_ticket(
                        description,
                        user_key,
                    )

                if response.status_code == 201:

                    data = response.json()

                    if (
                        data.get("status") == "pending_approval"
                        and data.get("thread_id")
                        and data.get("draft")
                    ):
                        st.session_state.submitted_ticket = data
                        st.rerun()

                    else:
                        st.error(
                            "接口返回了非预期的工作流状态。"
                            "请检查后端日志，不要立即重复提交。"
                        )

                elif response.status_code == 401:
                    st.error(
                        "未提供有效的员工认证信息。"
                    )

                elif response.status_code == 403:
                    st.error(
                        "员工 API Key 不正确。"
                    )

                elif response.status_code == 503:
                    st.error(
                        "工单服务暂时不可用，"
                        "请检查 FastAPI 配置。"
                    )

                else:
                    st.error(
                        "提交失败，HTTP 状态码："
                        f"{response.status_code}"
                    )

            except requests.Timeout:
                st.error(
                    "请求超时。服务端可能已接收申请，"
                    "请先检查记录，不要直接重复提交。"
                )

            except requests.RequestException:
                st.error(
                    "无法连接工单服务，请检查 FastAPI。"
                )

            except ValueError:
                st.error(
                    "接口响应格式不正确，请检查后端日志。"
                )


else:

    ticket = st.session_state.submitted_ticket
    draft = ticket.get("draft", {})

    st.success("✅ 工单申请已成功提交！")

    st.subheader("申请结果")

    st.write("**当前状态：** 等待人工审批")
    st.write(
        "**工单类别：**",
        draft.get("category", "未知"),
    )
    st.write(
        "**问题描述：**",
        draft.get("description", ""),
    )

    st.markdown("**工作流编号（thread_id）**")
    st.code(ticket["thread_id"])

    st.markdown("**请求编号（request_id）**")
    st.code(draft.get("request_id", ""))

    st.info(
        "当前还没有正式 ticket_id。"
        "管理员审批通过后，系统才会创建工单。"
    )

    if st.button(
        "提交另一张工单",
        use_container_width=True,
    ):
        st.session_state.submitted_ticket = None
        st.rerun()