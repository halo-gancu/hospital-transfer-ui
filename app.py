from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime, timedelta
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')
socketio = SocketIO(app, cors_allowed_origins="*")

DATABASE = os.environ.get('DATABASE_PATH', 'hospital_data.sqlite3')

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """データベースの初期化"""
    conn = get_db_connection()
    
    # usersテーブル
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # password_reset_tokensテーブル
    conn.execute('''
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ データベーステーブルを初期化しました")

# アプリケーション起動時にデータベースを初期化
init_db()

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return send_from_directory('.', 'index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('index'))
        else:
            flash('ユーザー名またはパスワードが正しくありません。')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# パスワードリセット申請ページ
@app.route('/reset-password-request', methods=['GET', 'POST'])
def reset_password_request():
    if request.method == 'POST':
        email = request.form.get('email')
        
        # ユーザーが存在するか確認
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user:
            # トークンを生成
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=1)  # 1時間有効
            
            # トークンをデータベースに保存
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES (?, ?, ?)
            ''', (user['id'], token, expires_at))
            conn.commit()
            conn.close()
            
            # 実際のメール送信はここに実装（現在は省略）
            reset_url = f"https://cantera-kyoto.com/reset-password/{token}"
            
            return render_template('reset_password_request.html', 
                                 success=f'パスワードリセットリンクをメールで送信しました。<br>（開発中のため、リンクを表示: <a href="{reset_url}">{reset_url}</a>）')
        else:
            return render_template('reset_password_request.html', 
                                 error='このメールアドレスは登録されていません。')
    
    return render_template('reset_password_request.html')

# パスワード変更ページ
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # トークンを検証
    conn = get_db_connection()
    reset_token = conn.execute('''
        SELECT * FROM password_reset_tokens 
        WHERE token = ? AND expires_at > ? AND used = 0
    ''', (token, datetime.now())).fetchone()
    
    if not reset_token:
        conn.close()
        return render_template('reset_password.html', 
                             error='無効または期限切れのリンクです。', token=token)
    
    if request.method == 'POST':
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        # パスワードの検証
        if len(password) < 8:
            conn.close()
            return render_template('reset_password.html', 
                                 error='パスワードは8文字以上である必要があります。', token=token)
        
        if password != password_confirm:
            conn.close()
            return render_template('reset_password.html', 
                                 error='パスワードが一致しません。', token=token)
        
        # パスワードをハッシュ化して更新
        hashed_password = generate_password_hash(password)
        conn.execute('UPDATE users SET password = ? WHERE id = ?', 
                    (hashed_password, reset_token['user_id']))
        
        # トークンを使用済みにする
        conn.execute('UPDATE password_reset_tokens SET used = 1 WHERE id = ?', 
                    (reset_token['id'],))
        conn.commit()
        conn.close()
        
        flash('パスワードが正常に変更されました。')
        return redirect(url_for('login'))
    
    conn.close()
    return render_template('reset_password.html', token=token)

# API エンドポイント
@app.route('/api/users', methods=['GET', 'POST'])
def api_users():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    
    if request.method == 'GET':
        users = conn.execute('SELECT id, username, email, role, created_at FROM users').fetchall()
        conn.close()
        return jsonify([dict(user) for user in users])
    
    elif request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        role = data.get('role', 'user')
        
        if not username or not password or not email:
            conn.close()
            return jsonify({'error': 'Missing required fields'}), 400
        
        hashed_password = generate_password_hash(password)
        
        try:
            conn.execute('INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)',
                        (username, hashed_password, email, role))
            conn.commit()
            conn.close()
            return jsonify({'message': 'User created successfully'}), 201
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'error': 'Username or email already exists'}), 400

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🏥 病院情報管理システム サーバー起動中...")
    print("=" * 60)
    print(f"📍 ログインURL: http://localhost:5000/login")
    print(f"💾 データベース: {DATABASE}")
    print("=" * 60 + "\n")
    
    app.run(debug=True, host='0.0.0.0')