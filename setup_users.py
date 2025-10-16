#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = 'hospital_data.sqlite3'

def setup_users():
    """初期ユーザーを作成"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # ユーザーリスト（username, password, email, role）
    users = [
        ('admin',  'Admin@2024',  'admin@cantera-kyoto.com', 'admin'),
        ('toyoda', 'Toyoda@2024', 'toyoda@cantera-kyoto.com', 'user'),
        ('kudo',   'Kudo@2024',   'kudo@cantera-kyoto.com',   'user'),
        ('yamada', 'Yamada@2024', 'yamada@cantera-kyoto.com', 'user'),
    ]
    
    print("=" * 60)
    print("🏥 病院情報管理システム - ユーザー初期化")
    print("=" * 60)
    print("\nユーザーを登録中...\n")
    
    for username, password, email, role in users:
        try:
            # パスワードをハッシュ化
            password_hash = generate_password_hash(password)
            
            # ユーザーを挿入（既存の場合は更新）
            cursor.execute('''
                INSERT INTO users (username, password, email, role)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password = excluded.password,
                    email = excluded.email,
                    role = excluded.role
            ''', (username, password_hash, email, role))
            
            role_label = '管理者' if role == 'admin' else 'ユーザー'
            print(f'✅ [{role_label}] {username} - パスワード: {password}')
            
        except Exception as e:
            print(f'❌ エラー: {username} の登録失敗: {e}')
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ セットアップ完了！")
    print("=" * 60)
    print("\n【初期ログイン情報】")
    print("  管理者: admin / Admin@2024")
    print("  ユーザー: toyoda / Toyoda@2024")
    print("\n【次のステップ】")
    print("  1. サーバー起動: python app.py")
    print("  2. ブラウザでアクセス: http://localhost:5000/login")
    print("=" * 60 + "\n")

if __name__ == '__main__':
    setup_users()