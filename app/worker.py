import logging
import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.exchange import OrderPlacementError, place_order
from app.models import Order, OrderPlacementOutbox, OrderStatus, OutboxStatus

logger = logging.getLogger(__name__)


class OrderPlacementWorker:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="order-placement-worker")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.process_once()
            except Exception:  # pragma: no cover
                logger.exception("Unexpected worker error")
            time.sleep(settings.exchange_poll_interval_seconds)

    def process_once(self) -> None:
        with SessionLocal() as db:
            event = self._claim_next_event(db)
            if event is None:
                return
            self._process_event(db, event.id)

    def _claim_next_event(self, db: Session) -> OrderPlacementOutbox | None:
        stmt = (
            select(OrderPlacementOutbox)
            .where(OrderPlacementOutbox.status == OutboxStatus.pending)
            .order_by(OrderPlacementOutbox.created_at.asc())
            .limit(1)
        )
        event = db.execute(stmt).scalar_one_or_none()
        if event is None:
            return None

        event.status = OutboxStatus.processing
        db.commit()
        db.refresh(event)
        return event

    def _process_event(self, db: Session, event_id: str) -> None:
        event = db.get(OrderPlacementOutbox, event_id)
        if event is None:
            return

        order = db.get(Order, event.order_id)
        if order is None:
            event.status = OutboxStatus.completed
            db.commit()
            return

        try:
            place_order(order)
            order.status = OrderStatus.placed
            event.status = OutboxStatus.completed
            event.last_error = None
        except OrderPlacementError as exc:
            event.attempts += 1
            event.last_error = str(exc)
            event.status = (
                OutboxStatus.pending
                if event.attempts < settings.exchange_max_attempts
                else OutboxStatus.completed
            )
        db.commit()
