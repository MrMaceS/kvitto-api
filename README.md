# Kvitto API

API для приёма платежей онлайн-школы "Квитто".

## Стек

- Python 3.11+
- FastAPI
- PostgreSQL 16
- SQLAlchemy 2.0 (async)
- Pydantic v2
- Alembic (миграции БД)
- pytest + httpx (тесты)
- Ruff + Flake8 + MyPy (качество кода)
- Docker Compose (локальная разработка)
- GitHub Actions (CI/CD)

## Быстрый старт

Нужны Python 3.11+ и Docker (Docker используется только для PostgreSQL — само приложение
запускается локально).

### 1. Поднять PostgreSQL

```bash
docker compose up -d
```

Это запустит две БД:
- `kvitto` на порту 5432 — для разработки
- `kvitto_test` на порту 5433 — для тестов

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Применить миграции БД

```bash
alembic upgrade head
```

Приложение таблицы само **не создаёт** — этот шаг обязателен. Без него старт завершится
ошибкой `relation "tariffs" does not exist`.

### 4. Запустить приложение

```bash
python -m uvicorn app.main:app --reload
```

При старте приложение создаёт три тарифа (basic, standard, premium); повторный запуск
дубликатов не создаёт.

API доступен на http://localhost:8000  
Swagger-документация: http://localhost:8000/docs

### 5. Запустить тесты

```bash
python -m pytest tests/ -v
```

Для тестов нужна запущенная тестовая БД на порту 5433 (шаг 1). Таблицы в ней тесты
создают и удаляют сами, миграции для них не нужны.

Ожидается **24 зелёных теста**: пять обязательных групп из ТЗ (промокод, график рассрочки,
идемпотентность, запрещённый переход, 404) плюс проверки вебхука с подписью, фильтров
`GET /payments` и пограничных случаев.

## Настройки (переменные окружения)

Задаются переменными окружения или файлом `.env` (шаблон — `.env.example`).
Без них используются значения по умолчанию, подходящие для локального запуска.

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://kvitto:kvitto@localhost:5432/kvitto` | БД приложения и Alembic |
| `WEBHOOK_SECRET` | `super-secret-webhook-key` | секрет HMAC-подписи вебхука |
| `PROMO_CODE` | `KVITTO10` | промокод (регистр не важен) |
| `PROMO_DISCOUNT_PERCENT` | `10` | размер скидки, % |

Тесты всегда используют `postgresql+asyncpg://kvitto_test:kvitto_test@localhost:5433/kvitto_test`
(зашито в `tests/conftest.py`) и `DATABASE_URL` не читают.

## Правила API

- **Деньги** — целые копейки (`1990000` = 19 900 ₽), `float` не используется.
- **Промокод** `KVITTO10` даёт −10% от цены тарифа. Поле `amount` — сумма к оплате,
  `discount` — размер скидки в копейках. Неизвестный промокод → `422`.
- **Способ оплаты:** `card`, `sbp` или `installment`. Для `installment` обязателен
  `installment_months` (3, 6 или 12), для `card` и `sbp` это поле передавать нельзя (`422`).
- **График рассрочки** считается от суммы после скидки; лишние копейки идут в первые платежи.
- **Идемпотентность:** при повторе `Idempotency-Key` возвращается тот же платёж с кодом `200`,
  второй не создаётся. Запросы без ключа никогда не объединяются.
- **Вебхук банка** требует заголовок `X-Signature` (HMAC-SHA256 от тела запроса). Допустимые
  переходы: `pending → succeeded`, `pending → failed`, `succeeded → refunded`. Остальные дают
  `409 {"error": "invalid_transition"}`, статус при этом не меняется. Нет подписи или она
  неверна — `401`, платёж не найден — `404`, успех — `200 {"result": "ok"}`.

## Примеры запросов

### Получить список тарифов

```bash
curl http://localhost:8000/tariffs
```

### Создать платёж (карта)

```bash
curl -X POST http://localhost:8000/payments \
  -H "Content-Type: application/json" \
  -d '{
    "tariff_id": 1,
    "email": "user@example.com",
    "method": "card"
  }'
```

### Создать платёж с промокодом

```bash
curl -X POST http://localhost:8000/payments \
  -H "Content-Type: application/json" \
  -d '{
    "tariff_id": 2,
    "email": "user@example.com",
    "method": "card",
    "promo_code": "KVITTO10"
  }'
```

### Создать платёж в рассрочку

```bash
curl -X POST http://localhost:8000/payments \
  -H "Content-Type: application/json" \
  -d '{
    "tariff_id": 2,
    "email": "user@example.com",
    "method": "installment",
    "installment_months": 3
  }'
```

### Создать платёж с идемпотентностью

```bash
curl -X POST http://localhost:8000/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-key-123" \
  -d '{
    "tariff_id": 1,
    "email": "user@example.com",
    "method": "card"
  }'
```

### Получить платёж

```bash
curl http://localhost:8000/payments/1
```

### Список платежей с фильтрами

```bash
curl "http://localhost:8000/payments?email=user@example.com&status=succeeded"
```

### Обновить статус платежа (вебхук от банка)

Требует заголовок `X-Signature` с HMAC-SHA256 подписью **точного** тела запроса
(секрет — `WEBHOOK_SECRET`).

```bash
$BODY = '{"payment_id":8,"status":"succeeded"}'
$SECRET = "super-secret-webhook-key"
$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [System.Text.Encoding]::UTF8.GetBytes($SECRET)
$hashBytes = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($BODY))
$SIG = -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
Write-Host "Твоя подпись: $SIG"

curl -X POST http://localhost:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIG" \
  -d "$BODY"
```

## Проверка качества кода

```bash
# Линтер и проверка форматирования (то же самое запускает CI)
ruff check .
ruff format --check .

# Дополнительно: стиль и типы
flake8 .
mypy app/
```

Автоформатирование — `ruff format .`. Конфигурации находятся в `pyproject.toml` и `.flake8`.

## Миграции БД

Схемой БД управляет **Alembic**: `alembic upgrade head` создаёт таблицы `tariffs` и `payments`.
Адрес БД берётся из `DATABASE_URL`, а не из `alembic.ini`.

### Создать новую миграцию (после изменения моделей)

```bash
alembic revision --autogenerate -m "Описание изменений"
```

### Применить все миграции

```bash
alembic upgrade head
```

### Откатить последнюю миграцию

```bash
alembic downgrade -1
```

### Проверить текущую ревизию

```bash
alembic current
```

### Проверить, что модели и миграции совпадают

```bash
alembic check
```

## Структура проекта

```
kvitto-api/
├── app/
│   ├── main.py              # Точка входа
│   ├── config.py            # Конфигурация (Pydantic Settings)
│   ├── database.py          # Подключение к БД
│   ├── seed.py              # Сидирование тарифов
│   ├── models/              # SQLAlchemy модели
│   ├── schemas/             # Pydantic схемы
│   ├── routers/             # FastAPI роутеры
│   └── services/            # Бизнес-логика
├── alembic/                 # Миграции БД
├── tests/
│   ├── conftest.py          # Фикстуры pytest
│   └── test_payments.py     # 24 теста
├── .github/workflows/       # CI/CD (GitHub Actions)
├── .cursorrules             # Правила для AI-ассистента
├── .flake8                  # Конфиг линтера
├── pyproject.toml           # Конфиги Ruff, MyPy, Flake8
├── docker-compose.yml       # PostgreSQL (dev + test)
├── requirements.txt
├── pytest.ini
├── README.md
└── AI_LOG.md                # История работы с ИИ
```

## CI/CD

GitHub Actions автоматически запускает **lint + тесты** при каждом push в main/master
и при pull request в эти ветки.  
Workflow: `.github/workflows/test.yml`

### Что проверяется в CI:

1. **Ruff** — `ruff check .` и `ruff format --check .`
2. **pytest** — все 24 теста на PostgreSQL (сервис в контейнере)

## Реализованные бонусы

- ✅ Docker Compose поднимает PostgreSQL для разработки и тестов (приложение в контейнер не упаковано)
- ✅ HMAC-SHA256 подпись вебхука (`X-Signature`)
- ✅ Alembic миграции БД
- ✅ GET /payments с фильтрами по email и status
- ✅ GitHub Actions (Ruff + pytest)
- ✅ `.cursorrules` — правила для AI-ассистента