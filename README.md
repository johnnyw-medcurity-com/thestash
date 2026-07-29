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

## Deploying to PythonAnywhere (free, making it a real published web app)

This turns the app from "runs on my laptop" into a URL anyone on the team can open from
their phone, at no cost. PythonAnywhere's free tier gives you an always-on Flask app
plus a persistent home directory — no separate database/disk setup needed, unlike most
other free hosts whose filesystems get wiped on every restart.

The code is already pushed to GitHub at `github.com/johnnyw-medcurity-com/thestash`.

**1. Sign up** at [pythonanywhere.com](https://www.pythonanywhere.com) — choose the free
**Beginner** account.

**2. Open a Bash console** from the PythonAnywhere dashboard (**Consoles** tab → **Bash**),
then clone the repo and install dependencies:

```bash
git clone https://github.com/johnnyw-medcurity-com/thestash.git
cd thestash
mkvirtualenv --python=/usr/bin/python3.10 travel-expense-env
pip install -r requirements.txt
```

(If `thestash` is a private repo, this clone will ask for GitHub credentials — either
make the repo public first since it contains no secrets, `.gitignore` already keeps the
database/receipts/secret key out of it, or generate a GitHub personal access token
yourself and use it as the password when prompted.)

**3. Create the web app**: go to the **Web** tab → **Add a new web app** → when asked
about the framework, choose **Manual configuration** (not the Flask wizard, since we
already have our own `app.py`) → pick **Python 3.10**.

**4. Point it at your virtualenv**: on the Web tab, in the "Virtualenv" section, enter:
```
/home/<your-username>/.virtualenvs/travel-expense-env
```

**5. Edit the WSGI file**: still on the Web tab, click the WSGI configuration file link
(something like `/var/www/<your-username>_pythonanywhere_com_wsgi.py`), delete its
contents, and replace with:

```python
import sys

path = '/home/<your-username>/thestash'
if path not in sys.path:
    sys.path.append(path)

from app import app as application
```

(Replace `<your-username>` with your actual PythonAnywhere username, shown in the paths
already on that page.)

**6. Reload**: click the big green **Reload** button at the top of the Web tab.

**7. Open your app**: PythonAnywhere shows your URL at the top of the Web tab, like
`https://<your-username>.pythonanywhere.com`. That's what you open from a phone instead
of `http://<local-ip>:5000`.

**Free tier limitations worth knowing:**
- No custom domain — you're on `<your-username>.pythonanywhere.com`.
- A daily CPU-seconds allowance that resets every day — plenty for occasional expense
  logging by a small team, but worth knowing if usage ever grows heavily.
- Outbound internet from free accounts is limited to a whitelist of sites, but this app
  never calls out to anything else, so it's unaffected.
- Free accounts get suspended after a few months of no login — just log in
  occasionally to keep it active.
- After you push new commits to GitHub, you'll need to `git pull` inside a
  PythonAnywhere Bash console and click **Reload** again — there's no auto-deploy on
  the free tier.

## Alternative: deploying to Render (paid, but simpler ongoing ops)

If the team later wants guaranteed uptime, auto-deploy on every push, and no CPU-second
limits, this repo is also pre-configured for [Render](https://render.com) — see
`render.yaml` and `Procfile`. Render's free tier doesn't support persistent disks
(your database and receipts would be wiped on every restart), so this path requires a
paid **Starter** instance (~$7/mo):

- **New +** → **Blueprint** in the Render dashboard, connect this GitHub repo, and
  Render reads `render.yaml` to set up the web service, a 1GB persistent disk mounted
  at `/var/data`, and environment variables (`DATA_DIR`, `SECRET_KEY`, `FLASK_DEBUG`)
  automatically. Click **Apply**.

**Future upgrade path beyond either of these:** if the team outgrows a single small
disk (e.g. lots of concurrent writers), the next step would be swapping SQLite for a
managed Postgres database and receipt storage for an S3-compatible bucket (e.g.
Cloudflare R2) — not needed for a small team, but worth knowing the ceiling.
