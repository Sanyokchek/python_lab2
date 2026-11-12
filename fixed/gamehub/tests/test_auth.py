"""Функциональные и security-тесты входа и доступа."""
from conftest import login_as


def test_homepage_is_available(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Каталог игр".encode() in response.data


def test_login_rejects_wrong_password(client):
    response = login_as(client, "admin", "wrong-password")
    assert response.status_code == 200
    assert "Неверное имя пользователя или пароль".encode() in response.data


def test_login_accepts_valid_credentials(client):
    response = login_as(client, "player", "test-player-password")
    assert response.status_code == 200
    assert "Вход выполнен: player".encode() in response.data


def test_regular_user_cannot_open_admin(client):
    login_as(client, "player", "test-player-password")
    assert client.get("/admin").status_code == 403


def test_admin_can_open_admin(client):
    login_as(client, "admin", "test-admin-password")
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Доступ администратора подтверждён".encode() in response.data


# --- SQL Injection ---

def test_sqli_login_bypass_is_rejected(client):
    """Классический обход входа: `' OR 1=1 -- `."""
    response = login_as(client, "' OR 1=1 -- ", "anything")
    assert "Вход выполнен".encode() not in response.data
    assert "Неверное имя пользователя или пароль".encode() in response.data
    assert client.get("/admin").status_code == 403


def test_sqli_login_as_admin_is_rejected(client):
    """Обход входа с подстановкой конкретного администратора."""
    response = login_as(client, "admin' -- ", "anything")
    assert "Вход выполнен".encode() not in response.data
    assert client.get("/admin").status_code == 403


def test_sqli_union_in_search_does_not_leak_secrets(client):
    """UNION-инъекция в поиске не должна возвращать данные чужой таблицы."""
    payload = "%' UNION SELECT 1, name, value, 2024, 8.0, 'x' FROM lab_secrets -- "
    response = client.get("/games", query_string={"q": payload})
    assert response.status_code == 200
    assert b"TESTFLAG{should_not_be_reachable}" not in response.data


def test_search_still_works(client):
    response = client.get("/games", query_string={"q": "Neon"})
    assert response.status_code == 200
    assert b"Neon Drift" in response.data
    assert b"Hollow Depths" not in response.data


def test_game_detail_page_renders(client):
    """Страница игры должна открываться: шаблон обязан собирать ссылку на скачивание."""
    response = client.get("/games/1")
    assert response.status_code == 200
    assert b"Neon Drift" in response.data
    assert b"/download/guide.txt" in response.data


def test_unknown_game_returns_404(client):
    assert client.get("/games/999").status_code == 404


def test_homepage_contains_login_registration_and_catalog(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Создать аккаунт".encode() in response.data
    assert "Войти в аккаунт".encode() in response.data
    assert b"Neon Drift" in response.data


def test_registration_creates_regular_user_and_logs_them_in(client):
    response = client.post(
        "/register",
        data={"username": "new_student", "password": "safe-test-password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Аккаунт создан".encode() in response.data
    assert "new_student".encode() in response.data
    assert client.get("/admin").status_code == 403


def test_registration_rejects_duplicate_username(client):
    response = client.post(
        "/register",
        data={"username": "player", "password": "safe-test-password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Такой логин уже занят".encode() in response.data


def test_registration_rejects_short_password(client):
    response = client.post(
        "/register",
        data={"username": "new_student", "password": "short"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "не менее 8 символов".encode() in response.data
