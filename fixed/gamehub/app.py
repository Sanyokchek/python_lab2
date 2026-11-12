"""GameHub Security Lab — ИСПРАВЛЕННАЯ версия (только для локального обучения).

Отличия от уязвимой версии (см. security-fixes.diff):
  * SQL-запросы параметризованы, ввод пользователя больше не склеивается с SQL;
  * пароли хранятся как scrypt-хеш с солью и проверяются check_password_hash;
  * скачивание нормализует путь и проверяет, что он остался внутри lab_data/public.
"""
from pathlib import Path
import re
import os
import sqlite3

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for, send_file
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "gamehub.sqlite3"
PUBLIC_DIR = BASE_DIR / "lab_data" / "public"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("GAMEHUB_SECRET_KEY", "local-lab-change-this-key")
app.config["DATABASE"] = str(DATABASE)


def hash_password(password: str) -> str:
    """Пароль хранится как scrypt-хеш с индивидуальной солью."""
    return generate_password_hash(password)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return get_db().execute(
        "SELECT id, username, is_admin FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def admin_required():
    user = current_user()
    if user is None or not user["is_admin"]:
        abort(403)
    return user


@app.context_processor
def inject_user():
    return {"logged_in_user": current_user()}


@app.route("/")
def index():
    games = get_db().execute(
        "SELECT id, title, genre, release_year, rating, description FROM games ORDER BY id"
    ).fetchall()
    return render_template("index.html", games=games, query="")


@app.post("/register")
def register():
    """Создание обычной пользовательской учётной записи."""
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not re.fullmatch(r"[A-Za-z0-9_-]{3,24}", username):
        flash("Логин: от 3 до 24 символов (латинские буквы, цифры, _ и -).", "error")
        return redirect(url_for("index"))
    if len(password) < 8:
        flash("Пароль должен содержать не менее 8 символов.", "error")
        return redirect(url_for("index"))

    try:
        cursor = get_db().execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 0)",
            (username, hash_password(password)),
        )
        get_db().commit()
    except sqlite3.IntegrityError:
        flash("Такой логин уже занят.", "error")
        return redirect(url_for("index"))

    session.clear()
    session["user_id"] = cursor.lastrowid
    flash(f"Аккаунт создан. Добро пожаловать, {username}!", "success")
    return redirect(url_for("index"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # ИСПРАВЛЕНО: параметризованный запрос. Имя пользователя передаётся
        # отдельным параметром, поэтому кавычки и `-- ` внутри него остаются
        # обычным текстом и не меняют структуру SQL-выражения.
        user = get_db().execute(
            "SELECT id, username, password_hash, is_admin FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if user is not None and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Вход выполнен: {user['username']}", "success")
            return redirect(url_for("index"))
        flash("Неверное имя пользователя или пароль.", "error")
        return redirect(url_for("index"))
    return render_template("login.html", error=None)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
def admin():
    user = admin_required()
    return render_template("admin.html", user=user)


@app.route("/games")
def games():
    query = request.args.get("q", "").strip()

    # ИСПРАВЛЕНО: поисковая строка передаётся как параметр (LIKE-шаблон),
    # а не вставляется в текст запроса. UNION и другие конструкции внутри
    # `q` остаются данными.
    pattern = f"%{query}%"
    rows = get_db().execute(
        "SELECT id, title, genre, release_year, rating, description FROM games "
        "WHERE title LIKE ? OR genre LIKE ?",
        (pattern, pattern),
    ).fetchall()
    return render_template("games.html", games=rows, query=query)


@app.route("/games/<int:game_id>")
def game_detail(game_id):
    db = get_db()
    game = db.execute(
        "SELECT id, title, genre, release_year, rating, description FROM games WHERE id = ?",
        (game_id,),
    ).fetchone()
    if game is None:
        abort(404)
    reviews = db.execute(
        "SELECT username, score, body FROM reviews WHERE game_id = ? ORDER BY id",
        (game_id,),
    ).fetchall()
    return render_template("game_detail.html", game=game, reviews=reviews)


def resolve_public_file(filename: str) -> Path | None:
    """Возвращает путь к файлу, только если он лежит внутри PUBLIC_DIR."""
    base = PUBLIC_DIR.resolve()
    try:
        candidate = (base / filename).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    # is_relative_to покрывает и `../`, и абсолютные пути, и символические
    # ссылки, ведущие за пределы каталога.
    if candidate != base and not candidate.is_relative_to(base):
        return None
    return candidate


@app.route("/download/<path:filename>")
def download(filename):
    # ИСПРАВЛЕНО: путь нормализуется (resolve) и проверяется на принадлежность
    # каталогу lab_data/public. `../secret.txt`, абсолютные пути и ссылки
    # за пределы каталога отдают 404.
    path = resolve_public_file(filename)
    if path is None or not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="Доступ запрещён."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="Страница не найдена."), 404


if __name__ == "__main__":
    if not DATABASE.exists():
        from init_db import main
        main()
    app.run(host="127.0.0.1", port=5000, debug=False)
