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
- Black + Flake8 + MyPy (качество кода)
- Docker Compose (локальная разработка)
- GitHub Actions (CI/CD)

## Быстрый старт

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

### 4. Запустить приложение

```bash
python -m uvicorn app.main:app --reload
```

API доступен на http://localhost:8000  
Swagger-документация: http://localhost:8000/docs

### 5. Запустить тесты

```bash
python -m pytest tests/ -v
```

Ожидается **13 зелёных тестов** (9 обязательных + 4 бонусных).

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

Требует заголовок `X-Signature` с HMAC-SHA256 подписью тела запроса.

```bash
# Пример генерации подписи (Python):
python -c "import hmac, hashlib, json; body = json.dumps({'payment_id': 1, 'status': 'succeeded'}, separators=(',', ':')); print(hmac.new(b'super-secret-webhook-key', body.encode(), hashlib.sha256).hexdigest())"

curl -X POST http://localhost:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -H "X-Signature: <вычисленная_подпись>" \
  -d '{
    "payment_id": 1,
    "status": "succeeded"
  }'
```

## Проверка качества кода

Проект использует три инструмента для поддержания качества:

```bash
# Форматирование кода
black .

# Проверка стиля
flake8 .

# Проверка типов
mypy app/
```

Конфигурации находятся в `pyproject.toml` и `.flake8`.

## Миграции БД

Проект использует **Alembic** для управления схемой БД.

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
│   └── test_payments.py     # 13 тестов
├── .github/workflows/       # CI/CD (GitHub Actions)
├── .cursorrules             # Правила для AI-ассистента
├── .flake8                  # Конфиг линтера
├── pyproject.toml           # Конфиги Black, MyPy, Flake8
├── docker-compose.yml       # PostgreSQL (dev + test)
├── requirements.txt
├── pytest.ini
├── README.md
└── AI_LOG.md                # История работы с ИИ
```

## CI/CD

GitHub Actions автоматически запускает **lint + тесты** при каждом push в main/master.  
Workflow: `.github/workflows/test.yml`

### Что проверяется в CI:

1. **Black** — форматирование кода
2. **Flake8** — стиль кода
3. **MyPy** — проверка типов
4. **pytest** — все 13 тестов на PostgreSQL

## Реализованные бонусы

- ✅ Docker Compose для локальной разработки
- ✅ HMAC-SHA256 подпись вебхука (`X-Signature`)
- ✅ Alembic миграции БД
- ✅ GET /payments с фильтрами по email и status
- ✅ GitHub Actions (Black + Flake8 + MyPy + pytest)
- ✅ `.cursorrules` — правила для AI-ассистента