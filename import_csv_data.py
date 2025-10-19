import sqlite3
import json
import csv
import codecs

def import_csv_to_database(csv_filename, db_filename='hospital_data.sqlite3'):
    """
    CSVファイルからデータベースにデータをインポート（改良版）
    """
    print(f'📂 CSVファイルを読み込んでいます: {csv_filename}')
    
    # BOM付きUTF-8で開く
    with codecs.open(csv_filename, 'r', 'utf-8-sig') as f:
        # 区切り文字を自動検出
        sample = f.read(1024)
        f.seek(0)
        
        # Papaparseのように柔軟に区切り文字を検出
        dialect = csv.Sniffer().sniff(sample, delimiters=',\t;')
        reader = csv.DictReader(f, dialect=dialect)
        
        # ヘッダーから余分な空白を削除
        reader.fieldnames = [field.strip() for field in reader.fieldnames]
        
        print(f'📋 検出されたカラム: {reader.fieldnames[:5]}...')
        
        rows = list(reader)
    
    print(f'✅ {len(rows)}件のデータを読み込みました')
    
    # データベースに接続
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    
    # 既存のデータを削除
    print('🗑️  既存のデータを削除しています...')
    cursor.execute('DELETE FROM mdata')
    
    # データをインポート
    print('📥 データベースにインポート中...')
    imported_count = 0
    skipped_count = 0
    
    for idx, row in enumerate(rows):
        # ヘッダー名の候補を試す
        code = None
        for key in ['コード', 'code', 'Code', 'CODE']:
            if key in row:
                # ★修正箇所：先頭のシングルクォート（'）を削除
                code = str(row[key]).strip().lstrip("'")
                break
        
        # コードが空の行はスキップ
        if not code:
            skipped_count += 1
            if idx < 3:  # 最初の3行だけデバッグ情報を表示
                print(f'⚠️  スキップ（行{idx+1}）: コードが見つかりません。利用可能なキー: {list(row.keys())[:5]}')
            continue
        
        # JSON形式で保存するデータを準備
        kv_data = {}
        for key, value in row.items():
            # 空の値はスキップ
            if value and str(value).strip():
                # ★追加：全ての値からも先頭のシングルクォートを削除
                cleaned_value = str(value).strip().lstrip("'")
                kv_data[key.strip()] = cleaned_value
        
        # JSONに変換
        kv_json = json.dumps(kv_data, ensure_ascii=False)
        
        # データベースに挿入
        try:
            cursor.execute(
                'INSERT OR REPLACE INTO mdata (code, kv) VALUES (?, ?)',
                (code, kv_json)
            )
            imported_count += 1
            
            # 進捗表示（100件ごと）
            if imported_count % 100 == 0:
                print(f'  ... {imported_count}件インポート完了')
                
        except Exception as e:
            print(f'❌ エラー（コード: {code}）: {e}')
            skipped_count += 1
    
    # コミット
    conn.commit()
    
    # 結果を表示
    print('\n' + '='*50)
    print(f'✅ インポート完了!')
    print(f'📊 インポート件数: {imported_count}件')
    print(f'⚠️  スキップ件数: {skipped_count}件')
    print('='*50)
    
    if imported_count > 0:
        # サンプルデータを表示
        print('\n📋 インポートされたデータの例（最初の3件）:')
        cursor.execute('SELECT code, kv FROM mdata LIMIT 3')
        for code, kv in cursor.fetchall():
            data = json.loads(kv)
            print(f'\n🏥 コード: {code}')
            print(f'   病院名: {data.get("病院名", "N/A")}')
            print(f'   都道府県: {data.get("都道府県", "N/A")}')
        
        # 都道府県コードの確認
        print('\n📊 都道府県コードの確認（最初の10件）:')
        cursor.execute('SELECT DISTINCT substr(code, 1, 2) as pref FROM mdata ORDER BY pref LIMIT 10')
        for row in cursor.fetchall():
            print(f'   都道府県コード: {row[0]}')
    
    conn.close()
    print('\n🎉 全ての処理が完了しました!')

if __name__ == '__main__':
    csv_filename = 'csv研修医有1072×837 .csv'
    
    try:
        import_csv_to_database(csv_filename)
    except Exception as e:
        print(f'❌ エラーが発生しました: {e}')
        import traceback
        traceback.print_exc()