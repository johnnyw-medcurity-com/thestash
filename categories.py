MILEAGE_CATEGORY = "Mileage (Personal Vehicle)"

# Absolute last-resort fallback if the mileage_rates table is ever empty
# (shouldn't happen -- database.py seeds it on first run). The live,
# user-editable rate history lives in the database now, managed via
# /api/mileage-rates, not here.
LEGACY_MILEAGE_RATE = 0.725

COVERED_CATEGORIES = [
    "Flights",
    "Lodging",
    "Rental Car / Mileage",
    MILEAGE_CATEGORY,
    "Fuel",
    "Meals",
    "Parking, Tolls & Local Transportation",
    "Other Direct Trip Cost",
]

NEEDS_REVIEW_CATEGORY = "Other (Needs Review)"

ALL_CATEGORIES = COVERED_CATEGORIES + [NEEDS_REVIEW_CATEGORY]
