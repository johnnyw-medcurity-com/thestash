# Travel Expenses

A mobile-friendly web app for logging business travel expenses tied to a client, and
sending an expense report (PDF) to whoever needs to review or reimburse it.

## What it does

- Each person creates their own account and logs their own trips.
- Every trip is tied to a client and has a start/end date and purpose.
- Expenses are logged against a trip: date, category, vendor, amount, notes, and an
  optional receipt photo (the file picker opens the camera directly on a phone).
- Categories mirror the covered/not-covered expense policy (flights, lodging, rental
  car/mileage, meals, parking/tolls/transportation, other direct trip costs). Anything
  that doesn't clearly fit can be logged as "Other (Needs Review)" or flagged manually
  so nothing gets silently guessed at.
- Each trip can generate a PDF expense report (itemized table, subtotals by category,
  grand total, and a flagged-for-review section) and download it on demand.
- "Send Report" downloads the PDF and opens a pre-filled email draft in your own mail
  app — just attach the file that was downloaded and hit send. No email credentials
  are stored by the app.

## Setup

Requires Python 3.9+ (already available on macOS).

```bash
cd "/Users/johnnyw/Claude Code/travel expense"
python3 -m pip install --user -r requirements.txt
```

## Run

```bash
cd "/Users/johnnyw/Claude Code/travel expense"
python3 app.py
```

The app runs at http://localhost:5000

### Using it from your phone

1. Make sure your phone is on the same Wi-Fi network as this computer.
2. Find this computer's local IP address:
   ```bash
   ipconfig getifaddr en0
   ```
3. On your phone's browser, go to `http://<that-ip>:5000` (e.g. `http://192.168.1.23:5000`).
4. Optional: use "Add to Home Screen" in the phone's browser menu so it opens like an app.

## Data storage

- All data lives in `expense.db` (SQLite) in this folder.
- Uploaded receipt photos are stored in `uploads/`.
- Back up the whole folder to back up all trips, expenses, and receipts.

## Notes / limitations (v1)

- Clients are a shared list across everyone using the app (so employees pick the same
  client instead of creating duplicates); trips and expenses are private to the person
  who created them.
- There's no admin view that lists everyone's trips yet — each person downloads/sends
  their own reports. That would be a reasonable next addition if a manager needs a
  combined view.

## Deploying to Render (making it a real published web app)

This turns the app from "runs on my laptop" into a URL anyone on the team can open from
their phone. The app is already configured for this: `gunicorn` as the production
server (`Procfile`), and a `DATA_DIR` environment variable that points the database and
uploaded receipts at a persistent disk instead of the app's own folder.

**1. Push this folder to a GitHub repo** (Render deploys from git):

```bash
cd "/Users/johnnyw/Claude Code/travel expense"
git init
git add -A
git commit -m "Travel expense app"
```

Then create an empty repository on [github.com/new](https://github.com/new) (don't
initialize it with a README), and:

```bash
git remote add origin <your-new-repo-url>
git branch -M main
git push -u origin main
```

**2. Create a Render account** at [render.com](https://render.com) (free to sign up).

**3. Deploy using the included blueprint:**
- In the Render dashboard, click **New +** → **Blueprint**.
- Connect your GitHub account and select this repo. Render will read `render.yaml`
  and set up the web service, environment variables, and persistent disk automatically.
- Click **Apply** to deploy.

**Or deploy manually** (New + → Web Service) if you'd rather not use the blueprint:
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --workers 2 --threads 4 --timeout 60`
- Add a persistent disk (Settings → Disks): mount path `/var/data`, size 1 GB.
- Environment variables: `DATA_DIR=/var/data`, `SECRET_KEY=<click "Generate">`,
  `FLASK_DEBUG=false`.

**Important — plan choice:** Render's free web service tier has an *ephemeral*
filesystem and doesn't support persistent disks, so the SQLite database and every
uploaded receipt would be wiped on each restart/redeploy. That defeats the purpose of
an expense tracker. Use a paid **Starter** instance (currently ~$7/mo) so the disk
persists. `render.yaml` is already set to `plan: starter` for this reason.

Once deployed, Render gives you a URL like `https://travel-expenses.onrender.com` —
that's what you'd open from a phone instead of `http://<local-ip>:5000`.

**Future upgrade path:** if the team outgrows a single small disk (e.g. lots of
concurrent writers), the next step would be swapping SQLite for Render's managed
Postgres and receipt storage for an S3-compatible bucket (e.g. Cloudflare R2) — not
needed for a small team, but worth knowing the ceiling.
