"""pages/5_Login.py — Authentication & RBAC."""

import streamlit as st

from pipeline import init_db
from auth.security import (
    ROLES, authenticate_user, create_access_token,
    register_user, ensure_default_admin, has_permission,
)

st.set_page_config(page_title="Login — Stochastix", page_icon="🔐", layout="wide")

st.markdown("""
<style>
[data-testid="metric-container"]{background:#161B22;border:1px solid #21262D;border-radius:10px;padding:16px 20px;}
[data-testid="stSidebar"]{background:#0D1117;border-right:1px solid #21262D;}
hr{border-color:#21262D;}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def ensure():
    init_db(); ensure_default_admin(); return True
ensure()

st.title("🔐 Account & Access")

user = st.session_state.get("user")

if user is None:
    st.info("Sign in to unlock analyst/admin features. Public dashboards are always visible.")
    tab_in, tab_reg = st.tabs(["Sign In", "Register"])

    with tab_in:
        with st.form("login_form"):
            username  = st.text_input("Username")
            password  = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
        if submitted:
            u = authenticate_user(username, password)
            if u:
                st.session_state["user"]         = u
                st.session_state["access_token"] = create_access_token(u["username"], u["role"])
                st.success(f"Welcome back, {u['username']}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with tab_reg:
        st.caption("New accounts default to **viewer** role.")
        with st.form("register_form"):
            new_user  = st.text_input("Username")
            new_email = st.text_input("Email")
            new_pass  = st.text_input("Password", type="password")
            reg_sub   = st.form_submit_button("Create Account", use_container_width=True)
        if reg_sub:
            ok, msg = register_user(new_user, new_email, new_pass, role="viewer")
            (st.success if ok else st.error)(msg)
else:
    st.success(f"Signed in as **{user['username']}** — role: **{user['role']}**")
    st.markdown("### 🔑 Your Access Level")
    cols = st.columns(len(ROLES))
    for col, (role_name, meta) in zip(cols, ROLES.items()):
        with col:
            icon = "✅" if has_permission(user["role"], role_name) else "⛔"
            st.metric(role_name.capitalize(), icon)
            st.caption(meta["description"])

    st.markdown("---")
    st.markdown("### 🪪 JWT Access Token")
    st.code(st.session_state.get("access_token", ""), language="text")
    if st.button("Sign Out", type="primary"):
        st.session_state.pop("user", None)
        st.session_state.pop("access_token", None)
        st.rerun()

st.markdown("---")
st.markdown("### 🛡️ Role Capability Matrix")
st.table({
    "Role":              list(ROLES.keys()),
    "Level":             [ROLES[r]["level"] for r in ROLES],
    "Description":       [ROLES[r]["description"] for r in ROLES],
    "Dashboard Access":  ["✅" for _ in ROLES],
    "ML Anomaly":        ["✅" if has_permission(r, "analyst") else "—" for r in ROLES],
    "Data Export":       ["✅" if has_permission(r, "analyst") else "—" for r in ROLES],
    "User Management":   ["✅" if has_permission(r, "admin")   else "—" for r in ROLES],
})
