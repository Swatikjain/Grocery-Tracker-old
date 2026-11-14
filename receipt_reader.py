import io
import os
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from httpx import HTTPError
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError

load_dotenv()

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1600


class ExtractedItem(BaseModel):
    name: str = Field(description="Item name as printed on the receipt")
    quantity: float = Field(gt=0, description="Quantity purchased")
    unit_price: float = Field(ge=0, description="Price per unit")
    total_price: float = Field(ge=0, description="Line total for this item")


class ExtractedReceipt(BaseModel):
    store_name: str = Field(description="Store or merchant name")
    purchase_date: Optional[date] = Field(
        default=None, description="Purchase date in YYYY-MM-DD format, or null if unreadable"
    )
    items: list[ExtractedItem] = Field(description="Purchased grocery items")
    total_amount: float = Field(ge=0, description="Final receipt total")
    image_readable: bool = Field(
        description="Whether the receipt text is clear enough to extract accurately"
    )


class ReceiptReaderError(Exception):
    """Base error for receipt image processing and extraction."""


class ImageUnreadableError(ReceiptReaderError):
    pass


class NoItemsFoundError(ReceiptReaderError):
    pass


class ReaderConfigurationError(ReceiptReaderError):
    pass


class ReaderRateLimitError(ReceiptReaderError):
    pass


class ReaderAPIError(ReceiptReaderError):
    pass


def resize_image(image_bytes: bytes) -> Tuple[bytes, str]:
    if not image_bytes:
        raise ImageUnreadableError("The uploaded image is empty.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise ImageUnreadableError("Image is too large. Please upload a photo under 12 MB.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image = image.convert("RGB")
            image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
            return output.getvalue(), "image/jpeg"
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise ImageUnreadableError(
            "We couldn't read that image. Try a clear JPG, PNG, or WebP photo."
        ) from exc


def _client() -> Tuple[genai.Client, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if not api_key:
        raise ReaderConfigurationError(
            "GEMINI_API_KEY is missing. Add your key to the .env file and restart the app."
        )
    return genai.Client(api_key=api_key), model


def read_receipt(image_bytes: bytes) -> dict:
    resized, mime_type = resize_image(image_bytes)
    client, model = _client()
    prompt = (
        "Read this grocery receipt. Extract every purchasable line item with its printed name, "
        "quantity, unit price, and line total. Exclude subtotals, tax, discounts, and payment "
        "lines from items. Include the final amount paid as total_amount. Use null for "
        "purchase_date if it is missing or unreadable. Set image_readable to false if the "
        "receipt is too blurry, cut off, or otherwise impossible to read reliably. Do not "
        "invent values; use quantity 1 only when no quantity is shown and the item is legible."
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=resized, mime_type=mime_type), prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractedReceipt,
                temperature=0,
            ),
        )
    except genai_errors.APIError as exc:
        if str(getattr(exc, "code", "")) == "429":
            raise ReaderRateLimitError(
                "Gemini's free-tier limit was reached. Please try again in a minute."
            ) from exc
        raise ReaderAPIError("Gemini couldn't read the receipt right now. Please try again.") from exc
    except HTTPError as exc:
        raise ReaderAPIError("Gemini couldn't be reached. Please check your connection and retry.") from exc

    try:
        extracted = ExtractedReceipt.model_validate_json(response.text or "")
    except (ValidationError, ValueError, TypeError) as exc:
        raise ReaderAPIError(
            "Gemini returned an unreadable result. Please try another photo."
        ) from exc

    if not extracted.image_readable:
        raise ImageUnreadableError(
            "This receipt looks blurry or cut off. Try a clearer, well-lit photo."
        )
    if not extracted.items:
        raise NoItemsFoundError(
            "No grocery items were found. Make sure the full receipt is visible and try again."
        )

    needs_confirmation = extracted.purchase_date is None
    return {
        "store_name": extracted.store_name.strip() or "Unknown store",
        "purchase_date": extracted.purchase_date or date.today(),
        "date_needs_confirmation": needs_confirmation,
        "items": [item.model_dump(mode="json") for item in extracted.items],
        "total_amount": extracted.total_amount,
    }
