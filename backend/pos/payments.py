"""Payment providers: a small plug-in interface so card processing can be added without touching orders.

How a payment flows
-------------------
1. The POS calls `start(payment)`. The provider either approves right away (cash, or a card taken on the
   restaurant's own stand-alone terminal), or returns PENDING and a `client_action` for the front end
   (e.g. "present card on reader X").
2. A pending payment is finished by the provider's webhook (`handle_webhook`) or by polling `refresh`.
3. Refunds go through `refund(payment, amount)`.

Larder never sees or stores card numbers. Providers keep only their own reference (`provider_ref`) and
non-sensitive details (card brand, last 4 digits) in `provider_data`. That keeps Larder out of PCI scope
for card data: the terminal and the processor handle it.

Adding a provider (e.g. Stripe Terminal, Square Terminal, Moneris)
------------------------------------------------------------------
1. Subclass `PaymentProvider`, set `key`, implement `start`, `refund`, and `handle_webhook` if it pushes events.
2. Register it in PROVIDERS below.
3. Add its key to LARDER_PAYMENT_PROVIDERS in settings / the environment, plus its API keys.
The POS screen lists enabled providers automatically.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from .models import Payment


class PaymentError(Exception):
    pass


@dataclass
class StartResult:
    status: str                      # Payment.Status value
    client_action: dict = field(default_factory=dict)  # what the front end should show next, if pending
    message: str = ""


class PaymentProvider:
    key = ""
    label = ""
    methods: tuple = ()             # Payment.Method values this provider handles

    def start(self, payment: Payment) -> StartResult:
        raise NotImplementedError

    def refund(self, payment: Payment, amount: Decimal) -> None:
        raise NotImplementedError

    def cancel(self, payment: Payment) -> None:
        """Abandon a pending payment (e.g. guest changed their mind at the reader)."""

    def handle_webhook(self, request) -> Payment | None:
        raise PaymentError(f"{self.label} doesn't use webhooks.")

    def describe(self):
        return {"key": self.key, "label": self.label, "methods": list(self.methods)}


class ManualProvider(PaymentProvider):
    """Cash, plus cards run on a stand-alone terminal that isn't connected to Larder.

    Staff take the card on their own terminal and confirm here; the approval is recorded with whatever
    reference they type (e.g. the terminal's auth code). Refunds are also done on the terminal.
    """

    key = "manual"
    label = "Cash / own card terminal"
    methods = (Payment.Method.CASH, Payment.Method.CARD, Payment.Method.GIFT, Payment.Method.OTHER, Payment.Method.APP)

    def start(self, payment):
        if payment.method == Payment.Method.CASH and payment.cash_tendered is not None \
                and payment.cash_tendered < payment.amount + payment.tip:
            raise PaymentError("Cash tendered is less than the amount plus tip.")
        return StartResult(Payment.Status.APPROVED)

    def refund(self, payment, amount):
        # Money goes back in cash or on the stand-alone terminal; Larder records it.
        return None


class StripeTerminalProvider(PaymentProvider):
    """Skeleton for Stripe Terminal (card readers connected to Larder). Not active until finished.

    To finish it: `pip install stripe`, set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET, register a reader
    per location, then:
      start():  create a PaymentIntent (amount in cents, currency "cad", capture_method="automatic"),
                call terminal.Reader.process_payment_intent on the location's reader, store intent.id
                in provider_ref, return StartResult("pending", {"type": "present_card", "reader": ...}).
      handle_webhook(): verify the signature with STRIPE_WEBHOOK_SECRET; on payment_intent.succeeded find
                the Payment by provider_ref, set APPROVED, store card brand/last4 in provider_data.
      refund(): stripe.Refund.create(payment_intent=provider_ref, amount=cents).
    """

    key = "stripe_terminal"
    label = "Card reader (Stripe Terminal)"
    methods = (Payment.Method.CARD,)

    def _check(self):
        if not settings.STRIPE_SECRET_KEY:
            raise PaymentError("Stripe Terminal isn't set up yet (no STRIPE_SECRET_KEY).")

    def start(self, payment):
        self._check()
        raise PaymentError("Stripe Terminal support isn't finished yet. Use 'Cash / own card terminal'.")

    def refund(self, payment, amount):
        self._check()
        raise PaymentError("Stripe Terminal refunds aren't finished yet. Refund on the terminal.")

    def handle_webhook(self, request):
        self._check()
        raise PaymentError("Stripe webhooks aren't finished yet.")


PROVIDERS = {cls.key: cls for cls in (ManualProvider, StripeTerminalProvider)}


def enabled() -> list[PaymentProvider]:
    return [PROVIDERS[k.strip()]() for k in settings.LARDER_PAYMENT_PROVIDERS if k.strip() in PROVIDERS]


def get(key: str) -> PaymentProvider:
    for p in enabled():
        if p.key == key:
            return p
    raise PaymentError(f"Payment provider '{key}' isn't enabled.")


def approve(payment: Payment, provider_data: dict | None = None):
    """Mark a payment approved. Providers' webhooks call this too."""
    payment.status = Payment.Status.APPROVED
    payment.approved_at = timezone.now()
    if provider_data:
        payment.provider_data = {**payment.provider_data, **provider_data}
    payment.save(update_fields=["status", "approved_at", "provider_data"])
