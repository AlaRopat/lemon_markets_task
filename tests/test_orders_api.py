from decimal import Decimal
from unittest.mock import patch

from app.exchange import OrderPlacementError
from app.models import Order, OrderPlacementOutbox, OrderStatus, OutboxStatus


def test_create_market_order_returns_201_and_persists_order(client, db_session):
    response = client.post(
        "/orders",
        json={
            "instrument": "DE000A0Q4RZ3",
            "type": "market",
            "quantity": 10,
            "side": "buy",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["instrument"] == "DE000A0Q4RZ3"
    assert body["status"] == "pending_placement"

    stored_order = db_session.get(Order, body["id"])
    assert stored_order is not None
    assert stored_order.quantity == 10

    outbox_event = db_session.query(OrderPlacementOutbox).filter_by(order_id=body["id"]).one()
    assert outbox_event.status == OutboxStatus.pending


def test_create_limit_order_requires_limit_price(client):
    response = client.post(
        "/orders",
        json={
            "instrument": "DE000A0Q4RZ3",
            "type": "limit",
            "quantity": 10,
            "side": "buy",
        },
    )

    assert response.status_code == 422


def test_create_market_order_rejects_limit_price(client):
    response = client.post(
        "/orders",
        json={
            "instrument": "DE000A0Q4RZ3",
            "type": "market",
            "quantity": 10,
            "side": "buy",
            "limit_price": 11.25,
        },
    )

    assert response.status_code == 422


def test_returns_500_when_database_commit_fails(client):
    with patch("app.service.OrderService.create_order", side_effect=RuntimeError("db down")):
        response = client.post(
            "/orders",
            json={
                "instrument": "DE000A0Q4RZ3",
                "type": "market",
                "quantity": 10,
                "side": "buy",
            },
        )

    assert response.status_code == 500
    assert response.json() == {"message": "Internal server error while placing the order"}


def test_worker_places_order_and_marks_outbox_completed(client, db_session, worker):
    response = client.post(
        "/orders",
        json={
            "instrument": "DE000A0Q4RZ3",
            "type": "limit",
            "quantity": 3,
            "side": "sell",
            "limit_price": 99.99,
        },
    )
    order_id = response.json()["id"]

    with patch("app.worker.place_order", return_value=None):
        worker.process_once()

    order = db_session.get(Order, order_id)
    outbox_event = db_session.query(OrderPlacementOutbox).filter_by(order_id=order_id).one()

    assert order.status == OrderStatus.placed
    assert outbox_event.status == OutboxStatus.completed
    assert Decimal(str(response.json()["limit_price"])) == Decimal("99.9900")


def test_worker_retries_after_exchange_failure(client, db_session, worker):
    response = client.post(
        "/orders",
        json={
            "instrument": "DE000A0Q4RZ3",
            "type": "market",
            "quantity": 1,
            "side": "buy",
        },
    )
    order_id = response.json()["id"]

    with patch("app.worker.place_order", side_effect=OrderPlacementError("Failed to place the order at the stock exchange")):
        try:
            worker.process_once()
        except Exception:
            pass

    outbox_event = db_session.query(OrderPlacementOutbox).filter_by(order_id=order_id).one()
    order = db_session.get(Order, order_id)

    assert outbox_event.status == OutboxStatus.pending
    assert outbox_event.attempts == 1
    assert order.status == OrderStatus.pending_placement
