# Larder

**An all-in-one restaurant platform for multi-outlet groups: front of house, kitchen, back office and people.**

Take orders on a tablet, run the kitchen display, seat guests from the waitlist, take payments, and every
sale flows straight into stock, food cost, performance and labour reports. Larder tracks every gram of stock
across outlets and a central kitchen, and compares what recipes say you *should* have used with what you
*actually* used, so you can see where food cost leaks.

Built with **Django + Django REST Framework** (API) and **React + Vite** (web app).

---

## What it does

| Area | Features |
|---|---|
| **POS** | Picture tiles (photo or emoji) by menu section with icons, search by name or code (press `/`) · veg / non-veg mark, chef’s pick, new and spice badges · options per dish: sizes (single/double/triple), sauces and flavours, add-ons that cost extra and use stock · ⓘ on every dish: description, allergens, what it’s made with, what to suggest · the guest’s allergies (from their profile, or ticked by the server) flag every dish that contains them and ask before adding · “suggest with” after each dish for quick upsells · Floor plan with live table status · dine-in, takeout, online and delivery orders · notes, seats, voids (manager approval once sent) · guest count with automatic large-party service charge (removable with a reason) · discounts (manager) · split payments, tips, cash change · HST · printed receipts · loyalty lookup and redemption |
| **Kitchen display** | Chosen options and the guest’s allergies printed on every ticket · Tickets in order with live timers against a target · Start / Ready / Served taps are timed · pass (expo) view · rush tickets |
| **Service times** | Wait to be seated, seated → order, waiting for a cook, cooking, ready → served, table time: averages, 90th percentile, weekday vs weekend, by hour · % of tickets over target · quoted vs actual waits |
| **Host stand** | Walk-in waitlist with quotes and "table ready" messages · reservations · seat straight onto a free table (opens the check) |
| **Guests & loyalty** | Guest profiles with allergies and notes · visits and spend · points earned on every paid order, rewards redeemed at the table · marketing consent recorded |
| **Payments** | Provider plug-ins (see below): cash and stand-alone card terminals work today; card-reader integrations slot in without touching orders · refunds · Larder never stores card numbers |
| **Online ordering** | Public pickup-ordering page per outlet (`/order/SQ1`) with the same picture menu, options and allergen filter · live order status · secure endpoint for delivery-app adapters |
| **Schedule & time clock** | Weekly schedule with draft/publish · PIN time clock on a shared tablet · timesheets with manager edits logged · labour cost %, sales per labour hour · tip pool split by hours |
| **Accounting export** | Daily sales journal (sales by category, discounts, service charge, HST, tips, payments by method, voids, refunds) and purchases as CSV for QuickBooks or Xero |
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
| **Recipes & costing** | Dishes made of ingredients and in-house preps · plate cost rolls up through sub-recipes · food cost % and the price needed to hit target · allergens roll up from ingredients, plus any the dish must declare · each dish’s menu card: photo upload, icon, description, badges, options, suggestions · option groups with prices and stock use |
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
| Take orders and payments, run the kitchen display, seat guests, clock in, do checklists with photos, read SOPs, write logbook notes, report issues, log complaints, scan invoices, count stock, log wastage, receive deliveries and transfers, cook batches | ✅ | ✅ | ✅ |
| Discounts, void sent items and orders, refunds, schedules and timesheets, edit tables, review checklists, edit checklists and SOPs, approve scanned invoices, manage staffing and issues, see performance, costs and reports, set par levels, plan production, create and send orders, import sales | | ✅ | ✅ |
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
python manage.py makemigrations accounts catalog stock purchasing sales audit checklists ops guests pos
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
python manage.py makemigrations accounts catalog stock purchasing sales audit checklists ops guests pos
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

`seed_demo` builds a fictional smash-burger chain, *Smash Lane* (three outlets around the GTA plus a central kitchen), and
simulates 30 days of trading: daily POS sales, deliveries, kitchen production, transfers, weekly
counts and wastage, plus 15 months of past sales (for year-on-year growth), a week of opening and
closing checklists with placeholder photos, staff, complaints, equipment and handover notes. It plants a
few problems for the alerts to catch: a missed closing, a warm walk-in (which opens an issue), short
staffing at the central kitchen and a high service-charge removal rate at Brampton. It takes a few minutes. Run `python manage.py seed_demo --reset` to start over.

The demo menu (about 80 dishes across smash, exhibition, chicken, fried-chicken and veggie burgers, mac & cheese,
sides, salads, kids, shakes, drinks, coffee & matcha and desserts) follows a real Bengaluru smash-burger menu
used as a reference: the same dishes, descriptions, sizes, add-ons and declared allergens (egg, nuts, milk in
the bun, mushroom in the smash sauce and garlic mayo). Rupee prices are converted to Canadian dollars
(₹30 ≈ $1). Ingredient quantities and supplier prices are estimates. Change any of it in
`backend/catalog/demo_menu.py`, or on the **Recipes** page once it's loaded.

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
| `sofia` | `LarderServer1` | Server | Square One |
| `ravi` | `LarderCook1` | Cook | Downtown Brampton |
| `ana` | `LarderCook1` | Cook | Central Kitchen |

These passwords are for the demo only. Time-clock PINs: 1001, 1002, 1003 at Square One (2001…, 3001…, 4001… elsewhere).

Square One runs on Larder's POS for the last three demo days and has a live service in progress when the seed
finishes: tables at every stage, a late ticket on the kitchen display, an online order, people on the waitlist and
bookings tonight. The online ordering page is at http://localhost:5173/order/SQ1.

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

| `LARDER_PAYMENT_PROVIDERS` | `manual` | Comma-separated payment providers to enable |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | empty | For the Stripe Terminal provider once it's finished |
| `LARDER_INTEGRATION_SECRET` | empty | Shared secret delivery-app adapters send in `X-Larder-Secret` |
| `LARDER_MESSAGE_PROVIDER` | `log` | Guest texts (waitlist). `log` records them only |

## Payments

Larder takes payments through **providers**: small plug-ins in `backend/pos/payments.py`.

- **`manual`** (on by default): cash, plus cards run on a stand-alone terminal (Moneris, Square, Clover…). Staff run the card,
  then confirm in Larder with the approval code. Refunds happen on the terminal and are recorded in Larder.
- **`stripe_terminal`**: a documented skeleton for card readers connected to Larder. Not active until finished.

Larder never sees card numbers. A provider stores only its own reference and non-sensitive details (card brand, last 4).
That keeps card data with the processor, which is what PCI DSS expects from a POS like this.

**Adding a provider** (Stripe Terminal, Square Terminal, Moneris Go…):

1. Subclass `PaymentProvider` in `pos/payments.py`; implement `start()` (approve now or return a pending action),
   `refund()`, and `handle_webhook()` if the processor sends events.
2. Register it in `PROVIDERS` and add its key to `LARDER_PAYMENT_PROVIDERS`.
3. Point the processor's webhook at `/api/pos/payments/webhook/<provider>/`.

The POS screen, payment records, refunds, tips, reports and the accounting export already work with any provider.

## Delivery apps

Adapters (or a middleware such as Otter or Deliverect) post orders to `/api/pos/integrations/<platform>/orders/`
with header `X-Larder-Secret`. Orders go straight to the kitchen display, are marked paid on the app, and count in
sales, stock and reports. See the docstring in `pos/views.py` for the body format.

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
2026-11-08,BRM,SB01,31,416.95
2026-11-08,BRM,SD01,52,517.40
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
| `locations/` · `vendors/` · `items/` · `menu-items/` | GET (+ writes by role) | `items/{id}/recipe/` and `menu-items/{id}/recipe/` PUT replace a recipe · `menu-items/{id}/photo/` POST multipart `photo` |
| `menu-categories/` · `modifier-groups/` | GET POST PATCH (PUT) | POS sections (icon, kind) · option groups with their options |
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
| `pos/floor/` `pos/menu/` `pos/orders/` + `{id}/lines/` `{id}/send/` `{id}/payments/` `{id}/close/` `{id}/void/` … | GET POST PATCH | The POS |
| `pos/kds/` · `pos/tickets/{id}/{start,ready,served,recall}/` | GET POST | Kitchen display |
| `pos/payments/webhook/{provider}/` · `pos/integrations/{platform}/orders/` | POST | No login; verified by signature / secret |
| `public/menu/{code}/` · `public/orders/{code}/` · `public/order-status/{token}/` | GET POST | Online ordering, no login, rate-limited |
| `guests/` · `guests/reservations/` · `guests/waitlist/` | GET POST PATCH | |
| `ops/shifts/` · `ops/clock/` · `ops/timesheets/` · `ops/time-entries/` | GET POST PATCH | |
| `reports/service-times/` · `reports/accounting-export/?kind=sales\|purchases` | GET | |
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
  reports/       variance, dashboard, performance, menu engineering, forecast, service times, accounting export
  audit/         change log
  checklists/    SOPs, opening/closing checklists, photo answers, reviews, compliance, readings
  ops/           staffing, schedule, time clock, labour, complaints, equipment issues, logbook, notifications, send_alerts
  pos/           tables, orders, kitchen tickets, payments + provider plug-ins, online ordering, delivery intake
  guests/        guest profiles, loyalty points, reservations, waitlist, guest messaging plug-ins
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

- Finish a card-reader provider (Stripe Terminal or Moneris) and online card payment for pickup orders
- Offline mode for the POS (queue orders locally when the internet drops, sync later)
- Kitchen and receipt printers (ESC/POS) and cash drawer
- Real SMS provider for waitlist texts
- Direct POS-data imports from Toast, Square and Lightspeed for groups not using Larder's POS
- Unit conversions per item (buy in cases, count in kg) and batch/lot expiry tracking
