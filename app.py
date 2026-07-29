import datetime
import os
import uuid
from pathlib import Path

from flask import Flask, request, jsonify, g, send_file, send_from_directory
from werkzeug.utils import secure_filename

from database import get_db, init_db, DATA_DIR
from auth import hash_password, verify_password, create_token, require_auth
from categories import COVERED_CATEGORIES, NEEDS_REVIEW_CATEGORY, ALL_CATEGORIES
from pdf_report import build_trip_pdf
from receipt_parser import parse_receipt_image

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "heic", "webp", "pdf"}
MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

init_db()


def now_iso():
    return datetime.datetime.utcnow().isoformat()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def user_public(user):
    return {"id": user["id"], "name": user["name"], "email": user["email"]}


def trip_public(row, total=None):
    d = {
        "id": row["id"],
        "user_id": row["user_id"],
        "client_id": row["client_id"],
        "client_name": row["client_name"] if "client_name" in row.keys() else None,
        "purpose": row["purpose"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "status": row["status"],
        "created_at": row["created_at"],
    }
    if total is not None:
        d["total"] = total
    return d


def expense_public(row):
    return {
        "id": row["id"],
        "trip_id": row["trip_id"],
        "date": row["date"],
        "category": row["category"],
        "vendor": row["vendor"],
        "amount": row["amount"],
        "notes": row["notes"],
        "flagged": bool(row["flagged"]),
        "receipt_filename": row["receipt_filename"],
        "created_at": row["created_at"],
    }


# ---------- Static app shell ----------


@app.route("/")
def index():
    from flask import render_template

    return render_template("index.html")


# ---------- Auth ----------


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        db.close()
        return jsonify({"error": "An account with that email already exists"}), 409

    cur = db.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (name, email, hash_password(password), now_iso()),
    )
    db.commit()
    user_id = cur.lastrowid
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()

    token = create_token(user_id)
    return jsonify({"token": token, "user": user_public(user)}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    db.close()

    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_token(user["id"])
    return jsonify({"token": token, "user": user_public(user)})


@app.route("/api/me")
@require_auth
def me():
    return jsonify(user_public(g.user))


# ---------- Categories ----------


@app.route("/api/categories")
@require_auth
def categories():
    return jsonify({"covered": COVERED_CATEGORIES, "needs_review": NEEDS_REVIEW_CATEGORY})


# ---------- Clients ----------


@app.route("/api/clients", methods=["GET"])
@require_auth
def list_clients():
    db = get_db()
    rows = db.execute("SELECT * FROM clients ORDER BY name COLLATE NOCASE").fetchall()
    db.close()
    return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])


@app.route("/api/clients", methods=["POST"])
@require_auth
def create_client():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Client name is required"}), 400

    db = get_db()
    existing = db.execute("SELECT * FROM clients WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if existing:
        db.close()
        return jsonify({"id": existing["id"], "name": existing["name"]}), 200

    cur = db.execute(
        "INSERT INTO clients (name, created_by, created_at) VALUES (?, ?, ?)",
        (name, g.user["id"], now_iso()),
    )
    db.commit()
    client_id = cur.lastrowid
    db.close()
    return jsonify({"id": client_id, "name": name}), 201


# ---------- Trips ----------


def get_owned_trip(db, trip_id, user_id):
    return db.execute(
        "SELECT trips.*, clients.name AS client_name FROM trips "
        "JOIN clients ON clients.id = trips.client_id "
        "WHERE trips.id = ? AND trips.user_id = ?",
        (trip_id, user_id),
    ).fetchone()


@app.route("/api/trips", methods=["GET"])
@require_auth
def list_trips():
    db = get_db()
    rows = db.execute(
        "SELECT trips.*, clients.name AS client_name, "
        "COALESCE((SELECT SUM(amount) FROM expenses WHERE expenses.trip_id = trips.id), 0) AS total "
        "FROM trips JOIN clients ON clients.id = trips.client_id "
        "WHERE trips.user_id = ? ORDER BY trips.start_date DESC, trips.created_at DESC",
        (g.user["id"],),
    ).fetchall()
    db.close()
    return jsonify([trip_public(r, total=r["total"]) for r in rows])


@app.route("/api/trips", methods=["POST"])
@require_auth
def create_trip():
    data = request.get_json(force=True) or {}
    client_id = data.get("client_id")
    purpose = (data.get("purpose") or "").strip()
    start_date = data.get("start_date") or ""
    end_date = data.get("end_date") or ""

    if not client_id:
        return jsonify({"error": "A client is required"}), 400
    if not start_date or not end_date:
        return jsonify({"error": "Start and end dates are required"}), 400

    db = get_db()
    client = db.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if not client:
        db.close()
        return jsonify({"error": "Client not found"}), 404

    cur = db.execute(
        "INSERT INTO trips (user_id, client_id, purpose, start_date, end_date, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'draft', ?)",
        (g.user["id"], client_id, purpose, start_date, end_date, now_iso()),
    )
    db.commit()
    trip_id = cur.lastrowid
    row = get_owned_trip(db, trip_id, g.user["id"])
    db.close()
    return jsonify(trip_public(row, total=0)), 201


@app.route("/api/trips/<int:trip_id>", methods=["GET"])
@require_auth
def get_trip(trip_id):
    db = get_db()
    row = get_owned_trip(db, trip_id, g.user["id"])
    if not row:
        db.close()
        return jsonify({"error": "Trip not found"}), 404
    expenses = db.execute(
        "SELECT * FROM expenses WHERE trip_id = ? ORDER BY date ASC, id ASC", (trip_id,)
    ).fetchall()
    db.close()
    total = sum(e["amount"] or 0 for e in expenses)
    result = trip_public(row, total=total)
    result["expenses"] = [expense_public(e) for e in expenses]
    return jsonify(result)


@app.route("/api/trips/<int:trip_id>", methods=["PATCH"])
@require_auth
def update_trip(trip_id):
    db = get_db()
    row = get_owned_trip(db, trip_id, g.user["id"])
    if not row:
        db.close()
        return jsonify({"error": "Trip not found"}), 404

    data = request.get_json(force=True) or {}
    fields = {}
    for key in ("purpose", "start_date", "end_date", "status", "client_id"):
        if key in data:
            fields[key] = data[key]

    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        db.execute(
            f"UPDATE trips SET {set_clause} WHERE id = ?",
            (*fields.values(), trip_id),
        )
        db.commit()

    row = get_owned_trip(db, trip_id, g.user["id"])
    db.close()
    return jsonify(trip_public(row))


@app.route("/api/trips/<int:trip_id>", methods=["DELETE"])
@require_auth
def delete_trip(trip_id):
    db = get_db()
    row = get_owned_trip(db, trip_id, g.user["id"])
    if not row:
        db.close()
        return jsonify({"error": "Trip not found"}), 404

    expenses = db.execute("SELECT receipt_filename FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    db.execute("DELETE FROM expenses WHERE trip_id = ?", (trip_id,))
    db.execute("DELETE FROM report_log WHERE trip_id = ?", (trip_id,))
    db.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
    db.commit()
    db.close()

    for e in expenses:
        if e["receipt_filename"]:
            path = UPLOAD_DIR / e["receipt_filename"]
            if path.exists():
                path.unlink()

    return jsonify({"ok": True})


# ---------- Receipt parsing ----------


@app.route("/api/receipts/parse", methods=["POST"])
@require_auth
def parse_receipt():
    file = request.files.get("receipt")
    if not file or not file.filename:
        return jsonify({"error": "No receipt file provided"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported receipt file type"}), 400

    result = parse_receipt_image(file.stream)
    if not result.get("ocr_available"):
        return jsonify({"ocr_available": False})

    return jsonify({
        "ocr_available": True,
        "date": result.get("date"),
        "amount": result.get("amount"),
        "vendor": result.get("vendor"),
        "category": result.get("category"),
        "raw_text": (result.get("raw_text") or "")[:2000],
    })


# ---------- Expenses ----------


@app.route("/api/trips/<int:trip_id>/expenses", methods=["POST"])
@require_auth
def create_expense(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id, g.user["id"])
    if not trip:
        db.close()
        return jsonify({"error": "Trip not found"}), 404

    form = request.form
    date = form.get("date") or ""
    category = form.get("category") or ""
    vendor = (form.get("vendor") or "").strip()
    amount_raw = form.get("amount") or "0"
    notes = (form.get("notes") or "").strip()
    flagged = form.get("flagged") in ("1", "true", "True", "on")

    try:
        amount = float(amount_raw)
    except ValueError:
        db.close()
        return jsonify({"error": "Amount must be a number"}), 400

    if not date or not category or amount <= 0:
        db.close()
        return jsonify({"error": "Date, category, and a positive amount are required"}), 400

    if category not in ALL_CATEGORIES:
        db.close()
        return jsonify({"error": "Unknown category"}), 400
    if category == NEEDS_REVIEW_CATEGORY:
        flagged = True

    receipt_filename = None
    file = request.files.get("receipt")
    if file and file.filename:
        if not allowed_file(file.filename):
            db.close()
            return jsonify({"error": "Unsupported receipt file type"}), 400
        ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
        receipt_filename = f"{uuid.uuid4().hex}.{ext}"
        file.save(UPLOAD_DIR / receipt_filename)

    cur = db.execute(
        "INSERT INTO expenses (trip_id, date, category, vendor, amount, notes, flagged, receipt_filename, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (trip_id, date, category, vendor, amount, notes, int(flagged), receipt_filename, now_iso()),
    )
    db.commit()
    expense_id = cur.lastrowid
    row = db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    db.close()
    return jsonify(expense_public(row)), 201


def get_owned_expense(db, expense_id, user_id):
    return db.execute(
        "SELECT expenses.* FROM expenses JOIN trips ON trips.id = expenses.trip_id "
        "WHERE expenses.id = ? AND trips.user_id = ?",
        (expense_id, user_id),
    ).fetchone()


@app.route("/api/expenses/<int:expense_id>", methods=["PATCH"])
@require_auth
def update_expense(expense_id):
    db = get_db()
    row = get_owned_expense(db, expense_id, g.user["id"])
    if not row:
        db.close()
        return jsonify({"error": "Expense not found"}), 404

    if request.content_type and "multipart/form-data" in request.content_type:
        form = request.form
        fields = {}
        if "date" in form:
            fields["date"] = form.get("date")
        if "category" in form:
            fields["category"] = form.get("category")
        if "vendor" in form:
            fields["vendor"] = form.get("vendor")
        if "amount" in form:
            try:
                fields["amount"] = float(form.get("amount"))
            except ValueError:
                db.close()
                return jsonify({"error": "Amount must be a number"}), 400
        if "notes" in form:
            fields["notes"] = form.get("notes")
        if "flagged" in form:
            fields["flagged"] = int(form.get("flagged") in ("1", "true", "True", "on"))
        if fields.get("category") == NEEDS_REVIEW_CATEGORY:
            fields["flagged"] = 1

        file = request.files.get("receipt")
        if file and file.filename:
            if not allowed_file(file.filename):
                db.close()
                return jsonify({"error": "Unsupported receipt file type"}), 400
            ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
            new_filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(UPLOAD_DIR / new_filename)
            old_path = UPLOAD_DIR / row["receipt_filename"] if row["receipt_filename"] else None
            if old_path and old_path.exists():
                old_path.unlink()
            fields["receipt_filename"] = new_filename
    else:
        data = request.get_json(force=True) or {}
        fields = {k: v for k, v in data.items() if k in ("date", "category", "vendor", "amount", "notes", "flagged")}
        if "flagged" in fields:
            fields["flagged"] = int(bool(fields["flagged"]))
        if fields.get("category") == NEEDS_REVIEW_CATEGORY:
            fields["flagged"] = 1

    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        db.execute(f"UPDATE expenses SET {set_clause} WHERE id = ?", (*fields.values(), expense_id))
        db.commit()

    row = db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    db.close()
    return jsonify(expense_public(row))


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
@require_auth
def delete_expense(expense_id):
    db = get_db()
    row = get_owned_expense(db, expense_id, g.user["id"])
    if not row:
        db.close()
        return jsonify({"error": "Expense not found"}), 404

    db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    db.commit()
    db.close()

    if row["receipt_filename"]:
        path = UPLOAD_DIR / row["receipt_filename"]
        if path.exists():
            path.unlink()

    return jsonify({"ok": True})


@app.route("/uploads/<path:filename>")
@require_auth
def get_upload(filename):
    db = get_db()
    row = db.execute(
        "SELECT expenses.id FROM expenses JOIN trips ON trips.id = expenses.trip_id "
        "WHERE expenses.receipt_filename = ? AND trips.user_id = ?",
        (filename, g.user["id"]),
    ).fetchone()
    db.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(UPLOAD_DIR, filename)


# ---------- Reports ----------


@app.route("/api/trips/<int:trip_id>/report", methods=["GET"])
@require_auth
def trip_report(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id, g.user["id"])
    if not trip:
        db.close()
        return jsonify({"error": "Trip not found"}), 404
    expenses = db.execute(
        "SELECT * FROM expenses WHERE trip_id = ? ORDER BY date ASC, id ASC", (trip_id,)
    ).fetchall()
    db.close()

    pdf_buffer = build_trip_pdf(trip, trip["client_name"], g.user["name"], g.user["email"], expenses)
    safe_client = secure_filename(trip["client_name"] or "trip") or "trip"
    filename = f"expense-report-{safe_client}-{trip['start_date']}.pdf"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


@app.route("/api/trips/<int:trip_id>/report/log", methods=["POST"])
@require_auth
def log_report(trip_id):
    db = get_db()
    trip = get_owned_trip(db, trip_id, g.user["id"])
    if not trip:
        db.close()
        return jsonify({"error": "Trip not found"}), 404

    data = request.get_json(force=True) or {}
    recipient_email = (data.get("recipient_email") or "").strip()
    recipient_name = (data.get("recipient_name") or "").strip()

    db.execute(
        "INSERT INTO report_log (trip_id, recipient_email, recipient_name, sent_at) VALUES (?, ?, ?, ?)",
        (trip_id, recipient_email, recipient_name, now_iso()),
    )
    db.execute("UPDATE trips SET status = 'submitted' WHERE id = ?", (trip_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug)
