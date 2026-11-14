import base64
import binascii
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session, selectinload

from database import Base, create_database
from models import Item, Receipt
from receipt_reader import (
    ImageUnreadableError,
    MAX_UPLOAD_BYTES,
    NoItemsFoundError,
    ReaderAPIError,
    ReaderConfigurationError,
    ReaderRateLimitError,
    read_receipt,
)
from schemas import MonthlySpendingRead, PurchasedItemRead, ReceiptCreate, ReceiptRead

STATIC_DIR = Path(__file__).parent / "static"


def create_app(database_url: Optional[str] = None) -> FastAPI:
    engine, session_factory = create_database(database_url)
    Base.metadata.create_all(bind=engine)
    app = FastAPI(title="Grocery Tracker")
    app.state.session_factory = session_factory
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    @app.get("/")
    def home():
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/api/scan")
    async def scan_receipt(file: UploadFile = File(...)):
        content = await file.read(12 * 1024 * 1024 + 1)
        try:
            return read_receipt(content)
        except ReaderRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except ImageUnreadableError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except NoItemsFoundError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ReaderConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ReaderAPIError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/receipts", response_model=ReceiptRead, status_code=201)
    def save_receipt(payload: ReceiptCreate, db: Session = Depends(get_db)):
        save_images = os.getenv("STORE_RECEIPT_IMAGES", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        image_data = None
        if payload.image_data:
            if not save_images:
                raise HTTPException(
                    status_code=400,
                    detail="Image storage is disabled. Enable STORE_RECEIPT_IMAGES in .env to save images.",
                )
            try:
                image_data = base64.b64decode(payload.image_data, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(status_code=422, detail="Invalid receipt image data.") from exc
            if len(image_data) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=422, detail="Receipt image must be under 12 MB.")

        receipt = Receipt(
            store_name=payload.store_name,
            purchase_date=payload.purchase_date,
            total_amount=payload.total_amount,
            image_data=image_data,
            items=[
                Item(
                    name=item.name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_price=item.total_price,
                )
                for item in payload.items
            ],
        )
        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        return receipt

    @app.get("/api/receipts", response_model=list[ReceiptRead])
    def list_receipts(db: Session = Depends(get_db)):
        query = select(Receipt).options(selectinload(Receipt.items)).order_by(
            Receipt.purchase_date.desc(), Receipt.id.desc()
        )
        return db.scalars(query).all()

    @app.get("/api/items", response_model=list[PurchasedItemRead])
    def list_items(
        q: str = Query(default="", max_length=100),
        db: Session = Depends(get_db),
    ):
        query = (
            select(Item, Receipt.purchase_date, Receipt.store_name)
            .join(Receipt)
            .order_by(Receipt.purchase_date.desc(), Item.id.desc())
        )
        if q.strip():
            pattern = f"%{q.strip()}%"
            query = query.where(or_(Item.name.ilike(pattern), Receipt.store_name.ilike(pattern)))

        return [
            {
                "id": item.id,
                "name": item.name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "purchase_date": purchase_date,
                "store_name": store_name,
            }
            for item, purchase_date, store_name in db.execute(query)
        ]

    @app.get("/api/spending", response_model=MonthlySpendingRead)
    def monthly_spending(
        month: str = Query(default_factory=lambda: date.today().strftime("%Y-%m"), pattern=r"^\d{4}-\d{2}$"),
        db: Session = Depends(get_db),
    ):
        try:
            selected = datetime.strptime(month, "%Y-%m").date()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Month must use YYYY-MM format.") from exc
        total = db.scalar(
            select(func.coalesce(func.sum(Receipt.total_amount), 0)).where(
                extract("year", Receipt.purchase_date) == selected.year,
                extract("month", Receipt.purchase_date) == selected.month,
            )
        )
        return {"month": month, "total": Decimal(str(total or 0))}

    return app


app = create_app()
