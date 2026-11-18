package com.shop.billing;

import static com.shop.billing.Tax.rateFor;

import com.shop.orders.Cart;
import com.shop.notify.*;

public class Invoice {
    private final Cart cart = new Cart();

    public Invoice() {
        this(1);
    }

    public Invoice(int copies) {
        init();
    }

    public double total() {
        double sum = cart.sumItems();
        return sum * rateFor("kr");
    }

    public double total(int discount) {
        return total() - discount;
    }

    private void init() {
        Mailer.send("created");
    }

    static class Line {
        double amount() {
            return Tax.rateFor("us");
        }
    }
}
