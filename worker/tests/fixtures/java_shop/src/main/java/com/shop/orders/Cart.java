package com.shop.orders;

public class Cart {
    public double sumItems() {
        double total = 0;
        for (int i = 0; i < 3; i++) {
            total += price(i);
        }
        return total;
    }

    double price(int i) {
        return i * 2.5;
    }
}
