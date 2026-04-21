"""
app/core/db_path.py

Single source of truth for the SQLite database path.
Import this everywhere instead of hardcoding paths.
"""

import os
from pathlib import Path

# backend/app/core/db_path.py
# parents: core → app → backend → database/ticket.db
_BACKEND_DIR = Path(__file__).resolve().parents[2]
DB_PATH = str(_BACKEND_DIR / "database" / "ticket.db")

def get_db_path() -> str:
    """Returns absolute path to ticket.db — always backend/database/ticket.db"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return DB_PATH