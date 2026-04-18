# Solution

## Overview

I implemented the API with **FastAPI + SQLAlchemy + PostgreSQL** and used the **transactional outbox pattern** to satisfy the key reliability requirement:

> the reliability of the stock exchange must not impact the reliability of `POST /orders`.

The endpoint does **not** call the exchange directly. Instead, it stores:
1. the order row, and
2. an outbox event that represents the future placement action,

inside the **same database transaction**.

Once that transaction commits successfully, the API can safely return `201`, because the system now guarantees that the order **will be attempted and retried** by the worker. This is the critical durability guarantee.

## Main design decisions

### 1. Transactional outbox instead of synchronous exchange call

A naive approach would call the exchange inside `POST /orders`. That would make the endpoint slow and fragile because:
- the external system can fail,
- the external call adds latency,
- it ties API availability to exchange availability.

Instead, the endpoint persists an outbox message and returns immediately after commit.

### 2. Background worker for reliable asynchronous placement

A background worker polls pending outbox events and calls the dummy exchange function.

Behavior:
- picks a pending outbox event,
- marks it as processing,
- calls `place_order(order)`,
- on success: marks the order as `placed` and the outbox event as `completed`,
- on `OrderPlacementError`: stores the error, increments the attempt counter, and requeues the event.

This keeps the request path short and resilient.

### 3. Persistence model

There are two tables:
- `orders`
- `order_placement_outbox`

This separation makes recovery possible after crashes. If the API process dies after returning `201`, the outbox row is still in Postgres, so another worker instance can continue processing.

### 4. Error contract

Unexpected endpoint failures return:

```json
{"message": "Internal server error while placing the order"}
```

with status code `500`, matching the task.

## Assumptions

1. “Guaranteed that the order will be placed” means **durably recorded for asynchronous placement with retries**, not “already accepted by the exchange before returning”.
2. It is acceptable for the returned order state to initially be `pending_placement`.
3. A simple polling worker is enough for the coding task. In production, I would likely replace it with a message broker or dedicated job system.
4. The exchange placement simulator is intentionally unreliable, so retry behavior is expected.

## Validation rules

Implemented request validation:
- `instrument` must be a 12-character alphanumeric string,
- `type` must be `market` or `limit`,
- `side` must be `buy` or `sell`,
- `quantity` must be `> 0`,
- `limit_price` is required only for `limit` orders,
- `limit_price` must not be present for `market` orders.

## Testing strategy

### Implemented tests

I added automated tests for:
- successful order creation,
- validation for missing `limit_price` on limit orders,
- validation for forbidden `limit_price` on market orders,
- `500` response contract on internal failures,
- worker success path,
- worker retry-oriented behavior after exchange failure.

### How I would test the whole application

#### Unit tests
- request validation,
- order service behavior,
- exchange adapter behavior,
- worker state transitions,
- retry logic,
- serialization and response mapping.

#### Integration tests
- API + real Postgres,
- transaction behavior: order and outbox row committed together,
- worker picks persisted outbox rows and updates status correctly,
- restart recovery: create order, stop app, restart worker, verify eventual placement.

#### End-to-end tests
- run app with Docker Compose,
- send HTTP request to `POST /orders`,
- verify returned payload,
- verify DB state,
- verify eventual transition from `pending_placement` to `placed`.

#### Reliability tests
- simulate many concurrent order creations,
- simulate frequent exchange failures,
- verify no accepted order is lost,
- verify worker resumes after crash,
- verify duplicate processing protection.

## Improvements for the future

1. **Use `SELECT ... FOR UPDATE SKIP LOCKED`** in Postgres for stronger multi-worker concurrency control.
2. **Add Alembic migrations** instead of `create_all()`.
3. **Expose `GET /orders/{id}`** so clients can observe placement progress.
4. **Introduce exponential backoff** for retries.
5. **Dead-letter handling** for events that exceed max retries.
6. **Idempotency key support** on `POST /orders`.
7. **Observability**: structured logs, metrics, tracing, alerts.
8. **Message broker** replacement for polling, e.g. Kafka/SQS/RabbitMQ.
9. **Stronger ISIN validation** using checksum rules.
10. **Separate process for the worker** instead of in-process thread inside the API container.
11. **Testcontainers for Postgres** in CI to avoid SQLite-specific differences.
12. **Exactly-once safeguards** if the exchange interface supports idempotent external identifiers.

## Why this solution fits the requirements

- **Requirement 1**: the order is stored in the database.
- **Requirement 2**: the order is placed through a dummy stock exchange integration.
- **Requirement 3**: `201` is returned only after the order and its durable placement intent are committed.
- **Requirement 4**: internal failures return the required `500` body.
- **Requirement 5**: the endpoint remains reliable because the slow and flaky exchange dependency is decoupled from the request path.
