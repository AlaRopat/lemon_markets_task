from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OrderCreateRequest(BaseModel):
    instrument: str = Field(min_length=12, max_length=12, examples=["DE000A0Q4RZ3"])
    type: Literal["market", "limit"]
    quantity: int = Field(gt=0)
    side: Literal["buy", "sell"]
    limit_price: Decimal | None = Field(default=None, gt=0)

    @field_validator("instrument")
    @classmethod
    def instrument_must_look_like_isin(cls, value: str) -> str:
        if not value.isalnum():
            raise ValueError("instrument must be a valid ISIN")
        return value.upper()

    @model_validator(mode="after")
    def validate_limit_price(self) -> "OrderCreateRequest":
        if self.type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        if self.type == "market" and self.limit_price is not None:
            raise ValueError("limit_price must not be provided for market orders")
        return self


class OrderResponse(BaseModel):
    id: str
    instrument: str
    type: str
    quantity: int
    side: str
    limit_price: Decimal | None
    status: str

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    message: str
