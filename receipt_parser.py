import io
import re
from datetime import date

from categories import COVERED_CATEGORIES, NEEDS_REVIEW_CATEGORY

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_NAME = "|".join(MONTHS.keys())

DATE_PATTERNS = [
    # 2026-07-20
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    # 07/20/2026 or 7-20-26
    re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b"),
    # Jul 20, 2026 / July 20 2026
    re.compile(rf"\b({_MONTH_NAME})[a-z]*\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE),
    # 20 Jul 2026
    re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_NAME})[a-z]*\.?\s+(\d{{4}})\b", re.IGNORECASE),
]

AMOUNT_PATTERN = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})*\.\d{2})\b")

CATEGORY_KEYWORDS = [
    ("Flights", [
        "airlines", "airways", "flight", "boarding pass", "delta", "united",
        "american air", "southwest", "jetblue", "alaska air", "spirit air",
    ]),
    ("Lodging", [
        "hotel", "inn", "resort", "suites", "marriott", "hilton", "hyatt",
        "motel", "lodging", "holiday inn", "best western",
    ]),
    ("Rental Car / Mileage", [
        "rental", "hertz", "avis", "enterprise rent", "budget rent", "car rental",
    ]),
    ("Meals", [
        "restaurant", "cafe", "café", "diner", "grill", "coffee",
        "starbucks", "bar & grill", "bistro", "pizzeria", "food",
    ]),
    ("Parking, Tolls & Local Transportation", [
        "parking", "toll", "uber", "lyft", "taxi", "transit", "garage",
    ]),
]


def _normalize_year(year):
    year = int(year)
    if year < 100:
        year += 2000
    return year


def _extract_date(text):
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groups()
        try:
            if len(groups[0]) == 4 and groups[0].isdigit():
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            elif groups[0].isdigit() and groups[1].isdigit():
                month, day, year = int(groups[0]), int(groups[1]), _normalize_year(groups[2])
            elif groups[0].lower()[:3] in MONTHS:
                month, day, year = MONTHS[groups[0].lower()[:3]], int(groups[1]), int(groups[2])
            else:
                month, day, year = MONTHS[groups[1].lower()[:3]], int(groups[0]), int(groups[2])
            return date(year, month, day).isoformat()
        except (ValueError, KeyError):
            continue
    return None


def _extract_amount(text):
    lines = text.splitlines()
    total_candidates = []
    for line in lines:
        lower = line.lower()
        if "total" in lower and "subtotal" not in lower:
            for m in AMOUNT_PATTERN.finditer(line):
                total_candidates.append(float(m.group(1).replace(",", "")))
    if total_candidates:
        return total_candidates[-1]

    all_amounts = [float(m.group(1).replace(",", "")) for m in AMOUNT_PATTERN.finditer(text)]
    if all_amounts:
        return max(all_amounts)
    return None


ADDRESS_OR_PHONE_HINTS = re.compile(
    r"\b(pkwy|parkway|street|st\.|avenue|ave\.|blvd|hwy|highway|drive|dr\.|road|rd\.|"
    r"suite|ste\.|po box|tel|phone|fax)\b|,\s*[A-Z]{2}\s*\d{5}|\(\d{3}\)\s?\d{3}[-\s]?\d{4}",
    re.IGNORECASE,
)

BUSINESS_KEYWORDS = [
    "inn", "suites", "hotel", "motel", "resort", "restaurant", "cafe", "café",
    "airlines", "airways", "rental", "llc", "inc", "corp", "store", "market",
    "shop", "bar", "grill", "diner", "bistro",
]

# Invoice/reservation metadata labels that sit near the top of a receipt and
# could otherwise be mistaken for the vendor name (e.g. "Room No. 213").
# Compared letters-only so OCR noise in spacing/punctuation doesn't matter.
METADATA_LABEL_PREFIXES = [
    "roomno", "cashierno", "foliono", "confno", "contno", "pageno",
    "membershipno", "groupcode", "tarecord", "locator", "invoice",
    "arrival", "departure", "checkin", "checkout",
]


def _normalize_line(line):
    return re.sub(r"\s+", " ", line.strip().lower())


def _letters_only(line):
    return re.sub(r"[^a-z]", "", line.lower())


def _looks_like_metadata_label(line):
    letters = _letters_only(line)
    return any(letters.startswith(prefix) for prefix in METADATA_LABEL_PREFIXES)


def _extract_vendor(text):
    non_blank_lines = [line for line in text.splitlines() if line.strip()]
    candidates = []
    for line in non_blank_lines[:15]:
        cleaned = line.strip()
        letters = sum(1 for c in cleaned if c.isalpha())
        if letters < 3 or ADDRESS_OR_PHONE_HINTS.search(cleaned) or _looks_like_metadata_label(cleaned):
            continue
        candidates.append(cleaned)

    if not candidates:
        return None

    # A vendor name often appears more than once near the top of a receipt —
    # e.g. split across a logo ("La Quinta" / "BY WYNDHAM") and then again in
    # full ("La Quinta Inn & Suites by Wyndham Forsyth"). When one candidate
    # line contains another, that's a strong signal it's the vendor — and the
    # longest such line is usually the fullest, most useful version of the name.
    normalized = [_normalize_line(c) for c in candidates]
    repeat_scores = [0] * len(candidates)
    for i, a in enumerate(normalized):
        for j, b in enumerate(normalized):
            if i != j and (a in b or b in a):
                repeat_scores[i] += 1

    if any(repeat_scores):
        best = max(range(len(candidates)), key=lambda i: (repeat_scores[i], len(candidates[i])))
        return candidates[best][:60]

    for candidate in candidates:
        if any(kw in candidate.lower() for kw in BUSINESS_KEYWORDS):
            return candidate[:60]

    return candidates[0][:60]


def _extract_category(text):
    lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return category
    return NEEDS_REVIEW_CATEGORY


def extract_fields_from_text(text):
    """Pure heuristic extraction from already-OCR'd text. Kept separate from
    the OCR call itself so the parsing logic can be tested without the
    tesseract binary installed."""
    text = text or ""
    return {
        "date": _extract_date(text),
        "amount": _extract_amount(text),
        "vendor": _extract_vendor(text),
        "category": _extract_category(text),
        "raw_text": text,
    }


def parse_receipt_image(file_stream):
    """Runs OCR on an uploaded image file-like object and returns guessed
    fields. Returns a result with ocr_available=False if tesseract isn't
    installed on this host, so callers can fall back to a blank form instead
    of erroring out."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return {"ocr_available": False}

    try:
        image = Image.open(file_stream)
        text = pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError:
        return {"ocr_available": False}
    except Exception:
        return {"ocr_available": False}

    result = extract_fields_from_text(text)
    result["ocr_available"] = True
    return result
