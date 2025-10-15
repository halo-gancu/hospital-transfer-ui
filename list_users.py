#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3

DB_PATH = 'hospital_data.sqlite3'

def list_users():
    """全ユーザーを一覧表示"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, full_name, role, is_active, created_at 
            FROM users 
            ORDER BY id
        ''')
        
        users = cursor.fetchall()
        conn.close()
        
        if not users:
            print("登録されているユーザーはいません")
            return
        
        print("\n登録ユーザー一覧:")
        print("=" * 80)
        print(f"{'ID':<4} {'ユーザー名':<15} {'氏名':<15} {'権限':<8} {'状態':<6} {'登録日':<20}")
        print("-" * 80)
        
        for user in users:
            role_label = '管理者' if user['role'] == 'admin' else '社員'
            status = '有効' if user['is_active'] else '無効'
            
            print(f"{user['id']:<4} {user['username']:<15} {user['full_name']:<15} {role_label:<8} {status:<6} {user['created_at']:<20}")
        
        print("=" * 80)
        print(f"合計: {len(users)}名")
        
    except Exception as e:
        print(f'❌ エラー: {e}')

if __name__ == '__main__':
    print("=" * 80)
    print("病院情報管理システム - ユーザー一覧")
    print("=" * 80)
    list_users()
    print()