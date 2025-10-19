import sqlite3

DB_PATH = 'hospital_data.sqlite3'

def create_login_history_table():
    """ログイン履歴テーブルを作成"""
    print("📋 ログイン履歴テーブルを作成中...\n")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # テーブル作成
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
    
    # インデックス作成
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_history_user ON login_history(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_history_time ON login_history(login_time DESC)')
    
    conn.commit()
    conn.close()
    
    print("✅ ログイン履歴テーブル作成完了\n")

if __name__ == '__main__':
    create_login_history_table()