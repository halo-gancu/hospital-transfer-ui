#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = 'hospital_data.sqlite3'
SHOW_PLAINTEXT_PASSWORDS = True

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            password_changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            email TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hospital_data (
            code TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            updated_by TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (code, key)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ データベーステーブルを作成しました")

def upsert_user(cursor, username, password, full_name, role='user', email=''):
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    cursor.execute('''
        INSERT INTO users (username, password_hash, full_name, role, is_active, password_changed_at, email)
        VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(username) DO UPDATE SET
            password_hash = excluded.password_hash,
            full_name = excluded.full_name,
            role = excluded.role,
            is_active = 1,
            password_changed_at = CURRENT_TIMESTAMP,
            email = excluded.email
    ''', (username, password_hash, full_name, role, email))

def init_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    users = [
        ('admin',  'Admin@2024',  '大山勝雄', 'admin', ''),
        ('toyoda', 'Toyoda@2024', '豊田祐樹', 'staff', ''),
        ('kudo',   'Kudo@2024',   '工藤宗徳', 'staff', ''),
        ('yamada', 'Yamada@2024', '山田大聖', 'staff', ''),
        ('staff4', 'Staff4@2024', '社員4',    'staff', ''),
        ('staff5', 'Staff5@2024', '社員5',    'staff', ''),
    ]
    
    print("=" * 60)
    print("病院情報管理システム - 初期化")
    print("=" * 60)
    print("\nユーザーを登録/更新中...\n")
    
    for username, password, full_name, role, email in users:
        try:
            upsert_user(cursor, username, password, full_name, role, email)
            role_label = '管理者' if role == 'admin' else '社員'
            if SHOW_PLAINTEXT_PASSWORDS:
                print(f'✅ [{role_label}] {full_name} (ID: {username}) - パスワード: {password}')
            else:
                print(f'✅ [{role_label}] {full_name} (ID: {username}) を作成/更新')
        except Exception as e:
            print(f'❌ エラー: {username} ({full_name}) の登録失敗: {e}')
    
    conn.commit()
    conn.close()
    
    print("=" * 60)
    print("✅ セットアップ完了！")
    print("=" * 60)
    if SHOW_PLAINTEXT_PASSWORDS:
        print("\n【初期ログイン情報】")
        print("  管理者: admin / Admin@2024")
        print("  社員:  toyoda / Toyoda@2024")
    
    print("\n【次のステップ】")
    print("  1. サーバー起動: python app.py")
    print("  2. ログイン: http://localhost:5000/login")
    print("=" * 60)

if __name__ == '__main__':
    init_database()
    init_users()