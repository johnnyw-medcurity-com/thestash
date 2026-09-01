import base64
import io
import json
import os
import re
import sys
import traceback

from PIL import Image, ImageOps

from categories import ALL_CATEGORIES, NEEDS_REVIEW_CATEGORY, MILEAGE_CATEGORY

MODEL = "claude-sonnet-5"
MAX_IMAGE_DIMENSION = 1568  # Claude's vision pipeline resizes above this anyway.
JPEG_QUALITY = 85

# A photographed receipt can never legitimately be a mileage entry -- that
# category is manually entered from an odometer reading, not a receipt --
# so it's excluded from what the model is allowed to pick.
PROMPT_CATEGORIES = [c for c in ALL_CATEGORIES if c != MILEAGE_CATEGORY]

SYSTEM_PROMPT = (
    "You extract structured data from photos of business travel expense receipts. "
    "Look at the image carefully -- read every line, not just the most prominent text -- "
    "and respond with ONLY a single JSON object, no markdown code fences, no explanation. "
    "The JSON must have exactly these keys:\n"
    '- "date": the transaction date in YYYY-MM-DD format, or null if not visible\n'
    '- "vendor": the business/merchant name, or null if not visible\n'
    '- "amount": the final total amount paid, as a plain number with no currency symbol '
    "or thousands separator, or null if not visible\n"
    f'- "category": your best-guess ONE of these exact strings: {json.dumps(PROMPT_CATEGORIES)}\n\n'
    "If you cannot make out a field confidently, use null for it rather than guessing -- "
    "a missing field the person can fill in themselves is far better than a wrong one."
)


def _prepare_image(file_stream):
    with Image.open(file_stream) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _extract_json(text):
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def parse_receipt_with_ai(file_stream):
    """Returns a dict matching the same contract as the Tesseract-based
    parser, or None if AI parsing isn't available/configured or fails for
    any reason -- callers should fall back to the OCR-based parser. Every
    early-return logs why, to stderr (PythonAnywhere's error log), so a
    misconfigured key or missing dependency doesn't look identical to
    "AI just wasn't confident" -- see also the "source" field the caller
    attaches to its response for a same-request, no-log-diving answer."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ai_receipt_parser] ANTHROPIC_API_KEY is not set -- falling back to OCR", file=sys.stderr)
        return None

    try:
        import anthropic
    except ImportError:
        print("[ai_receipt_parser] 'anthropic' package not installed (pip install -r requirements.txt?) -- falling back to OCR", file=sys.stderr)
        return None

    try:
        image_b64 = _prepare_image(file_stream)
    except Exception:
        print("[ai_receipt_parser] Failed to prepare/downscale the image:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
                    },
                    {"type": "text", "text": "Extract the fields from this receipt."},
                ],
            }],
        )
    except Exception:
        print("[ai_receipt_parser] API call failed:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None

    text = "".join(block.text for block in response.content if block.type == "text")
    data = _extract_json(text)
    if data is None:
        print(f"[ai_receipt_parser] Could not find JSON in the model's response: {text[:500]!r}", file=sys.stderr)
        return None

    category = data.get("category")
    if category not in PROMPT_CATEGORIES:
        category = NEEDS_REVIEW_CATEGORY

    amount = data.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None

    date = data.get("date")
    if not isinstance(date, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        date = None

    vendor = data.get("vendor")
    if not isinstance(vendor, str) or not vendor.strip():
        vendor = None

    return {
        "ocr_available": True,
        "source": "ai",
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "category": category,
        "raw_text": text.strip(),
    }
