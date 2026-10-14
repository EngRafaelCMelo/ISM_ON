"""Autenticacao local offline com PBKDF2, salt e controle de perfil."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional


PASSWORD_ITERATIONS = 310_000
MIN_PASSWORD_LENGTH = 8


def _encoded_hash(password: str, salt: bytes, iterations: int = PASSWORD_ITERATIONS) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha deve possuir ao menos {MIN_PASSWORD_LENGTH} caracteres.")
    return _encoded_hash(password, secrets.token_bytes(16))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, UnicodeError):
        return False


class UserStore:
    """Arquivo local de usuarios; o arquivo deve permanecer fora do repositorio."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {"version": 1, "users": {}}
        with open(self.path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict) or not isinstance(data.get("users", {}), dict):
            raise ValueError("Arquivo de usuarios invalido.")
        data.setdefault("version", 1)
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directory,
                prefix=".users-", suffix=".tmp", delete=False
            ) as file:
                temporary = file.name
                json.dump(data, file, indent=2, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def has_users(self) -> bool:
        return bool(self._load().get("users"))

    def create_user(self, username: str, password: str, role: str = "operator") -> None:
        username = username.strip()
        if not username:
            raise ValueError("Usuario obrigatorio.")
        if role not in {"operator", "admin"}:
            raise ValueError("Perfil de usuario invalido.")
        data = self._load()
        if username in data["users"]:
            raise ValueError("Usuario ja existente.")
        data["users"][username] = {
            "role": role,
            "password_hash": hash_password(password),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        self._save(data)

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, str]]:
        record = self._load().get("users", {}).get(username.strip())
        if not record or not verify_password(password, str(record.get("password_hash", ""))):
            return None
        return {"username": username.strip(), "role": str(record.get("role", "operator"))}

    def get_role(self, username: str) -> Optional[str]:
        record = self._load().get("users", {}).get(username.strip())
        return str(record["role"]) if record else None
