import notify.mailer as mailer
from billing import tax
from orders.cart import sum_items

from .tax import rate_for


class InvoiceService:
    def create(self, items):
        total = self.calc_total(items)
        mailer.send(total)
        return total

    def calc_total(self, items):
        return sum_items(items) * rate_for("kr")


def helper():
    print("x")
    return tax.rate_for("us")
