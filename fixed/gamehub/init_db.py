"""Наполнение базы учебного стенда демонстрационными данными."""
from pathlib import Path
import sqlite3

from app import hash_password

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "gamehub.sqlite3"

DEMO_USERS = [
    ("admin", "LabAdmin-ChangeMe-2026", 1),
    ("player", "PlayerDemo-ChangeMe-2026", 0),
]

DEMO_GAMES = [
    ("Neon Drift", "racing", 2024, 8.4, "Аркадные гонки по ночному мегаполису."),
    ("Hollow Depths", "adventure", 2022, 9.1, "Мрачное подводное приключение с головоломками."),
    ("Pixel Harvest", "simulation", 2023, 7.6, "Уютная ферма на далёкой планете."),
    ("Iron Verdict", "action", 2021, 8.0, "Тактический бой в разрушенном городе."),
    ("Silent Orbit", "strategy", 2025, 8.8, "Управление орбитальной станцией на грани катастрофы."),
    ("Paper Kingdoms", "rpg", 2020, 7.9, "Классическая ролевая игра в стиле бумажного театра."),
]

DEMO_REVIEWS = [
    (1, "player", 8, "Отличный саундтрек и приятное управление."),
    (1, "admin", 9, "Лучшая аркадная гонка за последние годы."),
    (2, "player", 10, "Атмосфера на высоте, головоломки не повторяются."),
    (5, "player", 7, "Сложно, но очень затягивает."),
]

# Данные, которые нельзя получить через штатный интерфейс.
# Добавлены только для наглядной демонстрации SQL Injection.
LAB_SECRETS = [
    ("flag", "GAMEHUB{un10n_b4s3d_5ql1_w0rk5}"),
    ("note", "Секрет из таблицы lab_secrets: доступен только через SQL-инъекцию."),
]


def main():
    if DB_PATH.exists():
        answer = input("gamehub.sqlite3 already exists. Re-create it? [y/N] ").strip().lower()
        if answer != "y":
            print("Existing database was kept.")
            return
        DB_PATH.unlink()

    db = sqlite3.connect(DB_PATH)
    db.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
    db.executemany(
        "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
        [(name, hash_password(pw), is_admin) for name, pw, is_admin in DEMO_USERS],
    )
    db.executemany(
        "INSERT INTO games (title, genre, release_year, rating, description) "
        "VALUES (?, ?, ?, ?, ?)",
        DEMO_GAMES,
    )
    db.executemany(
        "INSERT INTO reviews (game_id, username, score, body) VALUES (?, ?, ?, ?)",
        DEMO_REVIEWS,
    )
    db.executemany("INSERT INTO lab_secrets (name, value) VALUES (?, ?)", LAB_SECRETS)
    db.commit()
    db.close()

    public_dir = BASE_DIR / "lab_data" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "guide.txt").write_text(
        "GameHub Security Lab\n"
        "Это безопасный учебный файл для тестирования скачивания.\n",
        encoding="utf-8",
    )
    private_dir = BASE_DIR / "lab_data" / "private"
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "secret.txt").write_text(
        "gamehub-internal\n"
        "GAMEHUB{p4th_tr4v3rs4l_r34ch3d_pr1v4t3_f1l3}\n"
        "Этот файл не должен скачиваться через /download.\n",
        encoding="utf-8",
    )
    print("Database created.")
    print("Admin demo account: admin / LabAdmin-ChangeMe-2026")
    print("Player demo account: player / PlayerDemo-ChangeMe-2026")
    print("Use these credentials only in this local lab.")


if __name__ == "__main__":
    main()
