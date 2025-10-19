from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import json
from datetime import datetime, timedelta
import secrets

app = Flask(__name__)

# ============================================
# セッション設定
# ============================================
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # ローカル開発環境用（HTTPSの場合はTrue）
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_NAME'] = 'hospital_session'

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
    
    # mdataテーブル（病院データ）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mdata (
            code TEXT PRIMARY KEY,
            kv TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER,
            FOREIGN KEY (updated_by) REFERENCES users (id)
        )
    ''')
    
    # locksテーブル（編集ロック）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS locks (
            code TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # 🆕 historyテーブル（変更履歴）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            action TEXT NOT NULL,
            old_data TEXT,
            new_data TEXT,
            changed_fields TEXT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # 履歴テーブルのインデックス（検索高速化）
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_history_code 
        ON history(code)
    ''')
    
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_history_user 
        ON history(user_id)
    ''')
    
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_history_created 
        ON history(created_at DESC)
    ''')
    
    conn.commit()
    conn.close()
    print("✅ データベーステーブルを初期化しました")

# アプリケーション起動時にデータベースを初期化
init_db()

# ============================================
# 履歴記録用のヘルパー関数
# ============================================

def record_history(code, action, old_data, new_data, user_id, username):
    """
    データ変更履歴を記録
    
    Args:
        code: 病院コード
        action: アクション ('create', 'update', 'delete')
        old_data: 変更前のデータ（辞書）
        new_data: 変更後のデータ（辞書）
        user_id: ユーザーID
        username: ユーザー名
    """
    conn = get_db_connection()
    
    # 変更されたフィールドを検出
    changed_fields = []
    if old_data and new_data:
        for key in set(list(old_data.keys()) + list(new_data.keys())):
            old_value = old_data.get(key, '')
            new_value = new_data.get(key, '')
            if old_value != new_value:
                changed_fields.append(key)
    
    # JSON形式で保存
    old_data_json = json.dumps(old_data, ensure_ascii=False) if old_data else None
    new_data_json = json.dumps(new_data, ensure_ascii=False) if new_data else None
    changed_fields_json = json.dumps(changed_fields, ensure_ascii=False) if changed_fields else None
    
    # 履歴を記録
    conn.execute('''
        INSERT INTO history (code, action, old_data, new_data, changed_fields, user_id, username)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (code, action, old_data_json, new_data_json, changed_fields_json, user_id, username))
    
    conn.commit()
    conn.close()
    
    print(f"📝 履歴記録: code={code}, action={action}, user={username}, fields={len(changed_fields)}")

def record_login_history(user_id, username, success=True, ip_address=None, user_agent=None):
    """
    ログイン履歴を記録
    
    Args:
        user_id: ユーザーID（失敗時はNone）
        username: ユーザー名
        success: ログイン成功/失敗
        ip_address: IPアドレス
        user_agent: ブラウザ情報
    """
    conn = get_db_connection()
    
    conn.execute('''
        INSERT INTO login_history (user_id, username, ip_address, user_agent, success)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, ip_address, user_agent, success))
    
    conn.commit()
    conn.close()
    
    status = '成功' if success else '失敗'
    print(f"📝 ログイン履歴記録: username={username}, status={status}, ip={ip_address}")

# ============================================
# 認証チェック用デコレータ
# ============================================
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            print(f"❌ 未認証アクセス: {request.path}")
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        print(f"✅ 認証済みアクセス: user_id={session.get('user_id')}, path={request.path}")
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# ルート定義
# ============================================

@app.route('/')
def index():
    """メインページ"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    print(f"📄 メインページ表示: user={session.get('username')}, role={session.get('role')}")
    return send_from_directory('.', 'index.html')

# 静的ファイルの提供
@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory('css', filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory('js', filename)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # 既にログイン済みの場合はメインページへ
    if 'user_id' in session:
        print(f"✅ 既にログイン済み: user_id={session.get('user_id')}")
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 🆕 IPアドレスとUser-Agentを取得
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent', '')
        
        print(f"🔍 ログイン試行: username={username}, ip={ip_address}")
        
        if not username or not password:
            flash('ユーザー名とパスワードを入力してください。')
            return render_template('login.html')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user:
            print(f"🔍 ユーザー発見: id={user['id']}, username={user['username']}, role={user['role']}")
            
            if check_password_hash(user['password'], password):
                print(f"✅ パスワード検証成功")
                
                # セッションをクリアして新規設定
                session.clear()
                
                # セッション情報を設定
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                session.permanent = True  # 永続セッションを有効化
                
                print(f"✅ セッション設定完了:")
                print(f"   - user_id: {session.get('user_id')}")
                print(f"   - username: {session.get('username')}")
                print(f"   - role: {session.get('role')}")
                print(f"   - permanent: {session.permanent}")
                
                # 🆕 ログイン成功の履歴を記録
                record_login_history(user['id'], user['username'], True, ip_address, user_agent)
                
                flash('ログインに成功しました。', 'success')
                return redirect(url_for('index'))
            else:
                print(f"❌ パスワード検証失敗")
                # 🆕 ログイン失敗を記録
                record_login_history(user['id'], username, False, ip_address, user_agent)
                flash('ユーザー名またはパスワードが正しくありません。')
        else:
            print(f"❌ ユーザーが見つかりません: username={username}")
            # 🆕 ログイン失敗を記録（user_idはNone）
            record_login_history(None, username, False, ip_address, user_agent)
            flash('ユーザー名またはパスワードが正しくありません。')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('username', 'Unknown')
    user_id = session.get('user_id')
    
    # ユーザーが保持しているすべてのロックを解放
    if user_id:
        conn = get_db_connection()
        conn.execute('DELETE FROM locks WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        print(f"🔓 ロック解放: user_id={user_id}")
    
    session.clear()
    print(f"👋 ログアウト: user={username}")
    flash('ログアウトしました。')
    return redirect(url_for('login'))

# ============================================
# ユーザー管理・パスワード変更・履歴ページ
# ============================================

@app.route('/user_management')
def user_management():
    """ユーザー管理ページ"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # 管理者のみアクセス可能
    if session.get('role') != 'admin':
        flash('管理者のみアクセスできます。')
        return redirect(url_for('index'))
    
    print(f"👥 ユーザー管理ページ表示: user={session.get('username')}")
    return render_template('user_management.html')

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    """パスワード変更ページ（ログイン後）"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        new_password_confirm = request.form.get('new_password_confirm')
        
        if not current_password or not new_password or not new_password_confirm:
            flash('すべての項目を入力してください。')
            return render_template('change_password.html')
        
        if new_password != new_password_confirm:
            flash('新しいパスワードが一致しません。')
            return render_template('change_password.html')
        
        if len(new_password) < 8:
            flash('パスワードは8文字以上である必要があります。')
            return render_template('change_password.html')
        
        # 現在のパスワードを確認
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        if not user or not check_password_hash(user['password'], current_password):
            conn.close()
            flash('現在のパスワードが正しくありません。')
            return render_template('change_password.html')
        
        # パスワードを更新
        hashed_password = generate_password_hash(new_password)
        conn.execute('UPDATE users SET password = ? WHERE id = ?', 
                    (hashed_password, session['user_id']))
        conn.commit()
        conn.close()
        
        print(f"✅ パスワード変更成功: user_id={session['user_id']}")
        flash('パスワードを変更しました。', 'success')
        return redirect(url_for('index'))
    
    print(f"🔑 パスワード変更ページ表示: user={session.get('username')}")
    return render_template('change_password.html')

@app.route('/history')
def history():
    """変更履歴ページ"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    print(f"📜 変更履歴ページ表示: user={session.get('username')}")
    return render_template('history.html')

@app.route('/login_history')
def login_history():
    """🆕 ログイン履歴ページ"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    print(f"📊 ログイン履歴ページ表示: user={session.get('username')}")
    return render_template('login_history.html')

# ============================================
# パスワードリセット（メール経由）
# ============================================

@app.route('/reset-password-request', methods=['GET', 'POST'])
def reset_password_request():
    if request.method == 'POST':
        email = request.form.get('email')
        
        if not email:
            return render_template('reset_password_request.html', 
                                 error='メールアドレスを入力してください。')
        
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
            
            # リセットURLを生成
            reset_url = url_for('reset_password', token=token, _external=True)
            
            print(f"🔑 パスワードリセットトークン生成: user={user['username']}, token={token[:10]}...")
            
            return render_template('reset_password_request.html', 
                                 success=f'パスワードリセットリンクをメールで送信しました。<br>（開発中のため、リンクを表示: <a href="{reset_url}">{reset_url}</a>）')
        else:
            # セキュリティのため、ユーザーが存在しない場合も同じメッセージを表示
            return render_template('reset_password_request.html', 
                                 success='パスワードリセットリンクをメールで送信しました。（登録されている場合）')
    
    return render_template('reset_password_request.html')

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
        print(f"❌ 無効なトークン: {token[:10]}...")
        return render_template('reset_password.html', 
                             error='無効または期限切れのリンクです。', token=token)
    
    if request.method == 'POST':
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        # パスワードの検証
        if not password or not password_confirm:
            conn.close()
            return render_template('reset_password.html', 
                                 error='パスワードを入力してください。', token=token)
        
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
        
        # ユーザー情報を取得
        user = conn.execute('SELECT username FROM users WHERE id = ?', 
                          (reset_token['user_id'],)).fetchone()
        conn.close()
        
        print(f"✅ パスワードリセット成功: user={user['username']}")
        
        flash('パスワードが正常に変更されました。新しいパスワードでログインしてください。', 'success')
        return redirect(url_for('login'))
    
    conn.close()
    return render_template('reset_password.html', token=token)

# ============================================
# API エンドポイント
# ============================================

@app.route('/api/health', methods=['GET'])
def api_health():
    """ヘルスチェック"""
    return jsonify({'ok': True, 'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/api/session', methods=['GET'])
def api_session():
    """セッション情報を返す"""
    if 'user_id' not in session:
        return jsonify({
            'ok': False,
            'logged_in': False,
            'message': 'Not logged in'
        }), 401
    
    return jsonify({
        'ok': True,
        'logged_in': True,
        'user': {
            'id': session.get('user_id'),
            'username': session.get('username'),
            'role': session.get('role')
        },
        'permanent': session.permanent
    })

@app.route('/api/lock/status', methods=['GET'])
@login_required
def api_lock_status():
    """すべてのロック状態を取得"""
    conn = get_db_connection()
    locks = conn.execute('SELECT code, user_id, username, locked_at FROM locks').fetchall()
    conn.close()
    
    return jsonify({
        'ok': True,
        'locks': [dict(lock) for lock in locks]
    })

@app.route('/api/lock/<code>', methods=['POST', 'DELETE'])
@login_required
def api_lock(code):
    """ロックの取得/解放"""
    conn = get_db_connection()
    user_id = session.get('user_id')
    username = session.get('username')
    
    if request.method == 'POST':
        # ロックを取得
        existing_lock = conn.execute('SELECT * FROM locks WHERE code = ?', (code,)).fetchone()
        
        if existing_lock:
            if existing_lock['user_id'] == user_id:
                # 自分が既にロックしている
                conn.close()
                return jsonify({'ok': True, 'message': 'Already locked by you'})
            else:
                # 他のユーザーがロックしている
                conn.close()
                return jsonify({
                    'ok': False,
                    'error': f'Locked by {existing_lock["username"]}',
                    'locked_by': existing_lock['username']
                }), 409
        
        # ロックを設定
        conn.execute('INSERT INTO locks (code, user_id, username) VALUES (?, ?, ?)', 
                    (code, user_id, username))
        conn.commit()
        conn.close()
        
        print(f"🔒 ロック取得: code={code}, user={username}")
        return jsonify({'ok': True, 'message': 'Lock acquired'})
    
    elif request.method == 'DELETE':
        # ロックを解放
        conn.execute('DELETE FROM locks WHERE code = ? AND user_id = ?', (code, user_id))
        conn.commit()
        conn.close()
        
        print(f"🔓 ロック解放: code={code}, user={username}")
        return jsonify({'ok': True, 'message': 'Lock released'})

@app.route('/api/mdata/search', methods=['GET'])
@login_required
def api_mdata_search():
    """病院データ検索"""
    prefix = request.args.get('prefix', '')
    
    conn = get_db_connection()
    
    if prefix:
        # 前方一致検索
        query = 'SELECT code FROM mdata WHERE code LIKE ? ORDER BY code'
        results = conn.execute(query, (f'{prefix}%',)).fetchall()
    else:
        # すべて取得
        results = conn.execute('SELECT code FROM mdata ORDER BY code').fetchall()
    
    conn.close()
    
    items = [{'code': row['code']} for row in results]
    
    return jsonify({
        'ok': True,
        'items': items,
        'count': len(items)
    })

@app.route('/api/mdata/<code>', methods=['GET', 'POST'])
@login_required
def api_mdata(code):
    """病院データの取得/保存（履歴記録付き）"""
    conn = get_db_connection()
    user_id = session.get('user_id')
    username = session.get('username')
    
    if request.method == 'GET':
        # データ取得
        row = conn.execute('SELECT * FROM mdata WHERE code = ?', (code,)).fetchone()
        conn.close()
        
        if not row:
            return jsonify({'ok': False, 'error': 'Not found'}), 404
        
        try:
            kv = json.loads(row['kv'])
        except:
            kv = {}
        
        return jsonify({
            'ok': True,
            'code': row['code'],
            'kv': kv,
            'updated_at': row['updated_at']
        })
    
    elif request.method == 'POST':
        # データ保存
        data = request.json
        kv = data.get('kv', {})
        
        if not kv:
            conn.close()
            return jsonify({'ok': False, 'error': 'No data provided'}), 400
        
        kv_json = json.dumps(kv, ensure_ascii=False)
        
        # 🆕 既存データを取得（履歴記録用）
        existing = conn.execute('SELECT * FROM mdata WHERE code = ?', (code,)).fetchone()
        
        old_data = None
        action = 'create'
        
        if existing:
            # 更新の場合
            action = 'update'
            try:
                old_data = json.loads(existing['kv'])
            except:
                old_data = {}
            
            conn.execute('''
                UPDATE mdata 
                SET kv = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                WHERE code = ?
            ''', (kv_json, user_id, code))
        else:
            # 新規作成の場合
            conn.execute('''
                INSERT INTO mdata (code, kv, updated_by) 
                VALUES (?, ?, ?)
            ''', (code, kv_json, user_id))
        
        conn.commit()
        conn.close()
        
        # 🆕 履歴を記録
        record_history(code, action, old_data, kv, user_id, username)
        
        print(f"💾 データ保存: code={code}, user_id={user_id}, action={action}")
        
        return jsonify({
            'ok': True,
            'message': 'Data saved',
            'updated': len(kv),
            'action': action
        })

# ============================================
# 🆕 履歴管理API
# ============================================

@app.route('/api/history', methods=['GET'])
@login_required
def api_history():
    """全体の履歴を取得"""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    conn = get_db_connection()
    
    # 履歴を取得
    histories = conn.execute('''
        SELECT * FROM history 
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    ''', (limit, offset)).fetchall()
    
    # 総件数を取得
    total = conn.execute('SELECT COUNT(*) as count FROM history').fetchone()['count']
    
    conn.close()
    
    # 結果を整形
    result = []
    for h in histories:
        try:
            changed_fields = json.loads(h['changed_fields']) if h['changed_fields'] else []
        except:
            changed_fields = []
        
        result.append({
            'id': h['id'],
            'code': h['code'],
            'action': h['action'],
            'changed_fields': changed_fields,
            'user_id': h['user_id'],
            'username': h['username'],
            'created_at': h['created_at']
        })
    
    return jsonify({
        'ok': True,
        'histories': result,
        'total': total,
        'limit': limit,
        'offset': offset
    })

@app.route('/api/history/<code>', methods=['GET'])
@login_required
def api_history_by_code(code):
    """特定の病院の履歴を取得"""
    conn = get_db_connection()
    
    histories = conn.execute('''
        SELECT * FROM history 
        WHERE code = ?
        ORDER BY created_at DESC
    ''', (code,)).fetchall()
    
    conn.close()
    
    # 結果を整形
    result = []
    for h in histories:
        try:
            old_data = json.loads(h['old_data']) if h['old_data'] else None
            new_data = json.loads(h['new_data']) if h['new_data'] else None
            changed_fields = json.loads(h['changed_fields']) if h['changed_fields'] else []
        except:
            old_data = None
            new_data = None
            changed_fields = []
        
        result.append({
            'id': h['id'],
            'code': h['code'],
            'action': h['action'],
            'old_data': old_data,
            'new_data': new_data,
            'changed_fields': changed_fields,
            'user_id': h['user_id'],
            'username': h['username'],
            'created_at': h['created_at']
        })
    
    return jsonify({
        'ok': True,
        'code': code,
        'histories': result,
        'count': len(result)
    })

# ============================================
# 🆕 ログイン履歴API
# ============================================

@app.route('/api/login_history', methods=['GET'])
@login_required
def api_login_history():
    """ログイン履歴を取得"""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    user_id = request.args.get('user_id', type=int)  # 特定ユーザーのみ取得
    
    conn = get_db_connection()
    
    # 管理者以外は自分の履歴のみ閲覧可能
    current_user_role = session.get('role')
    current_user_id = session.get('user_id')
    
    if current_user_role != 'admin':
        user_id = current_user_id
    
    # クエリ構築
    if user_id:
        query = '''
            SELECT * FROM login_history 
            WHERE user_id = ?
            ORDER BY login_time DESC 
            LIMIT ? OFFSET ?
        '''
        histories = conn.execute(query, (user_id, limit, offset)).fetchall()
        total = conn.execute('SELECT COUNT(*) as count FROM login_history WHERE user_id = ?', 
                           (user_id,)).fetchone()['count']
    else:
        query = '''
            SELECT * FROM login_history 
            ORDER BY login_time DESC 
            LIMIT ? OFFSET ?
        '''
        histories = conn.execute(query, (limit, offset)).fetchall()
        total = conn.execute('SELECT COUNT(*) as count FROM login_history').fetchone()['count']
    
    conn.close()
    
    # 結果を整形
    result = []
    for h in histories:
        result.append({
            'id': h['id'],
            'user_id': h['user_id'],
            'username': h['username'],
            'login_time': h['login_time'],
            'ip_address': h['ip_address'],
            'user_agent': h['user_agent'],
            'success': bool(h['success'])
        })
    
    return jsonify({
        'ok': True,
        'histories': result,
        'total': total,
        'limit': limit,
        'offset': offset
    })

# ============================================
# 都道府県・病院リストAPI
# ============================================

@app.route('/api/prefectures', methods=['GET'])
@login_required
def api_prefectures():
    """都道府県リストを取得"""
    conn = get_db_connection()
    
    # 都道府県コードから一意の値を取得
    query = '''
        SELECT DISTINCT substr(code, 1, 2) as pref_code
        FROM mdata
        ORDER BY pref_code
    '''
    
    results = conn.execute(query).fetchall()
    conn.close()
    
    # 都道府県コードと名前のマッピング
    pref_names = {
        '01': '北海道', '02': '青森県', '03': '岩手県', '04': '宮城県', '05': '秋田県',
        '06': '山形県', '07': '福島県', '08': '茨城県', '09': '栃木県', '10': '群馬県',
        '11': '埼玉県', '12': '千葉県', '13': '東京都', '14': '神奈川県', '15': '新潟県',
        '16': '富山県', '17': '石川県', '18': '福井県', '19': '山梨県', '20': '長野県',
        '21': '岐阜県', '22': '静岡県', '23': '愛知県', '24': '三重県', '25': '滋賀県',
        '26': '京都府', '27': '大阪府', '28': '兵庫県', '29': '奈良県', '30': '和歌山県',
        '31': '鳥取県', '32': '島根県', '33': '岡山県', '34': '広島県', '35': '山口県',
        '36': '徳島県', '37': '香川県', '38': '愛媛県', '39': '高知県', '40': '福岡県',
        '41': '佐賀県', '42': '長崎県', '43': '熊本県', '44': '大分県', '45': '宮崎県',
        '46': '鹿児島県', '47': '沖縄県'
    }
    
    prefectures = []
    for row in results:
        pref_code = row['pref_code']
        pref_name = pref_names.get(pref_code, f'都道府県{pref_code}')
        
        prefectures.append({
            'code': pref_code,
            'name': pref_name
        })
    
    print(f"📊 都道府県リスト取得: {len(prefectures)}件")
    
    return jsonify({
        'ok': True,
        'prefectures': prefectures
    })

@app.route('/api/hospitals', methods=['GET'])
@login_required
def api_hospitals():
    """都道府県で絞り込んだ病院リストを取得"""
    prefecture = request.args.get('prefecture', '')
    
    if not prefecture:
        return jsonify({'ok': False, 'error': 'Prefecture code required'}), 400
    
    conn = get_db_connection()
    
    # 都道府県コードで前方一致検索（例：'01' -> '01-*'）
    query = '''
        SELECT code, kv
        FROM mdata
        WHERE code LIKE ?
        ORDER BY code
    '''
    
    results = conn.execute(query, (f'{prefecture}-%',)).fetchall()
    conn.close()
    
    hospitals = []
    for row in results:
        try:
            kv = json.loads(row['kv'])
            hospital_name = kv.get('病院名', '')
            
            if hospital_name:  # 病院名がある場合のみ追加
                hospitals.append({
                    'code': row['code'],
                    'name': hospital_name
                })
        except:
            # JSONのパースに失敗した場合はスキップ
            continue
    
    print(f"🏥 病院リスト取得: prefecture={prefecture}, count={len(hospitals)}")
    
    return jsonify({
        'ok': True,
        'hospitals': hospitals,
        'count': len(hospitals)
    })

# ============================================
# ユーザー管理API
# ============================================

@app.route('/api/users', methods=['GET', 'POST'])
@login_required
def api_users():
    """ユーザー管理API"""
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
        
        if len(password) < 8:
            conn.close()
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        
        hashed_password = generate_password_hash(password)
        
        try:
            conn.execute('INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)',
                        (username, hashed_password, email, role))
            conn.commit()
            conn.close()
            print(f"✅ ユーザー作成: username={username}, role={role}")
            return jsonify({'message': 'User created successfully'}), 201
        except sqlite3.IntegrityError as e:
            conn.close()
            print(f"❌ ユーザー作成失敗: {str(e)}")
            return jsonify({'error': 'Username or email already exists'}), 400

@app.route('/api/users/<int:user_id>', methods=['PUT', 'DELETE'])
@login_required
def api_user(user_id):
    """個別ユーザー管理API"""
    conn = get_db_connection()
    
    if request.method == 'PUT':
        data = request.json
        
        # 更新するフィールドを構築
        updates = []
        params = []
        
        if 'username' in data:
            updates.append('username = ?')
            params.append(data['username'])
        
        if 'email' in data:
            updates.append('email = ?')
            params.append(data['email'])
        
        if 'role' in data:
            updates.append('role = ?')
            params.append(data['role'])
        
        if 'password' in data and data['password']:
            if len(data['password']) < 8:
                conn.close()
                return jsonify({'error': 'Password must be at least 8 characters'}), 400
            updates.append('password = ?')
            params.append(generate_password_hash(data['password']))
        
        if not updates:
            conn.close()
            return jsonify({'error': 'No fields to update'}), 400
        
        params.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        
        try:
            conn.execute(query, params)
            conn.commit()
            conn.close()
            print(f"✅ ユーザー更新: user_id={user_id}")
            return jsonify({'message': 'User updated successfully'})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'error': 'Username or email already exists'}), 400
    
    elif request.method == 'DELETE':
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        print(f"✅ ユーザー削除: user_id={user_id}")
        return jsonify({'message': 'User deleted successfully'})

# ============================================
# Socket.IO イベント
# ============================================

@socketio.on('connect')
def handle_connect():
    """クライアント接続時"""
    user_id = session.get('user_id')
    username = session.get('username')
    
    if user_id and username:
        print(f"🔌 Socket接続: user={username} (ID: {user_id})")
        emit('connection_response', {'status': 'connected', 'username': username})
    else:
        print(f"🔌 Socket接続: 未認証ユーザー")

@socketio.on('disconnect')
def handle_disconnect():
    """クライアント切断時"""
    username = session.get('username', 'Unknown')
    print(f"🔌 Socket切断: user={username}")

# ============================================
# エラーハンドラ
# ============================================

@app.errorhandler(404)
def not_found(error):
    print(f"❌ 404エラー: {request.path}")
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    return render_template('login.html'), 404

@app.errorhandler(500)
def internal_error(error):
    print(f"❌ 500エラー: {str(error)}")
    return jsonify({'ok': False, 'error': 'Internal server error'}), 500

# ============================================
# アプリケーション起動
# ============================================

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🏥 病院情報管理システム サーバー起動中...")
    print("=" * 60)
    print(f"📍 ログインURL: http://localhost:5000/login")
    print(f"💾 データベース: {DATABASE}")
    print(f"🔑 SECRET_KEY: {'設定済み' if app.config['SECRET_KEY'] else '未設定'}")
    print(f"⏰ セッション有効期限: {app.config['PERMANENT_SESSION_LIFETIME']}")
    print("=" * 60 + "\n")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)