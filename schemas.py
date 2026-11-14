from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReceiptItemInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    total_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Item name cannot be blank")
        return cleaned


class ReceiptCreate(BaseModel):
    store_name: str = Field(min_length=1, max_length=200)
    purchase_date: date
    total_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    items: list[ReceiptItemInput] = Field(min_length=1)
    image_data: Optional[str] = Field(default=None, max_length=16 * 1024 * 1024)

    @field_validator("store_name")
    @classmethod
    def clean_store_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Store name cannot be blank")
        return cleaned


class ReceiptItemRead(ReceiptItemInput):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    store_name: str
    purchase_date: date
    total_amount: Decimal
    created_at: datetime
    items: list[ReceiptItemRead]


class PurchasedItemRead(BaseModel):
    id: int
    name: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal
    purchase_date: date
    store_name: str


class MonthlySpendingRead(BaseModel):
    month: str
    total: Decimal
