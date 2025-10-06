#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from werkzeug.security import generate_password_hash
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "hospital_data.sqlite3")

def ensure_tables(conn):
    cur = conn.cursor()
    
    # hospital_dataテーブル作成
    cur.execute("""
    CREATE TABLE IF NOT EXISTS hospital_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        updated_by TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(code, key)
    )
    """)
    
    # usersテーブル作成
    cur.execute("PRAGMA table_info(users)")
    cols = [r[1] for r in cur.fetchall()]

    if cols and "password_hash" not in cols:
        print("旧usersテーブルを削除して再作成します...")
        cur.execute("DROP TABLE IF EXISTS users")
        conn.commit()
        cols = []

    if not cols:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        print("✅ usersテーブルを作成しました")

def main():
    print("=" * 50)
    print("病院情報管理システム - 初期設定")
    print("=" * 50)
    
    conn = sqlite3.connect(DB_PATH)
    ensure_tables(conn)
    cur = conn.cursor()

    users = [
        ("yamada", "demo-pass", "admin"),
        ("sato", "sato1234", "user"),
        ("tanaka", "tanaka5678", "user"),
    ]

    print("\nユーザーを登録中...")
    for user_id, password, role in users:
        pw_hash = generate_password_hash(password)
        cur.execute("""
        INSERT INTO users (user_id, password_hash, role, is_active)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id) DO UPDATE SET
          password_hash=excluded.password_hash,
          role=excluded.role
        """, (user_id, pw_hash, role))
        print(f"  ✅ {user_id} ({role})")

    conn.commit()
    conn.close()
    
    print("\n" + "=" * 50)
    print("✅ セットアップ完了！")
    print("=" * 50)
    print("\n【ログイン情報】")
    print("  yamada  / demo-pass  (管理者)")
    print("  sato    / sato1234   (一般)")
    print("  tanaka  / tanaka5678 (一般)")
    print("\n次のコマンドでサーバーを起動してください:")
    print("  python app.py")
    print("\nアクセス: http://localhost:5000/login")
    print("=" * 50)

if __name__ == "__main__":
    main()