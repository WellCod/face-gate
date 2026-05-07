import json
import os
import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np

DB_PATH = os.environ.get("DB_PATH", "/app/data/usuarios.db")


def _ensure_db_dir() -> None:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def _connect() -> sqlite3.Connection:
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                encoding TEXT NOT NULL,
                imagem_path TEXT,
                criado_em TEXT NOT NULL
            )
            """
        )
        conn.commit()


def salvar_usuario(nome: str, encoding: np.ndarray, imagem_path: Optional[str] = None) -> int:
    encoding_json = json.dumps(encoding.tolist())
    criado_em = datetime.utcnow().isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO usuarios (nome, encoding, imagem_path, criado_em)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(nome) DO UPDATE SET
                encoding = excluded.encoding,
                imagem_path = excluded.imagem_path,
                criado_em = excluded.criado_em
            """,
            (nome, encoding_json, imagem_path, criado_em),
        )
        conn.commit()
        return cur.lastrowid or 0


def listar_usuarios() -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, nome, criado_em, imagem_path FROM usuarios ORDER BY nome ASC"
        ).fetchall()
        return [dict(row) for row in rows]


def carregar_encodings() -> List[Tuple[str, np.ndarray]]:
    with _connect() as conn:
        rows = conn.execute("SELECT nome, encoding FROM usuarios").fetchall()
        encodings: List[Tuple[str, np.ndarray]] = []
        for row in rows:
            vetor = np.array(json.loads(row["encoding"]), dtype=np.float32)
            encodings.append((row["nome"], vetor))
        return encodings
