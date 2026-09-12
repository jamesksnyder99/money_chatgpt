from __future__ import annotations

import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from thetadata import ThetaClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _REPO_ROOT / ".env"

_EMAIL_PASSWORD_PAIRS = (
    ("THETADATA_EMAIL", "THETADATA_PASSWORD"),
    ("THETA_EMAIL", "THETA_PASSWORD"),
    ("THETA_USERNAME", "THETA_PASSWORD"),
    ("EMAIL", "PASSWORD"),
    ("USERNAME", "PASSWORD"),
)

_EXPECTED = (
    "THETADATA_API_KEY, or an email/password pair: "
    "THETADATA_EMAIL/THETADATA_PASSWORD, THETA_EMAIL/THETA_PASSWORD, "
    "THETA_USERNAME/THETA_PASSWORD, EMAIL/PASSWORD, USERNAME/PASSWORD"
)


def _load_env() -> None:
    load_dotenv(_ENV_PATH)


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _email_password() -> tuple[str, str] | None:
    for email_key, password_key in _EMAIL_PASSWORD_PAIRS:
        email, password = _env(email_key), _env(password_key)
        if email and password:
            return email, password
    return None


def auth_mode() -> str:
    _load_env()
    if _env("THETADATA_API_KEY"):
        return "api_key"
    if _email_password():
        return "email_password"
    raise RuntimeError(f"Missing Theta Data credentials in .env. Expected {_EXPECTED}.")


def get_client() -> ThetaClient:
    _load_env()
    api_key = _env("THETADATA_API_KEY")
    if api_key:
        return ThetaClient(api_key=api_key, dataframe_type="polars")
    pair = _email_password()
    if pair:
        email, password = pair
        return ThetaClient(email=email, password=password, dataframe_type="polars")
    raise RuntimeError(f"Missing Theta Data credentials in .env. Expected {_EXPECTED}.")


_CLIENT: ThetaClient | None = None
_CLIENT_LOCK = threading.Lock()


def get_shared_client() -> ThetaClient:
    """One authenticated client for the process (gRPC stub is thread-safe)."""
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = get_client()
        return _CLIENT

