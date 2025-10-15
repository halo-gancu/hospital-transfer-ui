#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import io
import csv
import re
import sqlite3
import threading
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, request, jsonify, send_from_directory,
    session, redirect, url_for, render_template
)
from flask_cors import CORS
from flask_socketio import SocketIO
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash

MAIL_ENABLED = False
try:
    from flask_mailman import Mail, EmailMessage
    MAIL_ENABLED = True
except ImportError:
    print("⚠️ flask_mailmanが見つかりません。メール機能は無効です。")

# ======================================
# 設定
# ======================================
APP_DIR  = os.path.abspath(os.path.dirname(__file__))
DEFAULT_DB_PATH = os.path.join(APP_DIR, "hospital_data.sqlite3")
DB_PATH = os.environ.get('DATABASE_URL', DEFAULT_DB_PATH)
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
if not app.config["SECRET_KEY"]:
    print("🚨 警告: SECRET_KEYが環境変数に設定されていません。開発用に一時的なキーを生成します。")
    app.config["SECRET_KEY"] = secrets.token_hex(32)

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

if MAIL_ENABLED:
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    mail = Mail(app)

CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

DB_LOCK = threading.Lock()

# ======================================
# DB ヘルパー
# ======================================
def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_users_table():
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute('''
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
        con.commit()

def init_hospital_data_table():
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute('''
CREATE TABLE IF NOT EXISTS hospital_data (
    code TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, key)
)
        ''')
        con.commit()

@app.cli.command("init-db")
def init_db_command():
    init_users_table()
    init_hospital_data_table()
    print("🎉 データベースの初期化が完了しました。")

# ======================================
# パスワード強度チェック
# ======================================
def is_strong_password(password: str) -> bool:
    if len(password) < 12: return False
    if not re.search(r'[A-Z]', password): return False
    if not re.search(r'[a-z]', password): return False
    if not re.search(r'\d', password): return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password): return False
    return True

# ======================================
# CSRF トークン
# ======================================
def issue_csrf_token() -> str:
    token = secrets.token_hex(16)
    session["csrf_token"] = token
    return token

def require_csrf(token: str) -> bool:
    return token and session.get("csrf_token") == token

# ======================================
# ログイン検証
# ======================================
def find_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE username=? LIMIT 1", (username,))
        row = cur.fetchone()
        return dict(row) if row else None

def find_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE email=? AND is_active=1 LIMIT 1", (email,))
        row = cur.fetchone()
        return dict(row) if row else None

def verify_login(username: str, password: str) -> bool:
    u = find_user_by_username(username)
    if not u:
        return False
    return check_password_hash(u["password_hash"], password)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"ok": False, "error": "未認証"}), 401
        if session.get("role") != "admin":
            return jsonify({"ok": False, "error": "管理者権限が必要です"}), 403
        return f(*args, **kwargs)
    return decorated_function

# ======================================
# レート制限
# ======================================
_login_attempts: Dict[str, list] = {}
MAX_FAILS = 5
LOCK_MIN  = 3

def _rate_limit_check() -> Optional[str]:
    ip = request.remote_addr
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < LOCK_MIN*60]
    _login_attempts[ip] = attempts
    if len(attempts) >= MAX_FAILS:
        return "一定時間後に再試行してください"
    return None

def _rate_limit_fail():
    ip = request.remote_addr
    now = time.time()
    _login_attempts.setdefault(ip, []).append(now)

def _rate_limit_success():
    ip = request.remote_addr
    _login_attempts[ip] = []

# ======================================
# 認証まわり
# ======================================
@app.route("/api/csrf_token", methods=["GET"])
def get_csrf_token():
    token = issue_csrf_token()
    return jsonify({"ok": True, "token": token})

@app.route("/login", methods=["GET"])
def login_page():
    if session.get("user_id"):
        return redirect(url_for("root_index"))
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    locked = _rate_limit_check()
    if locked:
        return jsonify({"ok": False, "error": locked}), 429

    data = request.get_json(silent=True) or {}
    username = (data.get("user") or "").strip()
    password = (data.get("pw") or "")
    csrf = data.get("csrf") or ""

    if not require_csrf(csrf):
        return jsonify({"ok": False, "error": "CSRF検証に失敗しました"}), 400

    if not username or not password:
        _rate_limit_fail()
        return jsonify({"ok": False, "error": "ユーザー名とパスワードを入力してください"}), 400

    if verify_login(username, password):
        _rate_limit_success()
        user = find_user_by_username(username)
        if not user:
            return jsonify({"ok": False, "error": "ユーザーが見つかりません"}), 401
        if not user.get("is_active", 1):
            return jsonify({"ok": False, "error": "アカウントが無効化されています"}), 403

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]
        session["csrf_token"] = issue_csrf_token()
        session.permanent = True

        return jsonify({
            "ok": True,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"]
            }
        })
    else:
        _rate_limit_fail()
        return jsonify({"ok": False, "error": "ユーザー名またはパスワードが正しくありません"}), 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# ======================================
# パスワードリセットAPI
# ======================================
@app.route("/api/users/reset", methods=["POST"])
def request_password_reset():
    if not MAIL_ENABLED:
        return jsonify({"ok": False, "error": "メール機能が無効です。管理者に連絡してください。"}), 503

    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()

    if not email:
        return jsonify({"ok": False, "error": "メールアドレスを入力してください"}), 400

    user = find_user_by_email(email)
    if not user:
        return jsonify({"ok": True, "message": "リセットリンクをメールに送信しました"})

    try:
        token = s.dumps(user["id"], salt="password-reset")
        reset_url = f"{BASE_URL}/reset-password?token={token}"

        msg = EmailMessage(
            subject="パスワードリセットのお知らせ",
            to=[email],
            from_email=app.config.get("MAIL_USERNAME"),
        )
        msg.body = (
            "以下のリンクからパスワードをリセットしてください（有効期限15分）:\n"
            f"{reset_url}\n\n"
            "ご注意: 新パスワードは12文字以上で複雑に設定してください。"
        )

        mail.send(msg)
        return jsonify({"ok": True, "message": "リセットリンクをメールに送信しました"})
    except Exception as e:
        print(f"❌ メール送信エラー: {str(e)}")
        return jsonify({"ok": False, "error": "メール送信に失敗しました"}), 500

@app.route("/api/users/reset/<token>", methods=["POST"])
def confirm_password_reset(token):
    try:
        user_id = s.loads(token, salt='password-reset', max_age=900)
        with DB_LOCK, db_connect() as con:
            row = con.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                return jsonify({"ok": False, "error": "ユーザーが見つかりません"}), 404
            username = row['username']
        user = find_user_by_username(username)
        if not user:
            return jsonify({"ok": False, "error": "ユーザーが見つかりません"}), 404

        data = request.get_json(silent=True) or {}
        new_password = data.get("new_password", "")

        if not new_password or not is_strong_password(new_password):
            return jsonify({"ok": False, "error": "パスワードが弱いです（12文字以上、大文字/小文字/数字/記号を含む）"}), 400

        new_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        with DB_LOCK, db_connect() as con:
            con.execute("UPDATE users SET password_hash=?, password_changed_at=datetime('now') WHERE id=?", (new_hash, user_id))
            con.commit()

        return jsonify({"ok": True, "message": "パスワードがリセットされました。ログインしてください"})
    except Exception as e:
        print(f"❌ パスワードリセットエラー: {str(e)}")
        return jsonify({"ok": False, "error": "トークンが無効または期限切れです"}), 400

# ======================================
# パスワード変更ページ
# ======================================
@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password_page():
    if request.method == 'GET':
        return render_template("change_password.html")

    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    new_pw_confirm = request.form.get("new_password_confirm", "")

    if not current_pw or not new_pw or not new_pw_confirm:
        return render_template('change_password.html', error="全ての項目を入力してください")
    if new_pw != new_pw_confirm:
        return render_template('change_password.html', error="新しいパスワードが一致しません")
    if len(new_pw) < 8:
        return render_template('change_password.html', error="パスワードは8文字以上で設定してください")

    username = session.get("username")
    if not username:
        return redirect(url_for('login_page'))

    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
        user = cur.fetchone()

        if not user or not check_password_hash(user["password_hash"], current_pw):
            return render_template('change_password.html', error="現在のパスワードが正しくありません")

        new_hash = generate_password_hash(new_pw, method='pbkdf2:sha256')
        cur.execute(
            "UPDATE users SET password_hash = ?, password_changed_at = datetime('now') WHERE id = ?",
            (new_hash, user["id"])
        )
        con.commit()

    return render_template('change_password.html', success="パスワードを変更しました")

# ======================================
# セッション情報取得API
# ======================================
@app.route("/api/session", methods=["GET"])
@login_required
def get_session():
    return jsonify({
        "ok": True,
        "user": {
            "id": session.get("user_id"),
            "username": session.get("username"),
            "full_name": session.get("full_name"),
            "role": session.get("role")
        }
    })

# ======================================
# ユーザー管理API（管理者のみ）
# ======================================
@app.route("/api/users", methods=["GET"])
@admin_required
def list_users():
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute("""
SELECT id, username, full_name, role, is_active, created_at, email
FROM users
ORDER BY id
        """)
        users = [dict(row) for row in cur.fetchall()]
        return jsonify({"ok": True, "users": users})

@app.route("/api/users", methods=["POST"])
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    role = data.get("role") or "user"
    email = data.get("email", "").strip()

    if not username or not password or not full_name:
        return jsonify({"ok": False, "error": "ユーザー名、パスワード、氏名は必須です"}), 400
    if len(username) < 3 or len(username) > 50:
        return jsonify({"ok": False, "error": "ユーザー名は3〜50文字にしてください"}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "パスワードは8文字以上にしてください"}), 400
    if role not in ["admin", "user"]:
        return jsonify({"ok": False, "error": "権限は admin または user を指定してください"}), 400

    password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    try:
        with DB_LOCK, db_connect() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO users (username, password_hash, full_name, role, email) VALUES (?, ?, ?, ?, ?)",
                (username, password_hash, full_name, role, email)
            )
            con.commit()
            user_id = cur.lastrowid

        return jsonify({
            "ok": True,
            "message": f"ユーザー「{full_name}」を作成しました",
            "user_id": user_id
        })
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "このユーザー名は既に使用されています"}), 400

@app.route("/api/users/<int:user_id>", methods=["PUT"])
@admin_required
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    full_name = data.get("full_name")
    role = data.get("role")
    is_active = data.get("is_active")
    new_password = data.get("new_password")
    email = data.get("email")

    updates, params = [], []

    # ユーザー名の更新処理を追加
    if username is not None:
        username = username.strip()
        if len(username) < 3 or len(username) > 50:
            return jsonify({"ok": False, "error": "ユーザー名は3〜50文字にしてください"}), 400
        
        # 重複チェック（自分以外）
        with DB_LOCK, db_connect() as con:
            cur = con.cursor()
            cur.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, user_id))
            if cur.fetchone():
                return jsonify({"ok": False, "error": "このユーザー名は既に使用されています"}), 400
        
        updates.append("username = ?")
        params.append(username)

    if full_name is not None:
        updates.append("full_name = ?")
        params.append(full_name.strip())
    if role is not None:
        if role not in ["admin", "user"]:
            return jsonify({"ok": False, "error": "権限は admin または user を指定してください"}), 400
        updates.append("role = ?")
        params.append(role)
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if is_active else 0)
    if new_password:
        if len(new_password) < 8:
            return jsonify({"ok": False, "error": "パスワードは8文字以上にしてください"}), 400
        updates.append("password_hash = ?")
        params.append(generate_password_hash(new_password, method='pbkdf2:sha256'))
    if email is not None:
        updates.append("email = ?")
        params.append(email.strip())

    if not updates:
        return jsonify({"ok": False, "error": "更新する項目がありません"}), 400

    params.append(user_id)

    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        con.commit()
        if cur.rowcount == 0:
            return jsonify({"ok": False, "error": "ユーザーが見つかりません"}), 404

    return jsonify({"ok": True, "message": "ユーザー情報を更新しました"})

@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"ok": False, "error": "自分自身を無効化することはできません"}), 400

    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        con.commit()
        if cur.rowcount == 0:
            return jsonify({"ok": False, "error": "ユーザーが見つかりません"}), 404

    return jsonify({"ok": True, "message": "ユーザーを無効化しました"})

# ======================================
# ユーザー管理ページ（管理者専用）
# ======================================
@app.route("/user_management")
@login_required
def user_management_page():
    if session.get("role") != "admin":
        return redirect(url_for("root_index"))
    return render_template("user_management.html")

# ======================================
# トップページ
# ======================================
@app.route("/")
@login_required
def root_index():
    return send_from_directory(APP_DIR, "index.html")

# ======================================
# ヘルスチェック
# ======================================
@app.route("/api/health")
def health():
    return jsonify({"ok": True, "status": "healthy"})

# ======================================
# データAPI
# ======================================
@app.route("/api/mdata/<code>", methods=["GET"])
@login_required
def api_mdata_get(code):
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute("SELECT key, value FROM hospital_data WHERE code=?", (code,))
        rows = cur.fetchall()
        if not rows:
            return jsonify({"ok": False, "error": "データが見つかりません"}), 404
        kv = {r["key"]: r["value"] for r in rows}
        return jsonify({"ok": True, "code": code, "kv": kv})

@app.route("/api/mdata/<code>", methods=["POST"])
@login_required
def api_mdata_post(code):
    data = request.get_json(silent=True) or {}
    kv = data.get("kv", {})
    user = session.get("username", "unknown")

    with DB_LOCK, db_connect() as con:
        cur = con.cursor()

        cur.execute("DELETE FROM hospital_data WHERE code=?", (code,))
        removed = cur.rowcount

        updated = 0
        insert_data = []
        for key, value in kv.items():
            if value and str(value).strip():
                insert_data.append((
                    code, key, str(value).strip(), user
                ))
                updated += 1
        
        if insert_data:
            cur.executemany(
                "INSERT INTO hospital_data (code, key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                insert_data
            )

        con.commit()
        return jsonify({"ok": True, "updated": updated, "removed": removed})

@app.route("/api/mdata/import_csv", methods=["POST"])
@login_required
def import_csv():
    file = request.files.get('file')
    if not file:
        return jsonify({"ok": False, "error": "ファイルが選択されていません"}), 400

    encodings = ["utf-8-sig", "utf-8", "cp932", "shift_jis", "iso-2022-jp"]
    content = None
    used_encoding = None

    file_bytes = file.read()
    file.close()

    for enc in encodings:
        try:
            content = file_bytes.decode(enc)
            used_encoding = enc
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        return jsonify({"ok": False, "error": "文字コードを判定できませんでした"}), 400

    try:
        sio = io.StringIO(content)
        reader = csv.reader(sio)
        rows = list(reader)

        if not rows:
            return jsonify({"ok": False, "error": "CSVが空です"}), 400

        def normalize_header(s: str) -> str:
            return (s or "").replace("\ufeff", "").replace("\u3000", " ").strip()

        headers = [normalize_header(h) for h in rows[0]]

        code_column = None
        for candidate in ['コード', '病院コード', '施設コード', 'code', 'Code', 'ID', '番号']:
            if candidate in headers:
                code_column = candidate
                break

        if not code_column:
            return jsonify({"ok": False, "error": f"コード列が見つかりません。先頭10列: {', '.join(headers[:10])}"}), 400

        imported = 0
        skipped = 0
        errors = []

        BASIC_FIELDS = ['コード', '都道府県', '病院名', '郵便番号', '住所', '最寄駅', 'TEL', 'DI', 'ファミレス']
        SERIES_HEADS = [
            '印', '卒業', 'Dr./出身大学', '診療科', 'PHS', '直PHS', '①', '②', '備考',
            '関連病院施設等', '関連病院TEL', '関連病院備考',
            '部署', '業者', '内線', 'TEL・メモ'
        ]

        with DB_LOCK, db_connect() as con:
            cur = con.cursor()

            for row_index, row in enumerate(rows[1:], 1):
                try:
                    row_dict = {headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))}

                    code = row_dict.get(code_column, '').strip()
                    code = code.replace("\ufeff", "").replace("\u200b", "")
                    if code.startswith("'"):
                        code = code[1:]
                    code = code.strip()

                    if not code:
                        skipped += 1
                        continue
                    
                    cur.execute("DELETE FROM hospital_data WHERE code=?", (code,))

                    insert_data = []
                    
                    for field in BASIC_FIELDS:
                        value = row_dict.get(field, '').strip()
                        if value and value.lower() != 'nan':
                            insert_data.append((code, field, value, session.get("username")))

                    for head in SERIES_HEADS:
                        if head in row_dict:
                            value = row_dict[head].strip()
                            if value and value.lower() != 'nan':
                                insert_data.append((code, head, value, session.get("username")))
                        
                        pattern = re.compile(rf'^{re.escape(head)}_(\d+)$')
                        for key in headers:
                            match = pattern.match(key)
                            if match:
                                value = row_dict.get(key, '').strip()
                                if value and value.lower() != 'nan':
                                    insert_data.append((code, key, value, session.get("username")))
                    
                    if insert_data:
                        cur.executemany(
                            "INSERT OR REPLACE INTO hospital_data (code, key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                            insert_data
                        )
                    
                    imported += 1

                except Exception as e:
                    errors.append(f'Row {row_index}: {str(e)}')
                    if len(errors) > 20:
                        break
            
            con.commit()

        return jsonify({
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "total_errors": len(errors),
            "encoding_used": used_encoding,
            "code_column": code_column,
            "warnings": errors[:5] if errors else []
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/mdata/search", methods=["GET"])
@login_required
def search_mdata():
    prefix = request.args.get('prefix', '')
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        query = """
SELECT DISTINCT code,
       (SELECT value FROM hospital_data h2 WHERE h2.code = h1.code AND h2.key = '病院名' LIMIT 1) as hospital
FROM hospital_data h1
        """

        if prefix:
            query += " WHERE code LIKE ? ORDER BY code"
            cur.execute(query, (prefix + '%',))
        else:
            query += " ORDER BY code"
            cur.execute(query)

        rows = cur.fetchall()
        items = [{"code": r["code"], "hospital": r["hospital"] or ""} for r in rows]
        return jsonify({"ok": True, "items": items})

# ======================================
# ロック管理
# ======================================
active_locks = {}
LOCK_TIMEOUT = 30 * 60

def cleanup_expired_locks():
    current_time = time.time()
    expired_codes = []
    for code, lock in list(active_locks.items()):
        locked_at = lock.get('locked_at', 0)
        if locked_at and (current_time - locked_at) > LOCK_TIMEOUT:
            expired_codes.append(code)

    for code in expired_codes:
        if code in active_locks:
            del active_locks[code]
            socketio.emit('lock_released', {'code': code})

    return len(expired_codes)

@app.route("/api/lock/status", methods=["GET"])
def lock_status():
    cleanup_expired_locks()
    locks_data = {}
    for code, lock_info in active_locks.items():
        locks_data[code] = {
            'user_id': lock_info['user_id'],
            'username': lock_info['username'],
            'locked_at': lock_info.get('locked_at')
        }
    return jsonify({"ok": True, "locks": locks_data})

@app.route("/api/lock/acquire", methods=["POST"])
def lock_acquire():
    try:
        cleanup_expired_locks()

        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"ok": False, "error": "不正なリクエストボディ"}), 400

        code = data.get('code')
        user_id = session.get('user_id')
        username = session.get('username', 'Unknown')

        if not code or not user_id:
            return jsonify({"ok": False, "error": "コードとユーザーIDが必要です"}), 400

        # このユーザーが既に他の病院をロックしていないかチェック
        for locked_code, lock_info in active_locks.items():
            if lock_info['user_id'] == user_id and locked_code != code:
                return jsonify({"ok": False, "error": "既に別の病院をロックしています"}), 400

        existing_lock = active_locks.get(code)
        if existing_lock and existing_lock['user_id'] != user_id:
            return jsonify({
                "ok": False,
                "error": f"このコードは{existing_lock['username']}が使用中です",
                "locked_by": existing_lock['username']
            }), 409

        active_locks[code] = {
            'user_id': user_id,
            'username': username,
            'locked_at': time.time()
        }

        socketio.emit('lock_acquired', {
            'code': code,
            'user': {
                'user_id': user_id,
                'username': username,
                'locked_at': time.time()
            }
        })

        return jsonify({"ok": True, "message": "ロックを取得しました"})

    except Exception as e:
        print(f"❌ lock_acquire エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": "サーバー内部エラー"}), 500

@app.route("/api/lock/release", methods=["POST"])
def lock_release():
    try:
        data = request.get_json(silent=True) or {}
        code = data.get('code')
        user_id = session.get('user_id')

        if not code:
            return jsonify({"ok": False, "error": "コードが必要です"}), 400

        existing_lock = active_locks.get(code)

        if existing_lock:
            lock_owner = existing_lock.get('user_id')
            if lock_owner == user_id:
                del active_locks[code]
                socketio.emit('lock_released', {'code': code})
                return jsonify({"ok": True, "message": "ロックを解放しました"})
            else:
                return jsonify({"ok": False, "error": "権限がありません"}), 403
        else:
            return jsonify({"ok": True, "message": "ロックは既に解放されています"})

    except Exception as e:
        print(f"❌ ロック解放エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/lock/heartbeat", methods=["POST"])
def lock_heartbeat():
    data = request.get_json(silent=True) or {}
    code = data.get('code')
    user_id = session.get('user_id')

    if not code or not user_id:
        return jsonify({"ok": False, "error": "コードとユーザーIDが必要です"}), 400

    existing_lock = active_locks.get(code)
    if existing_lock and existing_lock['user_id'] == user_id:
        existing_lock['locked_at'] = time.time()
        return jsonify({"ok": True, "message": "ハートビート更新"})

    return jsonify({"ok": False, "error": "ロックが見つかりません"}), 404

# ======================================
# Socket.IOイベントハンドラ
# ======================================
@socketio.on('connect')
def handle_connect():
    if session.get("user_id"):
        cleanup_expired_locks()
        locks_data = {}
        for code, lock_info in active_locks.items():
            locks_data[code] = {
                'user_id': lock_info['user_id'],
                'username': lock_info['username'],
                'locked_at': lock_info.get('locked_at')
            }
        socketio.emit('lock_status_update', {'locks': locks_data}, room=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    pass

# ======================================
# 静的ファイル配信
# ======================================
@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(APP_DIR, 'css'), filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(APP_DIR, 'js'), filename)

# ======================================
# アプリ起動
# ======================================
if __name__ == "__main__":
    is_dev = os.environ.get("FLASK_ENV") == "development"
    if is_dev:
        app.config.update(SESSION_COOKIE_SECURE=False)
    else:
        app.config.update(SESSION_COOKIE_SECURE=True)

    print("=" * 60)
    print("🏥 病院情報管理システム サーバー起動中...")
    print(f"📍 ログインURL: {BASE_URL}/login")
    print(f"💾 データベース: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print("\n💡 データベースファイルが存在しません。")
        print("   初回起動時は以下のコマンドを実行してください:")
        print("   > flask init-db")
        print("   > python setup_users.py")
    
    print("=" * 60)

    debug_mode = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    socketio.run(app, host="0.0.0.0", port=5000, debug=debug_mode, allow_unsafe_werkzeug=True)