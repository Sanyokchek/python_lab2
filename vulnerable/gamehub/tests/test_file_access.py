"""Тесты скачивания файлов: Path Traversal."""


def test_public_guide_can_be_downloaded(client):
    response = client.get("/download/guide.txt")
    assert response.status_code == 200
    assert b"safe public guide" in response.data


def test_unknown_file_is_rejected(client):
    assert client.get("/download/nope.txt").status_code == 404


def test_path_traversal_relative_is_rejected(client):
    """`../secret.txt` не должен выводить за пределы каталога public."""
    # Клиент Flask нормализует URL, поэтому тестируем закодированный вариант,
    # который доходит до маршрута без нормализации.
    response = client.get("/download/%2E%2E%2Fsecret.txt")
    assert response.status_code == 404
    assert b"top-secret-marker" not in response.data


def test_path_traversal_encoded_is_rejected(client):
    """Двойное кодирование и вложенный обход тоже должны блокироваться."""
    for payload in (
        "%2E%2E%2F%2E%2E%2Fsecret.txt",
        "..%2Fsecret.txt",
        "%2e%2e%5csecret.txt",
    ):
        response = client.get(f"/download/{payload}")
        assert response.status_code == 404, payload
        assert b"top-secret-marker" not in response.data, payload
