import sqlite3
import uuid
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import hashlib
from app.core.db_path import get_db_path

router = APIRouter(prefix="/api/v1/login", tags=["login"])


class LoginRequest(BaseModel):
    username: str
    password: str


def get_conn():
    return sqlite3.connect(get_db_path())

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

@router.post("")
def login(data: LoginRequest):
    username = data.username   # ✅ works
    password = data.password
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute(
        "SELECT id, username FROM users WHERE username = ? AND password = ?",
        (username, hash_password(password)),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "user_id": row[0],
        "username": row[1],
        "session_id": str(uuid.uuid4()),
    }