import csv

csv_filename = 'csv研修医有1072×837 .csv'

print('='*60)
print('📊 CSVファイルの詳細分析')
print('='*60)

# エンコーディングを試す
encodings = ['utf-8', 'utf-8-sig', 'shift_jis', 'cp932']

for encoding in encodings:
    try:
        print(f'\n🔍 {encoding} で読み込み中...')
        with open(csv_filename, 'r', encoding=encoding) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        print(f'✅ 成功！')
        print(f'📊 読み込んだ行数: {len(rows)}行')
        print(f'📋 カラム数: {len(reader.fieldnames)}列')
        
        # 最初の5行のコードを表示
        print(f'\n📝 最初の5行の「コード」列:')
        for i, row in enumerate(rows[:5]):
            code = row.get('コード', '')
            print(f'  {i+1}. コード: [{code}] (長さ: {len(code)})')
            if code:
                print(f'     病院名: {row.get("病院名", "N/A")}')
        
        # コードが空白の行を数える
        empty_codes = sum(1 for row in rows if not row.get('コード', '').strip())
        print(f'\n⚠️  コードが空白の行: {empty_codes}件')
        print(f'✅ コードがある行: {len(rows) - empty_codes}件')
        
        break
        
    except Exception as e:
        print(f'❌ 失敗: {e}')

print('\n' + '='*60)