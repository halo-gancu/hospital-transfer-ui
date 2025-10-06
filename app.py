#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import io
import csv
import re
import json
import sqlite3
import threading
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from flask import (
    Flask, request, jsonify, send_from_directory,
    session, redirect, url_for, render_template
)
from flask_cors import CORS
from flask_socketio import SocketIO
from werkzeug.security import generate_password_hash, check_password_hash

# ======================================
# 設定
# ======================================
APP_DIR  = os.path.abspath(os.path.dirname(__file__))
DB_PATH  = os.path.join(APP_DIR, "hospital_data.sqlite3")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "super-secret-key-change-in-production")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DB_LOCK = threading.Lock()

# ======================================
# DB ヘルパー
# ======================================
def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

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
def find_user_by_userid(user_id: str):
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=? LIMIT 1", (user_id,))
        return cur.fetchone()

def verify_login(user_id: str, password: str) -> bool:
    u = find_user_by_userid(user_id)
    if not u:
        return False
    return check_password_hash(u["password_hash"], password)

# ======================================
# レート制限（簡易版）
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
@app.route("/login", methods=["GET"])
def login_page():
    if session.get("uid"):
        return redirect(url_for("root_index"))
    token = issue_csrf_token()
    return render_template("login.html", csrf_token=token)

@app.route("/api/login", methods=["POST"])
def api_login():
    locked = _rate_limit_check()
    if locked:
        return jsonify({"ok": False, "error": locked}), 429

    data = request.get_json(silent=True) or {}
    user = (data.get("user") or "").strip()
    pw   = (data.get("pw") or "")
    csrf = data.get("csrf") or ""

    if not require_csrf(csrf):
        return jsonify({"ok": False, "error": "CSRF検証に失敗しました"}), 400

    if not (1 <= len(user) <= 64) or not all(c.isalnum() or c in "-_." for c in user):
        _rate_limit_fail()
        return jsonify({"ok": False, "error": "ユーザーIDまたはパスワードが不正です"}), 400

    if not (6 <= len(pw) <= 256):
        _rate_limit_fail()
        return jsonify({"ok": False, "error": "ユーザーIDまたはパスワードが不正です"}), 400

    if verify_login(user, pw):
        _rate_limit_success()
        u = find_user_by_userid(user)
        if not u or not u["is_active"]:
            return jsonify({"ok": False, "error": "アカウントが無効です"}), 403

        session.clear()
        session["uid"]  = u["user_id"]
        session["role"] = u["role"]
        session["csrf_token"] = issue_csrf_token()

        return jsonify({"ok": True, "user_id": u["user_id"], "role": u["role"]})
    else:
        _rate_limit_fail()
        return jsonify({"ok": False, "error": "ユーザーIDまたはパスワードが不正です"}), 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# ======================================
# トップページ
# ======================================
@app.route("/")
def root_index():
    if not session.get("uid"):
        return redirect(url_for("login_page"))
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
def api_mdata_get(code):
    if not session.get("uid"):
        return jsonify({"ok": False, "error": "未認証"}), 401
    
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        cur.execute("SELECT key, value FROM hospital_data WHERE code=?", (code,))
        rows = cur.fetchall()
        
        if not rows:
            return jsonify({"ok": False, "error": "データが見つかりません"}), 404
        
        kv = {r["key"]: r["value"] for r in rows}
        return jsonify({"ok": True, "code": code, "kv": kv})

@app.route("/api/mdata/<code>", methods=["POST"])
def api_mdata_post(code):
    if not session.get("uid"):
        return jsonify({"ok": False, "error": "未認証"}), 401
    
    data = request.get_json(silent=True) or {}
    kv = data.get("kv", {})
    user = data.get("user") or session.get("uid")
    
    with DB_LOCK, db_connect() as con:
        cur = con.cursor()
        
        # 既存データを削除
        cur.execute("DELETE FROM hospital_data WHERE code=?", (code,))
        removed = cur.rowcount
        
        # 新しいデータを挿入
        updated = 0
        for key, value in kv.items():
            if value and str(value).strip():
                cur.execute(
                    "INSERT INTO hospital_data (code, key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                    (code, key, str(value).strip(), user)
                )
                updated += 1
        
        con.commit()
        return jsonify({"ok": True, "updated": updated, "removed": removed})

@app.route("/api/mdata/import_csv", methods=["POST"])
def import_csv():
    if not session.get("uid"):
        return jsonify({"ok": False, "error": "未認証"}), 401
    
    file = request.files.get('file')
    if not file:
        return jsonify({"ok": False, "error": "ファイルが選択されていません"}), 400
    
    # エンコーディング自動判定
    encodings = ["utf-8-sig", "utf-8", "cp932", "shift_jis", "iso-2022-jp"]
    content = None
    used_encoding = None
    
    for enc in encodings:
        try:
            file.stream.seek(0)
            content = file.stream.read().decode(enc)
            used_encoding = enc
            break
        except UnicodeDecodeError:
            continue
    
    if content is None:
        return jsonify({"ok": False, "error": "文字コードを判定できませんでした"}), 400
    
    try:
        # CSV解析
        sio = io.StringIO(content)
        reader = csv.reader(sio)
        rows = list(reader)
        
        if not rows:
            return jsonify({"ok": False, "error": "CSVが空です"}), 400
        
        # ヘッダー正規化
        def normalize_header(s):
            return (s or "").replace("\ufeff", "").replace("\u3000", " ").strip()
        
        headers = [normalize_header(h) for h in rows[0]]
        
        # コード列を自動検出
        code_column = None
        for candidate in ['コード', '病院コード', '施設コード', 'code', 'Code', 'ID', '番号']:
            if candidate in headers:
                code_column = candidate
                break
        
        if not code_column:
            return jsonify({"ok": False, "error": f"コード列が見つかりません。先頭10列: {', '.join(headers[:10])}"}), 400
        
        # データ処理
        imported = 0
        skipped = 0
        errors = []
        
        # 基本フィールド
        BASIC_FIELDS = ['コード', '都道府県', '病院名', '郵便番号', '住所', '最寄駅', 'TEL', 'DI', 'ファミレス']
        
        # シリーズフィールド（_1, _2, ...付き）
        SERIES_HEADS = [
            '印', '卒業', 'Dr./出身大学', '診療科', 'PHS', '直PHS', '①', '②', '備考',
            '関連病院施設等', '関連病院TEL', '関連病院備考',
            '部署', '業者', '内線', 'TEL・メモ'
        ]
        
        with DB_LOCK, db_connect() as con:
            cur = con.cursor()
            
            for row_index, row in enumerate(rows[1:], 1):
                try:
                    # 行をdict化
                    row_dict = {headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))}
                    
                    # コード取得・正規化
                    code = row_dict.get(code_column, '').strip()
                    code = code.replace("\ufeff", "").replace("\u200b", "")
                    if code.startswith("'"):
                        code = code[1:]
                    code = code.strip()
                    
                    if not code:
                        skipped += 1
                        continue
                    
                    # 基本フィールド保存
                    for field in BASIC_FIELDS:
                        value = row_dict.get(field, '').strip()
                        if value:
                            cur.execute(
                                "INSERT OR REPLACE INTO hospital_data (code, key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                                (code, field, value, session.get("uid"))
                            )
                    
                    # シリーズフィールド保存（_1, _2, ... を動的に検出）
                    for head in SERIES_HEADS:
                        # 完全一致（_なし）
                        if head in row_dict:
                            value = row_dict[head].strip()
                            if value and value.lower() != 'nan':
                                cur.execute(
                                    "INSERT OR REPLACE INTO hospital_data (code, key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                                    (code, head, value, session.get("uid"))
                                )
                        
                        # パターンマッチ（head_数字）
                        pattern = re.compile(rf'^{re.escape(head)}_(\d+)$')
                        for key in headers:
                            match = pattern.match(key)
                            if match:
                                value = row_dict.get(key, '').strip()
                                if value and value.lower() != 'nan':
                                    cur.execute(
                                        "INSERT OR REPLACE INTO hospital_data (code, key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                                        (code, key, value, session.get("uid"))
                                    )
                    
                    # 状況1→①, 状況2→②のマッピング
                    for i in range(1, 100):
                        for old, new in [('状況1', '①'), ('状況2', '②')]:
                            old_key = f'{old}_{i}'
                            if old_key in row_dict:
                                value = row_dict[old_key].strip()
                                if value and value.lower() != 'nan':
                                    cur.execute(
                                        "INSERT OR REPLACE INTO hospital_data (code, key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                                        (code, f'{new}_{i}', value, session.get("uid"))
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
def search_mdata():
    if not session.get("uid"):
        return jsonify({"ok": False, "error": "未認証"}), 401
    
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
# ロックAPI（スタブ）
# ======================================
@app.route("/api/lock/status", methods=["GET"])
def lock_status():
    return jsonify({"ok": True, "locks": {}})

@app.route("/api/lock/acquire", methods=["POST"])
def lock_acquire():
    return jsonify({"ok": True})

@app.route("/api/lock/release", methods=["POST"])
def lock_release():
    return jsonify({"ok": True})

@app.route("/api/lock/heartbeat", methods=["POST"])
def lock_heartbeat():
    return jsonify({"ok": True})

@app.route("/api/lock/force_release", methods=["POST"])
def lock_force_release():
    return jsonify({"ok": True})

# ======================================
# メイン
# ======================================
if __name__ == "__main__":
    dev_no_https = os.environ.get("DEV_NO_HTTPS", "1")
    if dev_no_https:
        app.config.update(SESSION_COOKIE_SECURE=False)
    else:
        app.config.update(SESSION_COOKIE_SECURE=True)

    print("=" * 50)
    print("病院情報管理システム サーバー起動中...")
    print(f"ログインURL: http://localhost:5000/login")
    print(f"データベース: {DB_PATH}")
    print("=" * 50)
    
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)