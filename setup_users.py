#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = 'hospital_data.sqlite3'

def setup_users():
    """初期ユーザーを作成"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

     # ログイン履歴テーブルの作成
    print("📋 ログイン履歴テーブルを作成中...\n")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT,
            success BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    print("✅ ログイン履歴テーブル作成完了\n")
    
    # 管理者1人
    admin_user = ('admin', 'Admin@2024', 'admin@cantera-kyoto.com', 'admin')
    
    # ユーザー49人（user01 ～ user49）
    regular_users = []
    for i in range(1, 50):
        username = f'user{i:02d}'  # user01, user02, ..., user49
        password = f'User{i:02d}@2024'  # User01@2024, User02@2024, ...
        email = f'user{i:02d}@cantera-kyoto.com'
        role = 'user'
        regular_users.append((username, password, email, role))
    
    # 全ユーザーリスト（管理者1人 + ユーザー49人 = 50人）
    all_users = [admin_user] + regular_users
    
    print("=" * 60)
    print("🏥 病院情報管理システム - ユーザー初期化")
    print(f"   管理者: 1人 / ユーザー: 49人 / 合計: 50人")
    print("=" * 60)
    print("\nユーザーを登録中...\n")
    
    success_count = 0
    error_count = 0
    
    for username, password, email, role in all_users:
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
            success_count += 1
            
        except Exception as e:
            print(f'❌ エラー: {username} の登録失敗: {e}')
            error_count += 1
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ セットアップ完了！")
    print("=" * 60)
    print(f"\n【登録結果】")
    print(f"  成功: {success_count}人")
    if error_count > 0:
        print(f"  失敗: {error_count}人")
    print(f"\n【初期ログイン情報】")
    print(f"  管理者: admin / Admin@2024")
    print(f"  ユーザー例: user01 / User01@2024")
    print(f"  ユーザー例: user02 / User02@2024")
    print(f"  ... (user01 ～ user49)")
    print(f"\n【次のステップ】")
    print(f"  1. サーバー起動: python app.py")
    print(f"  2. ブラウザでアクセス: http://localhost:5000/login")
    print("=" * 60 + "\n")

if __name__ == '__main__':
    setup_users()