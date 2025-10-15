# backup_db.py
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# ====== 設定 ======
PROJECT_DIR = Path(r"C:\Projects\hospital-transfer-ui")
DB_PATH     = PROJECT_DIR / "hospital_data.sqlite3"
BACKUP_DIR  = PROJECT_DIR / "backup"
# 何時間より古いバックアップを自動削除するか（例: 72 = 3日保管）
RETENTION_HOURS = 72
# ==================

def backup_sqlite(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = dst_dir / f"hospital_data_{ts}.sqlite3"

    # SQLite のオンラインバックアップAPIで整合性あるコピーを作成
    with sqlite3.connect(src) as src_con, sqlite3.connect(dst) as dst_con:
        src_con.backup(dst_con)  # DB使用中でも安全にスナップショット取得
    return dst

def rotate_old_backups(dst_dir: Path, retention_hours: int) -> int:
    cutoff = datetime.now() - timedelta(hours=retention_hours)
    removed = 0
    for p in dst_dir.glob("hospital_data_*.sqlite3"):
        if datetime.fromtimestamp(p.stat().st_mtime) < cutoff:
            try:
                p.unlink()
                removed += 1
            except Exception:
                pass
    return removed

def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DBが見つかりません: {DB_PATH}")

    out = backup_sqlite(DB_PATH, BACKUP_DIR)
    removed = rotate_old_backups(BACKUP_DIR, RETENTION_HOURS)
    print(f"[OK] Backup: {out}")
    if removed:
        print(f"[INFO] 古いバックアップを {removed} 件削除しました（保持: {RETENTION_HOURS} 時間）")

if __name__ == "__main__":
    main()
