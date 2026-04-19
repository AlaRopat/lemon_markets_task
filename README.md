# lemon.markets backend engineering task

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d db
python -m uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000/docs`.

## Run tests

```bash
pytest -q
```

## Example request

```bash
curl -X POST http://127.0.0.1:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{
    "instrument": "DE000A0Q4RZ3",
    "type": "limit",
    "quantity": 5,
    "side": "buy",
    "limit_price": 110.50
  }'
```
