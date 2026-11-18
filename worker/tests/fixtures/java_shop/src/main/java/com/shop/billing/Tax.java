package com.shop.billing;

public final class Tax {
    private Tax() {
    }

    public static double rateFor(String region) {
        return lookup(region);
    }

    static double lookup(String region) {
        return region.length();
    }
}
