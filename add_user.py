#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import sys
from werkzeug.security import generate_password_hash

DB_PATH = 'hospital_data.sqlite3'

def add_user(username, password, full_name, role='staff'):
    """新しいユーザーを追加"""
    if role not in ['admin', 'staff']:
        print(f"❌ エラー: 権限は 'admin' または 'staff' を指定してください")
        return False
    
    if len(password) < 8:
        print(f"❌ エラー: パスワードは8文字以上にしてください")
        return False
    
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)',
            (username, password_hash, full_name, role)
        )
        
        conn.commit()
        conn.close()
        
        role_label = '管理者' if role == 'admin' else '社員'
        print(f'✅ [{role_label}] {full_name} (ID: {username}) を登録しました')
        print(f'   パスワード: {password}')
        return True
        
    except sqlite3.IntegrityError:
        print(f'⚠️  エラー: ユーザー名「{username}」は既に使用されています')
        return False
    except Exception as e:
        print(f'❌ エラー: {e}')
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("病院情報管理システム - ユーザー追加")
    print("=" * 60)
    
    # コマンドライン引数から実行
    if len(sys.argv) == 5:
        username = sys.argv[1]
        password = sys.argv[2]
        full_name = sys.argv[3]
        role = sys.argv[4]
        add_user(username, password, full_name, role)
    else:
        # 対話モードで実行
        print("\n新しいユーザーを追加します\n")
        
        username = input("ユーザー名 (例: tanaka): ").strip()
        password = input("パスワード (8文字以上): ").strip()
        full_name = input("氏名 (例: 田中太郎): ").strip()
        
        print("\n権限を選択してください:")
        print("  1. 社員 (staff)")
        print("  2. 管理者 (admin)")
        choice = input("選択 [1]: ").strip() or "1"
        
        role = "admin" if choice == "2" else "staff"
        
        print()
        add_user(username, password, full_name, role)
    
    print("=" * 60)