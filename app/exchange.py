import random
import time

from app.models import Order


class OrderPlacementError(Exception):
    pass


def place_order(order: Order) -> None:
    if random.random() < 0.1:
        raise OrderPlacementError("Failed to place the order at the stock exchange")

    time.sleep(0.5)
