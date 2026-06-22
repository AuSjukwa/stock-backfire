"""A股回测平台 Web 面板。

运行：
  .venv/bin/streamlit run app/streamlit_app.py
默认仅监听 localhost，不对外暴露、无需鉴权。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 app/ 能 import 到 backfire 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="A股回测平台", layout="wide")


# ===========================================================================
# 访问口令（可选）
# 仅当配置了 secrets["app_password"] 时启用；本地未配置则照常无鉴权运行。
# 云端部署：在平台 Secrets 里写 app_password = "你的口令"
# ===========================================================================
def _check_password() -> bool:
    try:
        expected = st.secrets["app_password"]
    except (FileNotFoundError, KeyError):
        return True  # 未配置口令 → 不启用鉴权（本地开发）
    if not expected:
        return True

    if st.session_state.get("password_ok"):
        return True

    def _verify():
        import hmac
        st.session_state["password_ok"] = hmac.compare_digest(
            st.session_state.get("password_input", ""), str(expected)
        )

    st.text_input("访问口令", type="password", key="password_input", on_change=_verify)
    if "password_ok" in st.session_state and not st.session_state["password_ok"]:
        st.error("口令错误")
    return False


if not _check_password():
    st.stop()


from app.views import backtest_view, monitor_view

pages = [
    st.Page(monitor_view.render, title="趋势监控", icon="📈", url_path="monitor", default=True),
    st.Page(backtest_view.render, title="策略回测", icon="🧪", url_path="strategy"),
]
pg = st.navigation(pages, position="top")
pg.run()
