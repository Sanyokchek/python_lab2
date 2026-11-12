"""GameHub Security Lab — УЯЗВИМАЯ версия (только для локального обучения).

ВНИМАНИЕ! Этот файл намеренно содержит уязвимости:
  * SQL Injection в форме входа  (/login)
  * SQL Injection в поиске игр   (/games)
  * Path Traversal в скачивании  (/download/<path:filename>)

Запускайте приложение только на 127.0.0.1 и только внутри учебной
виртуальной машины. Не используйте этот код вне лаборатории.
"""
from pathlib import Path
import re
import hashlib
import os
import sqlite3

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for, send_file

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "gamehub.sqlite3"
PUBLIC_DIR = BASE_DIR / "lab_data" / "public"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("GAMEHUB_SECRET_KEY", "local-lab-change-this-key")
app.config["DATABASE"] = str(DATABASE)


def hash_password(password: str) -> str:
    """Учебный (намеренно слабый) вариант: sha256 без соли."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


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

        # УЯЗВИМОСТЬ (SQL Injection): ввод пользователя склеивается с текстом
        # SQL-запроса, поэтому кавычка завершает строковый литерал, а `-- `
        # закомментирует оставшуюся часть условия.
        password_hash = hash_password(password)
        query = (
            f"SELECT id, username, is_admin FROM users "
            f"WHERE username = '{username}' AND password_hash = '{password_hash}'"
        )
        user = get_db().execute(query).fetchone()

        if user is not None:
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

    # УЯЗВИМОСТЬ (SQL Injection): поисковая строка попадает в SQL как есть.
    # Через UNION SELECT можно вывести данные из любой таблицы базы.
    sql = (
        f"SELECT id, title, genre, release_year, rating, description FROM games "
        f"WHERE title LIKE '%{query}%' OR genre LIKE '%{query}%'"
    )
    rows = get_db().execute(sql).fetchall()
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


@app.route("/download/<path:filename>")
def download(filename):
    # УЯЗВИМОСТЬ (Path Traversal): имя файла из URL просто приклеивается
    # к каталогу lab_data/public. `../` выводит за его пределы, поэтому
    # можно прочитать любой файл, доступный процессу приложения.
    path = os.path.join(str(PUBLIC_DIR), filename)
    if not os.path.isfile(path):
        abort(404)
    return send_file(
        os.path.abspath(path), as_attachment=True, download_name=os.path.basename(path)
    )


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
