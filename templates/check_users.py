#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from werkzeug.security import check_password_hash

DB_PATH = 'hospital_data.sqlite3'

def check_user_login(username, password):
    """ユーザー認証をテスト"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            print(f"❌ ユーザー「{username}」が見つかりません")
            return False
        
        if not user['is_active']:
            print(f"⚠️  ユーザー「{username}」は無効化されています")
            return False
        
        if check_password_hash(user['password_hash'], password):
            role_label = '管理者' if user['role'] == 'admin' else '社員'
            print(f"✅ 認証成功: [{role_label}] {user['full_name']}")
            return True
        else:
            print(f"❌ パスワードが正しくありません")
            return False
            
    except Exception as e:
        print(f'❌ エラー: {e}')
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("病院情報管理システム - ログインテスト")
    print("=" * 60)
    print()
    
    username = input("ユーザー名: ").strip()
    password = input("パスワード: ").strip()
    
    print()
    check_user_login(username, password)
    print()
    print("=" * 60)