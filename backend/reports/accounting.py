"""CSV exports for the bookkeeper (QuickBooks, Xero or a spreadsheet).

sales     one row per location per day: net sales by category, discounts, service charge, tax, tips,
          payments by method. Built from Larder POS orders (CSV-imported days show net sales only).
purchases one row per received delivery: vendor, invoice, date, location, total.
"""
import csv
import io
from collections import defaultdict
from decimal import Decimal

from purchasing.models import PurchaseOrder
from pos.models import Order, OrderLine, Payment
from sales.models import SalesLine

Z = Decimal(0)


def sales_csv(location_ids, start, end) -> str:
    rows = defaultdict(lambda: defaultdict(lambda: Z))
    categories, methods = set(), set()
    for line in SalesLine.objects.filter(day__location_id__in=location_ids, day__business_date__gte=start,
                                         day__business_date__lte=end).select_related("day__location", "menu_item"):
        key = (line.day.business_date, line.day.location.code)
        cat = line.menu_item.category
        categories.add(cat)
        rows[key][f"sales:{cat}"] += line.net_sales
        rows[key]["net_sales"] += line.net_sales
    orders = Order.objects.filter(location_id__in=location_ids, business_date__gte=start, business_date__lte=end,
                                  status=Order.Status.CLOSED).select_related("location")
    for o in orders:
        key = (o.business_date, o.location.code)
        rows[key]["discounts"] += o.discount
        rows[key]["service_charge"] += o.service_charge
        rows[key]["tax"] += o.tax
        rows[key]["orders"] += 1
        voided = OrderLine.objects.filter(order=o, status=OrderLine.Status.VOID)
        rows[key]["voids"] += sum((v.qty * v.unit_price for v in voided), Z)
    for p in Payment.objects.filter(order__in=orders, status=Payment.Status.APPROVED).select_related("order__location"):
        key = (p.order.business_date, p.order.location.code)
        m = p.get_method_display()
        methods.add(m)
        rows[key][f"paid:{m}"] += p.amount - p.refunded_amount
        rows[key]["tips"] += p.tip
        rows[key]["refunds"] += p.refunded_amount

    cats, meths = sorted(categories), sorted(methods)
    header = (["date", "location", "orders", "net_sales"] + [f"sales_{c.lower().replace(' ', '_')}" for c in cats]
              + ["discounts", "service_charge", "tax_collected", "tips", "voids", "refunds"]
              + [f"paid_{m.lower().replace(' ', '_')}" for m in meths])
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    for (d, code), r in sorted(rows.items()):
        w.writerow([d.isoformat(), code, int(r["orders"]), f"{r['net_sales']:.2f}"]
                   + [f"{r[f'sales:{c}']:.2f}" for c in cats]
                   + [f"{r[k]:.2f}" for k in ("discounts", "service_charge", "tax", "tips", "voids", "refunds")]
                   + [f"{r[f'paid:{m}']:.2f}" for m in meths])
    return out.getvalue()


def purchases_csv(location_ids, start, end) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["received_on", "location", "vendor", "invoice_number", "po_number", "lines", "total"])
    for po in PurchaseOrder.objects.filter(location_id__in=location_ids, status=PurchaseOrder.Status.RECEIVED,
                                           received_on__gte=start, received_on__lte=end) \
            .select_related("vendor", "location").prefetch_related("lines").order_by("received_on", "id"):
        w.writerow([po.received_on.isoformat(), po.location.code, po.vendor.name, po.invoice_number, po.number,
                    po.lines.count(), f"{po.total():.2f}"])
    return out.getvalue()
