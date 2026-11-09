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
| Count stock, log wastage, receive deliveries and transfers, cook batches | ✅ | ✅ | ✅ |
| See costs and reports, set par levels, plan production, create and send orders, import sales | | ✅ | ✅ |
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
python manage.py makemigrations accounts catalog stock purchasing sales audit
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
python manage.py makemigrations accounts catalog stock purchasing sales audit
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

`seed_demo` builds a fictional chain (three outlets around the GTA plus a central kitchen) and
simulates 30 days of trading: daily POS sales, deliveries, kitchen production, transfers, weekly
counts and wastage. It takes about a minute. Run `python manage.py seed_demo --reset` to start over.

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

Upload it on the **Sales import** page, or `POST /api/sales/import/` with the file in a `file` field.
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

---

## Project layout

```
backend/
  config/        settings, root URLs
  accounts/      User with role + locations, permissions, login
  catalog/       locations, vendors, items, prep recipes, menu, price history, seed_demo command
  stock/         the ledger: movements, pars, counts, wastage, transfers, production (+ services.py)
  purchasing/    purchase orders, receiving, reorder suggestions
  sales/         POS sales import
  reports/       variance and dashboard (read-only)
  audit/         change log
frontend/
  src/pages/     one file per screen
  src/ui.jsx     shared components, formatting, charts
  src/api.js     API client with token refresh
```

Business rules live in each app's `services.py`. Views handle HTTP, permissions and audit logging;
the seed command and tests call the same services.

---

## Roadmap

- Menu engineering (popularity × margin per dish)
- Invoice scanning (OCR) into draft deliveries
- Sales forecast and automatic reorder
- Direct POS integrations instead of CSV
- Unit conversions (buy in cases, count in kg)
- Batch/lot tracking for expiry instead of "last delivery" estimates
