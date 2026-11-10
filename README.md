# Larder

**Restaurant back-office and food-cost control for multi-outlet kitchens.**

Larder tracks every gram of stock across outlets and a central kitchen. It compares what your
recipes say you *should* have used (from POS sales) with what you *actually* used (from deliveries,
transfers, waste and stock counts), so you can see where food cost leaks.

Built with **Django + Django REST Framework** (API) and **React + Vite** (web app).

---

## What it does

| Area | Features |
|---|---|
| **Outlet performance** | Each outlet vs its brand average, green better / red worse: **APC** (spend per cover), average bill, **SSSG** 4-week and quarter vs last year (same weekdays, same stores), **beverage and dessert attach** per cover, **service charge removed %**, **average prep time** Mon–Thu vs Fri–Sun, **loyalty enrollment %**, **delivery food-ready accuracy** per app, **wrong / missing items**, complaints per 1,000 covers · weekly sales vs last year · **staffing** ideal vs current vs gap · laid out like a printed weekly ops review |
| **Menu engineering** | Popularity × margin per category (Stars, Plowhorses, Puzzles, Dogs) with what to do about each |
| **Forecast & smart reorder** | Next 7 days of portions per dish from same-weekday history × trend · orders exactly what the forecast will run short of before each vendor's next delivery |
| **Invoice scanning** | Photo or PDF of a supplier invoice → lines read, matched to your items, lb converted to kg, price changes flagged → a manager approves and it's booked as a received delivery |
| **Issues & equipment** | Report broken equipment from the floor · a failed critical checklist reading opens an issue automatically · assign, fix, record cost |
| **Temperature log** | Every fridge, freezer and hot-holding reading from checklists, charted with its safe range and printable for inspectors |
| **Shift logbook** | Handover notes between opening and closing teams; important ones notify managers |
| **Guest complaints** | Log complaints by reason and channel, with comps; feeds the performance sheet |
| **Team & staffing** | Required headcount per department, employee list, leavers |
| **Notifications** | In-app alerts plus email: missed checklists, out-of-range readings, flagged checklists, short transfers, critical issues, important handover notes |
| **Opening & closing checklists** | Managers build checklists per location type · tasks can require a photo (taken on the phone camera) or a reading with limits, e.g. walk-in 0–4 °C, cash over/short ±$5 · each task links to its SOP · staff can't submit until everything is done · managers review photos and readings, then approve, flag or reopen · dashboard shows missed checklists, out-of-range readings and on-time rate |
| **SOP library** | Step-by-step procedures (food safety, cleaning, cash, security) searchable by everyone, edited by managers |
| **Stock** | Live stock per location from an append-only ledger · par levels · low-stock and expiry flags · stock counts that record the difference · per-item movement history |
| **Recipes & costing** | Dishes made of ingredients and in-house preps · plate cost rolls up through sub-recipes · food cost % and the price needed to hit target · allergens roll up too |
| **Purchasing** | Purchase orders (draft → sent → received) · reorder suggestions from par levels net of open orders · receiving updates stock and the ingredient's latest price |
| **Central kitchen** | Prep demand from outlets · production batches that consume ingredients and produce preps · stock check before cooking |
| **Transfers** | Outlet requests → kitchen dispatches → outlet receives · short deliveries flagged |
| **Wastage** | Log waste with a reason; counted as *explained* loss |
| **Sales** | Import daily item sales from a POS CSV · each import books recipe usage against stock · re-importing a day replaces it |
| **Reports** | COGS and variance per location: theoretical vs actual, wastage vs unexplained loss · dashboard with alerts (low stock, price rises, food cost over target, late orders, short transfers) |
| **People & audit** | Real logins (JWT) · roles: Cook, Manager, Owner · staff limited to their locations · every change written to a change log that can't be edited |

### Who can do what

| | Cook | Manager | Owner |
|---|:-:|:-:|:-:|
| Do checklists with photos, read SOPs, write logbook notes, report issues, log complaints, scan invoices, count stock, log wastage, receive deliveries and transfers, cook batches | ✅ | ✅ | ✅ |
| Review checklists, edit checklists and SOPs, approve scanned invoices, manage staffing and issues, see performance, costs and reports, set par levels, plan production, create and send orders, import sales | | ✅ | ✅ |
| Change recipes and menu prices, manage users | | | ✅ |

The API enforces these rules. The web app only hides what the API would refuse.

---

## How the numbers work

Stock is never typed over. Every change is a **movement** in a ledger (`stock.Movement`):

```
opening · delivery received · transfer in/out · sold (recipe usage) · wastage · count adjustment · produced · used in production
```

Stock on hand = the sum of movements. Each movement freezes the unit cost at that moment, so past reports don't shift when prices change.

For a location and date range:

- **Theoretical usage** = POS portions × recipe quantities (the `sale` movements)
- **Wastage** = what staff logged
- **Unexplained loss** = what stock counts found missing (`count` movements)
- **Actual usage (COGS)** = theoretical + wastage + unexplained
  = opening stock + deliveries + transfers in − transfers out ± production − closing stock
- **Food cost %** = actual usage ÷ net sales

---

## Run it locally

You need **Python 3.10+** and **Node.js 20+**.

### 1. Backend (Django API on port 8000)

**Windows (PowerShell)**

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py makemigrations accounts catalog stock purchasing sales audit checklists ops
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

**macOS / Linux**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py makemigrations accounts catalog stock purchasing sales audit checklists ops
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

`seed_demo` builds a fictional chain (three outlets around the GTA plus a central kitchen) and
simulates 30 days of trading: daily POS sales, deliveries, kitchen production, transfers, weekly
counts and wastage, plus 15 months of past sales (for year-on-year growth), a week of opening and
closing checklists with placeholder photos, staff, complaints, equipment and handover notes. It plants a
few problems for the alerts to catch: a missed closing, a warm walk-in (which opens an issue), short
staffing at the central kitchen and a high service-charge removal rate at Brampton. It takes a minute or two. Run `python manage.py seed_demo --reset` to start over.

### 2. Frontend (React app on port 5173)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The dev server forwards `/api` calls to Django.

### Demo accounts

| Username | Password | Role | Locations |
|---|---|---|---|
| `owner` | `LarderOwner1` | Owner | All |
| `meera` | `LarderManager1` | Manager | All |
| `ravi` | `LarderCook1` | Cook | Downtown Brampton |
| `ana` | `LarderCook1` | Cook | Central Kitchen |

These passwords are for the demo only.

For the Django admin (http://127.0.0.1:8000/admin/), create a superuser with `python manage.py createsuperuser`.

### Tests

```bash
cd backend
python manage.py test
```

Covers recipe cost roll-up, deliveries and price updates, production, transfers with short receipts,
the variance maths, sales re-imports and role/location permissions.

---

## Using PostgreSQL instead of SQLite

SQLite is fine for development. For anything shared, use PostgreSQL:

```bash
docker compose up -d          # starts Postgres 16 on localhost:5432
```

Then set these before running Django (PowerShell: `$env:POSTGRES_DB="larder"` and so on):

```bash
export POSTGRES_DB=larder POSTGRES_USER=larder POSTGRES_PASSWORD=larder POSTGRES_HOST=localhost
python manage.py migrate
python manage.py seed_demo
```

### Other settings

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev value | **Set a real one in production** |
| `DJANGO_DEBUG` | `1` | Set to `0` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated |
| `LARDER_FOOD_COST_TARGET` | `0.25` | Target food cost used for alerts |
| `ANTHROPIC_API_KEY` | empty | Turns on automatic invoice reading with Claude. Without it, invoice lines are typed in by hand |
| `LARDER_OCR_MODEL` | `claude-sonnet-5-5` | Model used to read invoices |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | console | Email for notifications. By default emails are printed in the Django terminal |
| `LARDER_APP_URL` | `http://localhost:5173` | Used for links in emails |

### Scheduled alerts

Missed checklists, out-of-stock items and critical issues left open for 24 hours are checked by a command.
Run it every hour (each alert goes to each person only once):

```bash
python manage.py send_alerts
```

On Windows use Task Scheduler; on macOS/Linux use cron (`0 * * * * cd /path/backend && .venv/bin/python manage.py send_alerts`).

---

## Importing sales from a POS

Export daily item sales as CSV:

```csv
date,location,pos_code,qty,net_sales
2026-11-08,BRM,BC01,31,711.45
2026-11-08,BRM,BN01,52,205.40
```

- `location` is the location code (SQ1, BRM, OAK in the demo)
- `pos_code` is the dish's POS code (set on each menu item)
- Importing a day that already exists replaces it, including its stock usage

Covers, bills and service charges come from the POS daily summary, a second CSV:

```csv
date,location,covers,bills,service_charge_bills,service_charge_removed,tickets,avg_prep_minutes,loyalty_bills
2026-11-08,BRM,112,48,6,1,55,11.4,17
```

Everything after `bills` is optional. `tickets` and `avg_prep_minutes` come from the kitchen display (KDS).
Delivery-app scores (food-ready accuracy, rating) are entered weekly on the Outlet performance page.

Upload either on the **Sales import** page, or `POST /api/sales/import/` with the file in a `file` field.
Tick **Past sales** (or send `history=1`) to load last year's figures for growth reports without touching stock.
A direct POS integration (Toast, Square, Lightspeed APIs) would call the same `sales.services.import_day` function.

---

## API overview

All endpoints are under `/api/` and need `Authorization: Bearer <access token>` except login.

| Endpoint | Methods | Notes |
|---|---|---|
| `auth/token/` · `auth/token/refresh/` | POST | Log in / refresh |
| `auth/me/` | GET | Current user, their locations and kitchens |
| `auth/users/` | GET POST PATCH | Owner only |
| `locations/` · `vendors/` · `items/` · `menu-items/` | GET (+ writes by role) | `items/{id}/recipe/` and `menu-items/{id}/recipe/` PUT replace a recipe |
| `stock/levels/?location=` | GET | On hand, par, status, value, shelf life |
| `stock/pars/` | POST | Set par levels |
| `stock/movements/?location=&item=` | GET | The ledger |
| `stock/counts/` · `stock/wastage/` | GET POST | |
| `stock/transfers/` + `{id}/dispatch/` `{id}/receive/` `{id}/cancel/` | GET POST | |
| `stock/batches/` + `{id}/` `{id}/complete/` | GET POST PATCH DELETE | Central kitchen production |
| `purchasing/orders/` + `{id}/send/` `{id}/receive/` `{id}/cancel/` | GET POST | |
| `purchasing/suggestions/?location=` | GET POST | Reorder suggestions → draft orders |
| `sales/days/` · `sales/items/` · `sales/import/` | GET / POST | |
| `reports/dashboard/` · `reports/variance/?location=&start=&end=` | GET | |
| `audit/` | GET | Change log, paginated |
| `checklists/today/?location=&date=` | GET | Checklists due and their progress |
| `checklists/runs/` + `{id}/` `{id}/answers/{answer}/` `{id}/submit/` `{id}/review/` | GET POST PATCH | Answers take multipart `photo` uploads |
| `checklists/templates/` · `checklists/sops/` · `checklists/compliance/` · `checklists/readings/` | GET POST PUT PATCH | |
| `reports/performance/` · `reports/menu-engineering/` · `reports/forecast/` | GET | |
| `purchasing/invoices/` + `{id}/` `{id}/approve/` `{id}/discard/` | GET POST PATCH | Upload is multipart `file` |
| `ops/staffing/` `ops/staffing/plan/` `ops/employees/` `ops/complaints/` `ops/equipment/` `ops/issues/` `ops/handover/` `ops/notifications/` | GET POST PATCH | |

---

## Project layout

```
backend/
  config/        settings, root URLs
  accounts/      User with role + locations, permissions, login
  catalog/       locations, vendors, items, prep recipes, menu, price history, seed_demo command
  stock/         the ledger: movements, pars, counts, wastage, transfers, production (+ services.py)
  purchasing/    purchase orders, receiving, reorder suggestions, invoice scanning
  sales/         POS sales import (item sales and daily covers/bills)
  reports/       variance, dashboard, performance, menu engineering, forecast (read-only)
  audit/         change log
  checklists/    SOPs, opening/closing checklists, photo answers, reviews, compliance, readings
  ops/           staffing, complaints, equipment issues, handover logbook, notifications, send_alerts command
frontend/
  src/pages/     one file per screen
  src/ui.jsx     shared components, formatting, charts
  src/api.js     API client with token refresh
```

Business rules live in each app's `services.py`. Views handle HTTP, permissions and audit logging;
the seed command and tests call the same services.

---

## Checklist photos

Photos are resized in the browser (max 1600 px JPEG) before upload and saved under `backend/media/`.
In development Django serves them at `/media/`. **In production, store them privately** (for example
S3 with signed URLs), because anyone with a photo's link could otherwise open it.

## Roadmap

- Direct POS integrations (Toast, Square, Lightspeed APIs) instead of CSV
- Unit conversions per item (buy in cases, count in kg)
- Batch/lot tracking for expiry instead of "last delivery" estimates
- Labour cost and sales per labour hour (needs a scheduling/timeclock feed)
- SMS alerts and a mobile app wrapper
