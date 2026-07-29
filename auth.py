import datetime
import os
from functools import wraps
from pathlib import Path

import jwt
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, DATA_DIR

SECRET_KEY_PATH = DATA_DIR / ".secret_key"


def _get_secret_key():
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_text().strip()
    import secrets

    key = secrets.token_hex(32)
    SECRET_KEY_PATH.write_text(key)
    return key


SECRET_KEY = _get_secret_key()


def hash_password(password):
    # Explicit pbkdf2 method: this system's Python lacks hashlib.scrypt,
    # which is werkzeug's newer default.
    return generate_password_hash(password, method="pbkdf2:sha256")


def verify_password(password, password_hash):
    return check_password_hash(password_hash, password)


def create_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("user_id")
    except jwt.PyJWTError:
        return None


def _extract_token():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return request.args.get("token")


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _extract_token()
        user_id = decode_token(token) if token else None
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        db.close()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        g.user = user
        return fn(*args, **kwargs)

    return wrapper
