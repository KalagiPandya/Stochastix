"""
auth/security.py
Authentication and Role-Based Access Control (RBAC) for Stochastix PRO.

Features:
- Password hashing with bcrypt (passlib)
- JWT access tokens (PyJWT) with configurable expiry
- Three built-in roles: admin, analyst, viewer
- DB-agnostic user storage — works against either the DuckDB or
  PostgreSQL backend via `pipeline` (both expose a `users` table)
- `require_role()` decorator/guard for protecting Streamlit pages

Environment variables:
    JWT_SECRET_KEY    — HMAC signing secret (REQUIRED in production;
                         a dev default is used otherwise with a warning)
    JWT_ALGORITHM     — default "HS256"
    JWT_EXPIRE_MINUTES — default 60
    DEFAULT_ADMIN_USER / DEFAULT_ADMIN_PASSWORD — optional bootstrap admin
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

if not JWT_SECRET_KEY:
    JWT_SECRET_KEY = "dev-only-insecure-secret-change-me"
    logger.warning(
        "JWT_SECRET_KEY not set — using an insecure development default. "
        "Set JWT_SECRET_KEY in your environment for any non-local deployment."
    )

# ── Roles ─────────────────────────────────────────────────────────────────
# admin   — full access: manage users, change settings, view everything
# analyst — read/write access to analytics, anomaly tuning, data export
# viewer  — read-only dashboard access
ROLES = {
    "admin":   {"level": 3, "description": "Full administrative access"},
    "analyst": {"level": 2, "description": "Configure analytics & export data"},
    "viewer":  {"level": 1, "description": "Read-only dashboard access"},
}


# ── Password hashing ─────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    import bcrypt
    # bcrypt has a hard 72-byte input limit; truncate (standard practice)
    # so longer passphrases don't raise instead of silently failing.
    truncated = plain_password.encode("utf-8")[:72]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    import bcrypt
    truncated = plain_password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(truncated, password_hash.encode("utf-8"))
    except Exception:
        return False


# ── JWT tokens ────────────────────────────────────────────────────────────

def create_access_token(username: str, role: str,
                         expires_minutes: int = JWT_EXPIRE_MINUTES) -> str:
    import jwt
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    import jwt
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.info("JWT expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.info("JWT invalid: %s", e)
        return None


# ── User management (DB-backed) ──────────────────────────────────────────

def register_user(username: str, email: str, password: str,
                   role: str = "viewer") -> tuple[bool, str]:
    """Create a new user. Returns (success, message)."""
    if role not in ROLES:
        return False, f"Invalid role '{role}'. Must be one of {list(ROLES)}."

    from pipeline import DB_BACKEND
    pw_hash = hash_password(password)

    try:
        if DB_BACKEND == "postgres":
            from pipeline.postgres_db import _exec, _query_one
            existing = _query_one("SELECT id FROM users WHERE username = %s OR email = %s",
                                   (username, email))
            if existing:
                return False, "Username or email already registered."
            _exec(
                "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                (username, email, pw_hash, role),
            )
        else:
            from pipeline.database import _exec, _query_one
            existing = _query_one("SELECT id FROM users WHERE username = ? OR email = ?",
                                   [username, email])
            if existing:
                return False, "Username or email already registered."
            _exec(
                """
                INSERT INTO users (id, username, email, password_hash, role)
                VALUES (nextval('users_id_seq'), ?, ?, ?, ?)
                """,
                [username, email, pw_hash, role],
            )
        return True, "User registered successfully."
    except Exception as e:
        logger.error("register_user error: %s", e)
        return False, f"Registration failed: {e}"


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Verify credentials. Returns user dict (without password hash) or None."""
    from pipeline import DB_BACKEND

    try:
        if DB_BACKEND == "postgres":
            from pipeline.postgres_db import _query_one
            row = _query_one(
                "SELECT id, username, email, password_hash, role, is_active FROM users WHERE username = %s",
                (username,),
            )
        else:
            from pipeline.database import _query_one
            row = _query_one(
                "SELECT id, username, email, password_hash, role, is_active FROM users WHERE username = ?",
                [username],
            )
    except Exception as e:
        logger.error("authenticate_user error: %s", e)
        return None

    if row is None:
        return None

    user_id, uname, email, pw_hash, role, is_active = row
    if not is_active:
        return None
    if not verify_password(password, pw_hash):
        return None

    return {"id": user_id, "username": uname, "email": email, "role": role}


def ensure_default_admin() -> None:
    """Optionally bootstrap a default admin user from env vars on first run."""
    admin_user = os.environ.get("DEFAULT_ADMIN_USER")
    admin_pass = os.environ.get("DEFAULT_ADMIN_PASSWORD")
    if not admin_user or not admin_pass:
        return

    if authenticate_user(admin_user, admin_pass) is not None:
        return  # already exists & matches

    ok, msg = register_user(admin_user, f"{admin_user}@stochastix.local", admin_pass, role="admin")
    if ok:
        logger.info("Bootstrapped default admin user '%s'", admin_user)
    else:
        logger.debug("Default admin bootstrap skipped: %s", msg)


# ── RBAC guard for Streamlit pages ───────────────────────────────────────

def has_permission(user_role: str, required_role: str) -> bool:
    """True if user_role's access level >= required_role's level."""
    return ROLES.get(user_role, {"level": 0})["level"] >= ROLES.get(required_role, {"level": 99})["level"]


def require_role(required_role: str):
    """
    Streamlit page guard. Call at the top of any page:

        from auth.security import require_role
        require_role("analyst")

    Renders a login form if the user isn't authenticated, and an
    "access denied" message if their role doesn't meet `required_role`.
    Stops page execution (st.stop()) if access isn't granted.
    """
    import streamlit as st

    user = st.session_state.get("user")

    if user is None:
        _render_login_form()
        st.stop()

    if not has_permission(user["role"], required_role):
        st.error(
            f"🔒 Access denied. This page requires the **{required_role}** role "
            f"or higher — your role is **{user['role']}**."
        )
        st.stop()

    return user


def _render_login_form():
    import streamlit as st

    st.title("🔐 Stochastix PRO — Sign In")
    st.caption("Authentication required to access this page.")

    tab_login, tab_register = st.tabs(["Sign In", "Register"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
        if submitted:
            user = authenticate_user(username, password)
            if user:
                token = create_access_token(user["username"], user["role"])
                st.session_state["user"] = user
                st.session_state["access_token"] = token
                st.success(f"Welcome back, {user['username']} ({user['role']}).")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Choose a username")
            new_email = st.text_input("Email")
            new_password = st.text_input("Choose a password", type="password")
            role = st.selectbox("Role", list(ROLES.keys()), index=2,
                                 help="In production, role assignment should be admin-controlled.")
            reg_submitted = st.form_submit_button("Create Account", use_container_width=True)
        if reg_submitted:
            ok, msg = register_user(new_username, new_email, new_password, role)
            if ok:
                st.success(msg + " You can now sign in.")
            else:
                st.error(msg)
