#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import io
import csv
import re
import json
import sqlite3
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ======================================
# 設定
# ======================================
APP_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(APP_DIR, "hospital_data.sqlite3")

app = Flask(__name__, static_folder=APP_DIR)
app.config["SECRET_KEY"] = "hospital-management-secret-key-2024"
CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)

DB_LOCK = threading.Lock()

# ======================================
# データベース
# ======================================
def db_connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    with DB_LOCK:
        conn = db_connect()
        cur = conn.cursor()

        # メインデータ
        cur.execute('''
            CREATE TABLE IF NOT EXISTS hospital_records (
                code TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                row_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT
            )
        ''')

        # 互換用（未使用）
        cur.execute('''
            CREATE TABLE IF NOT EXISTS editing_status (
                hospital_code TEXT,
                cell_id TEXT,
                user_id TEXT,
                username TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (hospital_code, cell_id)
            )
        ''')

        # レコードロック
        cur.execute('''
            CREATE TABLE IF NOT EXISTS record_locks (
                code TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT,
                session_id TEXT,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_record_locks_user ON record_locks (user_id)')

        # 検索用
        cur.execute('CREATE INDEX IF NOT EXISTS idx_code ON hospital_records (code)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_row_index ON hospital_records (row_index)')

        conn.commit()
        conn.close()

def get_hospital_data(code: str) -> Optional[Dict[str, Any]]:
    with DB_LOCK:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute('SELECT data, row_index FROM hospital_records WHERE code = ?', (code,))
        row = cur.fetchone()
        conn.close()
        if row:
            try:
                data = json.loads(row['data'])
                data['_row_index'] = row['row_index']
                return data
            except json.JSONDecodeError:
                return None
        return None

def save_hospital_data(code: str, data: Dict[str, Any], user_id: str = 'unknown', row_index: int = 0) -> bool:
    with DB_LOCK:
        conn = db_connect()
        cur = conn.cursor()
        clean = {k: v for k, v in data.items() if k != '_row_index'}
        cur.execute('''
            INSERT OR REPLACE INTO hospital_records
            (code, data, row_index, updated_at, updated_by)
            VALUES (?, ?, ?, datetime('now'), ?)
        ''', (code, json.dumps(clean, ensure_ascii=False), row_index, user_id))
        conn.commit()
        conn.close()
        return True

def search_hospitals(prefix: str = None, q: str = None, limit: int = 200) -> List[Dict[str, str]]:
    with DB_LOCK:
        conn = db_connect()
        cur = conn.cursor()
        if prefix:
            cur.execute('''
                SELECT code, data FROM hospital_records
                WHERE code LIKE ?
                ORDER BY row_index ASC, code ASC
                LIMIT ?
            ''', (f"{prefix}%", limit))
        else:
            cur.execute('''
                SELECT code, data FROM hospital_records
                ORDER BY row_index ASC, code ASC
                LIMIT ?
            ''', (limit,))
        rows = cur.fetchall()
        conn.close()

        results = []
        for row in rows:
            code = row['code']
            try:
                data = json.loads(row['data'])
                hospital = data.get('病院名', data.get('施設名', ''))
                if q and (q not in code and (not hospital or q not in hospital)):
                    continue
                results.append({'code': code, 'hospital': hospital})
            except json.JSONDecodeError:
                continue
        return results[:limit]

# ========== ユーティリティ ==========
def normalize_header(s: str) -> str:
    return (s or "").replace("\ufeff", "").replace("\u3000", " ").strip()

def normalize_code(val: str) -> str:
    s = (val or "")
    s = s.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    s = s.strip()
    if s.startswith("'"):
        s = s[1:]
    return s.strip()

# 取り込み時のキー名（UI側と完全一致）
BASIC_FIELDS = ['コード', '都道府県', '病院名', '郵便番号', '住所', '最寄駅', 'TEL', 'DI', 'ファミレス']
SERIES_HEADS = [
    # 病院情報リスト 9列
    '印', '卒業', 'Dr./出身大学', '診療科', 'PHS', '直PHS', '①', '②', '備考',
    # 関連施設
    '関連病院施設等', '関連病院TEL', '関連病院備考',
    # 業者・部署
    '部署', '業者', '内線', 'TEL・メモ'
]

_series_re_cache: Dict[str, re.Pattern] = {}
def _series_re(head: str) -> re.Pattern:
    if head not in _series_re_cache:
        _series_re_cache[head] = re.compile(rf'^{re.escape(head)}_(\d+)$')
    return _series_re_cache[head]

def map_csv_to_ui_format(csv_row_raw: Dict[str, str]) -> Dict[str, str]:
    """
    1行分のCSVをUI保存形式へ。
    - ヘッダーは正規化してから使用
    - 可変列（XXX_1, XXX_2, ...）は上限なしで拾う
    """
    # ヘッダー正規化
    row = { normalize_header(k): (v if v is not None else '') for k, v in csv_row_raw.items() }

    ui: Dict[str, str] = {}
    for f in BASIC_FIELDS:
        ui[f] = row.get(f, '')

    # まずは完全一致（_n が付かない）もコピーしておく（例: 旧CSVに「状況1」等が単体である場合の保険）
    for head in SERIES_HEADS:
        if head in row:
            ui[head] = row[head]

    # 可変列を総なめ
    for head in SERIES_HEADS:
        pat = _series_re(head)
        for key, val in row.items():
            m = pat.match(key)
            if m:
                ui[f"{head}_{m.group(1)}"] = val

    return ui

# ======================================
# Web ルート
# ======================================
@app.route("/")
def root_index():
    return send_from_directory(APP_DIR, "index.html")

@app.route("/favicon.ico")
def favicon():
    return Response(status=204)

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "status": "running", "timestamp": datetime.now().isoformat()})

# ---------- CSV インポート ----------
@app.route("/api/mdata/import_csv", methods=["POST"])
def import_csv():
    file = request.files.get("file")
    if not file:
        return jsonify({"ok": False, "error": "ファイルが選択されていません"}), 400

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
        # DictReaderのヘッダーを正規化したいので、手動でフィールド名を置換
        sio = io.StringIO(content)
        reader = csv.reader(sio)
        rows = list(reader)
        if not rows:
            return jsonify({"ok": False, "error": "CSVが空です"}), 400

        headers = [normalize_header(h) for h in rows[0]]
        dict_rows = [ { headers[i]: (r[i] if i < len(r) else '') for i in range(len(headers)) } for r in rows[1:] ]

        # コード列の特定
        code_column = None
        for cand in ['コード', '病院コード', '施設コード', 'code', 'Code', 'ID', '番号']:
            if cand in headers:
                code_column = cand
                break
        if not code_column:
            return jsonify({"ok": False, "error": f"コード列が見つかりません。先頭10列: {', '.join(headers[:10])}"}), 400

        imported, skipped = 0, 0
        errors = []
        for row_index, row in enumerate(dict_rows, 1):
            try:
                code = normalize_code(row.get(code_column, ''))
                if not code:
                    skipped += 1
                    continue
                ui_data = map_csv_to_ui_format(row)
                if save_hospital_data(code, ui_data, 'csv_import', row_index):
                    imported += 1
                else:
                    errors.append(f'Row {row_index}: 保存に失敗')
            except Exception as e:
                errors.append(f'Row {row_index}: {str(e)}')
                if len(errors) > 20:
                    break

        return jsonify({
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "total_errors": len(errors),
            "encoding_used": used_encoding,
            "code_column": code_column,
            "warnings": errors[:5]
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- データ取得/保存 ----------
@app.route("/api/mdata/<code>", methods=["GET"])
def get_hospital(code):
    code = normalize_code(code)
    data = get_hospital_data(code)
    if data is None:
        return jsonify({"ok": False, "error": "データが見つかりません"}), 404
    return jsonify({"ok": True, "code": code, "kv": data})

@app.route("/api/mdata/<code>", methods=["POST"])
def save_hospital(code):
    code = normalize_code(code)
    req = request.get_json(silent=True) or {}
    data = req.get("kv", {})
    user_id = req.get("user", "unknown")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "データが正しくありません"}), 400

    # ローカル開発中はロックチェックを無効化
    # # 保存前にロック確認
    # with DB_LOCK:
    #     conn = db_connect()
    #     cur = conn.cursor()
    #     cur.execute("SELECT user_id FROM record_locks WHERE code = ?", (code,))
    #     row = cur.fetchone()
    #     conn.close()
    #     if row and row["user_id"] != user_id:
    #         return jsonify({"ok": False, "error": "編集中のため保存できません（他ユーザーがロック中）"}), 423

    try:
        existing = get_hospital_data(code) or {}
        # ...以下省略
        row_index = existing.get('_row_index', 0)
        updated = 0
        removed = 0
        for k, v in data.items():
            if k.startswith('_'):
                continue
            old = existing.get(k, '')
            if isinstance(v, str) and v.strip() == '':
                if old:
                    removed += 1
            elif old != v:
                updated += 1
        if save_hospital_data(code, data, user_id, row_index):
            return jsonify({"ok": True, "updated": updated, "removed": removed,
                            "total_keys": len([k for k in data.keys() if not k.startswith('_')])})
        else:
            return jsonify({"ok": False, "error": "保存に失敗しました"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/mdata/search")
def search_codes():
    prefix = request.args.get("prefix")
    q = request.args.get("q")
    try:
        limit = int(request.args.get("limit", 200))
    except ValueError:
        limit = 200
    results = search_hospitals(prefix, q, limit)
    return jsonify({"ok": True, "items": results})

# ======================================
# レコードロック API
# ======================================
def acquire_record_lock(code: str, user_id: str, username: str, session_id: str):
    with DB_LOCK:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT user_id, username FROM record_locks WHERE code = ?", (code,))
        row = cur.fetchone()
        if row:
            if row["user_id"] == user_id:
                cur.execute("UPDATE record_locks SET locked_at = datetime('now'), session_id=? WHERE code=?",
                            (session_id, code))
                conn.commit()
                conn.close()
                return True, {"user_id": user_id, "username": username}
            else:
                owner = {"user_id": row["user_id"], "username": row["username"]}
                conn.close()
                return False, owner
        cur.execute("INSERT INTO record_locks (code, user_id, username, session_id) VALUES (?, ?, ?, ?)",
                    (code, user_id, username, session_id))
        conn.commit()
        conn.close()
        return True, {"user_id": user_id, "username": username}

def release_record_lock(code: str, user_id: str = None, session_id: str = None):
    with DB_LOCK:
        conn = db_connect()
        cur = conn.cursor()
        if user_id:
            cur.execute("DELETE FROM record_locks WHERE code=? AND user_id=?", (code, user_id))
        elif session_id:
            cur.execute("DELETE FROM record_locks WHERE code=? AND session_id=?", (code, session_id))
        else:
            conn.close()
            return 0
        count = cur.rowcount
        conn.commit()
        conn.close()
        return count

def release_all_locks_by_session(session_id: str):
    with DB_LOCK:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT code FROM record_locks WHERE session_id=?", (session_id,))
        codes = [r["code"] for r in cur.fetchall()]
        cur.execute("DELETE FROM record_locks WHERE session_id=?", (session_id,))
        count = cur.rowcount
        conn.commit()
        conn.close()
        return codes, count

@app.route("/api/lock/acquire", methods=["POST"])
def api_lock_acquire():
    data = request.get_json(silent=True) or {}
    code = normalize_code(data.get("code", ""))
    user_id = data.get("user_id") or "unknown"
    username = data.get("username") or user_id
    session_id = data.get("session_id") or request.headers.get("X-Session-ID") or "api"

    if not code:
        return jsonify({"ok": False, "error": "code が必要です"}), 400

    ok, owner = acquire_record_lock(code, user_id, username, session_id)
    if ok:
        socketio.emit("lock_acquired", {"code": code, "user": owner})
        return jsonify({"ok": True, "code": code, "owner": owner})
    else:
        return jsonify({"ok": False, "locked": True, "code": code, "owner": owner}), 423

@app.route("/api/lock/release", methods=["POST"])
def api_lock_release():
    data = request.get_json(silent=True) or {}
    code = normalize_code(data.get("code", ""))
    user_id = data.get("user_id")
    session_id = data.get("session_id")
    if not code:
        return jsonify({"ok": False, "error": "code が必要です"}), 400

    count = release_record_lock(code, user_id=user_id, session_id=session_id)
    if count > 0:
        socketio.emit("lock_released", {"code": code})
        return jsonify({"ok": True, "released": count})
    else:
        return jsonify({"ok": False, "released": 0})

@app.route("/api/lock/status")
def api_lock_status():
    with DB_LOCK:
        conn = db_connect()
        cur = conn.cursor()
        cur.execute("SELECT code, user_id, username FROM record_locks")
        rows = cur.fetchall()
        conn.close()
    return jsonify({"ok": True, "locks": {r["code"]: {"user_id": r["user_id"], "username": r["username"]} for r in rows}})

# ======================================
# Socket.IO（オンライン・ロック管理）
# ======================================
online_users = {}  # session_id -> user_info

@socketio.on("connect")
def on_connect():
    emit("connection_status", {"status": "connected"})

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    if sid in online_users:
        user_info = online_users[sid]
        del online_users[sid]
        emit("user_left", {"user": user_info}, broadcast=True, include_self=False)
        emit("users_update", {"users": list(online_users.values())}, broadcast=True)
    # セッション切断でロック自動解放
    codes, _ = release_all_locks_by_session(sid)
    for c in codes:
        socketio.emit("lock_released", {"code": c})

@socketio.on("user_join")
def on_user_join(data):
    sid = request.sid
    user_id = data.get("user_id", f"user_{sid[:8]}")
    username = data.get("username", user_id)
    online_users[sid] = {
        "user_id": user_id,
        "username": username,
        "session_id": sid,
        "joined_at": datetime.now().isoformat()
    }
    emit("user_joined", {"user": online_users[sid]})
    emit("users_update", {"users": list(online_users.values())}, broadcast=True)

# ================================
# メイン
# ================================
import eventlet
eventlet.monkey_patch()   # 追加 (必須)

if __name__ == "__main__":
    print("=" * 60)
    print(" 🏥 病院情報管理システム サーバー起動中...")
    print(f"📂 データベース: {DB_PATH}")
    print(f"📂 静的ファイル: {APP_DIR}")
    print("=" * 60)

    try:
        db_init()
        print("✅ データベース初期化完了")
    except Exception as e:
        print(f"❌ データベース初期化エラー: {e}")
        exit(1)

    print("🚀 サーバー起動: http://0.0.0.0:5000")
    print("=" * 60)

    # eventlet を使って安定稼働
    socketio.run(app, host="0.0.0.0", port=5000)

