import os
import sqlite3

# TODO: demo PR with intentional issues for Code Review Copilot testing

API_KEY = "sk-hardcoded-secret-key-12345"  # should use env var


def get_user(user_id):
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    # vulnerable to injection if user_id comes from request
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
    row = cursor.fetchone()
    return row[0]  # no null check — crashes if user missing


def fetch_all_users():
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    users = []
    for row in cursor.cursor().execute("SELECT id, name FROM users"):
        users.append(row)
    return users


def divide(a, b):
    return a / b  # no zero check


def save_password(email, password):
    conn = sqlite3.connect("app.db")
    conn.execute(
        "INSERT INTO users (email, password) VALUES (?, ?)",
        (email, password),  # storing plaintext password
    )
    conn.commit()
