from contextlib import asynccontextmanager

import fastapi
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.schemas import ErrorResponse, OrderCreateRequest, OrderResponse
from app.service import OrderService
from app.worker import OrderPlacementWorker

worker = OrderPlacementWorker()


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    Base.metadata.create_all(bind=engine)
    worker.start()
    yield
    worker.stop()


app = fastapi.FastAPI(title="lemon.markets backend task", lifespan=lifespan)


@app.exception_handler(Exception)
async def generic_exception_handler(_: fastapi.Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, SQLAlchemyError):
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(message="Internal server error while placing the order").model_dump(),
        )
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(message="Internal server error while placing the order").model_dump(),
    )


@app.post(
    "/orders",
    response_model=OrderResponse,
    status_code=201,
    responses={500: {"model": ErrorResponse}},
)
def create_order(request: OrderCreateRequest, db: Session = fastapi.Depends(get_db)) -> OrderResponse:
    order = OrderService(db).create_order(request)
    return OrderResponse.model_validate(order)
