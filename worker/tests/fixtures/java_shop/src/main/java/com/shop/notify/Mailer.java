package com.shop.notify;

public interface Mailer {
    static void send(String message) {
        System.out.println(format(message));
    }

    static String format(String message) {
        return "[mail] " + message;
    }

    void deliver(String to);
}
