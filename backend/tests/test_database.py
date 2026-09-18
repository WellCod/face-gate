"""Persistência dos encodings — ida e volta pelo SQLite."""

import importlib

import numpy as np
import pytest


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Banco isolado por teste, via DB_PATH."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "usuarios.db"))
    import database

    importlib.reload(database)
    database.init_db()
    return database


def test_init_db_e_idempotente(db) -> None:
    db.init_db()
    assert db.listar_usuarios() == []


def test_encoding_volta_igual_ao_que_entrou(db) -> None:
    original = np.array([0.1, -0.25, 0.75, 1.0], dtype=np.float64)
    db.salvar_usuario("Ana Souza", original)

    carregados = db.carregar_encodings()
    assert len(carregados) == 1
    nome, encoding = carregados[0]
    assert nome == "Ana Souza"
    np.testing.assert_allclose(encoding, original)


def test_listar_usuarios_traz_os_cadastrados(db) -> None:
    db.salvar_usuario("Ana Souza", np.zeros(4))
    db.salvar_usuario("Bruno Lima", np.ones(4))

    nomes = {u["nome"] for u in db.listar_usuarios()}
    assert nomes == {"Ana Souza", "Bruno Lima"}


def test_banco_vazio_nao_quebra_o_carregamento(db) -> None:
    assert db.carregar_encodings() == []
