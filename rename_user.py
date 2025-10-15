#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import sys

DB_PATH = 'hospital_data.sqlite3'

def rename_user(old_username, new_username):
    """ユーザー名を変更"""
    if not old_username or not new_username:
        print("❌ エラー: ユーザー名を指定してください")
        return False
    
    if old_username == new_username:
        print("❌ エラー: 新旧のユーザー名が同じです")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 旧ユーザー名が存在するか確認
        cursor.execute('SELECT full_name, role FROM users WHERE username = ?', (old_username,))
        user = cursor.fetchone()
        
        if not user:
            print(f'❌ エラー: ユーザー「{old_username}」が見つかりません')
            conn.close()
            return False
        
        full_name, role = user
        
        # 新ユーザー名が既に使用されていないか確認
        cursor.execute('SELECT username FROM users WHERE username = ?', (new_username,))
        existing = cursor.fetchone()
        
        if existing:
            print(f'❌ エラー: ユーザー名「{new_username}」は既に使用されています')
            conn.close()
            return False
        
        # ユーザー名を変更
        cursor.execute('UPDATE users SET username = ? WHERE username = ?', (new_username, old_username))
        conn.commit()
        conn.close()
        
        role_label = '管理者' if role == 'admin' else '社員'
        print(f'✅ ユーザー名を変更しました')
        print(f'   [{role_label}] {full_name}')
        print(f'   変更前: {old_username}')
        print(f'   変更後: {new_username}')
        return True
        
    except sqlite3.IntegrityError:
        print(f'❌ エラー: ユーザー名「{new_username}」は既に使用されています')
        return False
    except Exception as e:
        print(f'❌ エラー: {e}')
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("病院情報管理システム - ユーザー名変更")
    print("=" * 60)
    
    if len(sys.argv) == 3:
        old_username = sys.argv[1]
        new_username = sys.argv[2]
        rename_user(old_username, new_username)
    else:
        print("\n対話モードでユーザー名を変更します\n")
        
        old_username = input("変更前のユーザー名: ").strip()
        new_username = input("変更後のユーザー名: ").strip()
        
        print()
        rename_user(old_username, new_username)
    
    print("=" * 60)