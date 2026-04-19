from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Order, OrderPlacementOutbox, OrderStatus, OutboxStatus
from app.schemas import OrderCreateRequest


class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def create_order(self, request: OrderCreateRequest) -> Order:
        order = Order(
            instrument=request.instrument,
            type=request.type,
            quantity=request.quantity,
            side=request.side,
            limit_price=request.limit_price,
            status=OrderStatus.pending_placement,
        )
        outbox_event = OrderPlacementOutbox(order=order, status=OutboxStatus.pending)

        self.db.add(order)
        self.db.add(outbox_event)
        self.db.commit()
        self.db.refresh(order)
        return order





