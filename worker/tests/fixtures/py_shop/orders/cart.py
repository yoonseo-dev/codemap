def sum_items(items):
    total = 0
    for item in items:
        total += price(item)
    return total


def price(item):
    return item.amount
