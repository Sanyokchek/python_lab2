"""Общие фикстуры приёмочных тестов лаборатории GameHub.

Тесты намеренно написаны так, чтобы одинаково запускаться и на уязвимой,
и на исправленной версии приложения: на уязвимой части тестов должны
падать (это и есть демонстрация дыры), на исправленной — проходить.
"""
import sqlite3
from pathlib import Path

import pytest

import app as gamehub


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite3"
    public_dir = tmp_path / "public"
    public_dir.mkdir()

    (public_dir / "guide.txt").write_text("safe public guide", encoding="utf-8")
    # Файл-приманка вне каталога public: он не должен скачиваться через /download.
    (tmp_path / "secret.txt").write_text("top-secret-marker", encoding="utf-8")

    monkeypatch.setattr(gamehub, "DATABASE", db_path)
    monkeypatch.setattr(gamehub, "PUBLIC_DIR", public_dir.resolve())
    monkeypatch.setitem(gamehub.app.config, "DATABASE", str(db_path))
    monkeypatch.setitem(gamehub.app.config, "TESTING", True)
    monkeypatch.setitem(gamehub.app.config, "SECRET_KEY", "pytest-only-secret")

    db = sqlite3.connect(db_path)
    db.executescript(
        (Path(gamehub.__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")
    )
    db.executemany(
        "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
        [
            ("admin", gamehub.hash_password("test-admin-password"), 1),
            ("player", gamehub.hash_password("test-player-password"), 0),
        ],
    )
    db.executemany(
        "INSERT INTO games (title, genre, release_year, rating, description) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("Neon Drift", "racing", 2024, 8.4, "Аркадные гонки."),
            ("Hollow Depths", "adventure", 2022, 9.1, "Подводное приключение."),
        ],
    )
    db.executemany(
        "INSERT INTO reviews (game_id, username, score, body) VALUES (?, ?, ?, ?)",
        [(1, "player", 8, "Хорошая игра.")],
    )
    db.executemany(
        "INSERT INTO lab_secrets (name, value) VALUES (?, ?)",
        [("flag", "TESTFLAG{should_not_be_reachable}")],
    )
    db.commit()
    db.close()

    yield gamehub.app.test_client()


def login_as(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )
