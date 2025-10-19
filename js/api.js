/* ===== API通信ユーティリティ ===== */
async function safeJSON(resp) {
  try {
    const ct = resp.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      return { ok: false, _nonjson: true, text: await resp.text() };
    }
    return await resp.json();
  } catch (e) {
    return { ok: false, _parseError: String(e) };
  }
}

/* ===== サーバー接続テスト ===== */
async function testConnection() {
  setStatus('サーバー接続をテスト中...');
  try {
    const response = await fetch(`${API}/api/health`);
    const data = await safeJSON(response);
    if (response.ok && data.ok) {
      setStatus('サーバー接続成功！', 'success');
    } else {
      throw new Error('Server data not OK');
    }
  } catch (error) {
    setStatus('サーバーに接続できません', 'error');
  }
}

/* ===== コード検索（修正版） ===== */
async function fetchCodes(prefix = null) {
  try {
    // prefixから都道府県コードを抽出（例: "01-" -> "01"）
    const prefectureCode = prefix ? prefix.replace('-', '') : null;
    
    if (prefectureCode) {
      // 新しいAPIを使用：病院名付きで取得
      const url = new URL(`${API}/api/hospitals`);
      url.searchParams.append('prefecture', prefectureCode);
      
      const response = await fetch(url);
      const result = await safeJSON(response);
      
      if (response.ok && result.ok && Array.isArray(result.hospitals)) {
        // 新しいAPI形式: { hospitals: [{code: '01-02', name: '病院名'}, ...] }
        // 古い形式に変換: { items: [{code: '01-02', hospital: '病院名'}, ...] }
        return result.hospitals.map(h => ({
          code: h.code,
          hospital: h.name
        }));
      }
    } else {
      // prefixがない場合は古いAPIを使用
      const url = new URL(`${API}/api/mdata/search`);
      const response = await fetch(url);
      const result = await safeJSON(response);
      
      if (response.ok && result.ok && Array.isArray(result.items)) {
        return result.items;
      }
    }
  } catch (error) {
    console.error('Search error:', error);
  }
  return [];
}

/* ===== データ取得 ===== */
async function fillFromServer() {
  const codeSel = document.getElementById('codeSelect');
  const code = (codeSel.value || '').trim();
  if (!code) {
    setStatus('コードを選択してください', 'error');
    return;
  }

  // ロック切り替え
  if (currentLockCode && currentLockCode !== code) {
    await releaseLock(currentLockCode);
  }

  const ok = await acquireLock(code);
  if (!ok) {
    decorateCodeSelect();
    return;
  }

  isLoadingData = true;
  setStatus('データ取得中...');
  
  try {
    const r = await fetch(`${API}/api/mdata/${encodeURIComponent(code)}`);
    const j = await safeJSON(r);
    
    if (!r.ok || !j.ok) {
      isLoadingData = false;
      setStatus('データが見つかりません', 'error');
      await releaseLock(code);
      return;
    }

    currentData = { code: j.code, kv: j.kv || {} };
    const kv = currentData.kv;

    // メタ情報設定
    setMeta(kv);

    // テーブルデータ設定
    setTableData(
      document.getElementById('tbody'),
      kv,
      9,
      TABLE_KEYS.main,
      DEFAULT_ROWS.main,
      'main'
    );
    setTableData(
      document.getElementById('facilities-tbody'),
      kv,
      3,
      TABLE_KEYS.facilities,
      DEFAULT_ROWS.facilities,
      'facilities'
    );
    setTableData(
      document.getElementById('vendors-tbody'),
      kv,
      4,
      TABLE_KEYS.vendors,
      DEFAULT_ROWS.vendors,
      'vendors'
    );

    setStatus(LOCK_AVAILABLE ? `編集中: ${currentUsername}` : '転記完了', 'success');
    setButtons(true);
    isLoadingData = false;
    window.isDirty = false;
  } catch (e) {
    isLoadingData = false;
    setStatus('転記中にエラー: ' + e.message, 'error');
  }
}

/* ===== データ保存 ===== */
async function saveToServer() {
  if (!currentData || !currentData.code) {
    setStatus('まず転記してください', 'error');
    return;
  }

  setStatus('保存中...');
  const p = collectForSave();
  if (!p) {
    setStatus('保存データがありません', 'error');
    return;
  }

  try {
    const r = await fetch(`${API}/api/mdata/${encodeURIComponent(currentData.code)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kv: p })
    });
    const j = await safeJSON(r);
    
    if (r.ok && j.ok) {
      setStatus(`保存しました（${j.updated ?? 0}項目）`, 'success');
      syncMetaFields();
      window.isDirty = false;
      alert('変更を保存しました。');
    } else {
      setStatus((j && j.error) || '保存失敗', 'error');
    }
  } catch (e) {
    setStatus('保存中にエラー: ' + e.message, 'error');
  }
}

/* ===== 保存データ収集 ===== */
function collectForSave() {
  if (!currentData || !currentData.code) return null;

  const p = {};
  const g = id => document.getElementById(id).textContent || "";

  // メタ情報
  p["コード"] = g('v-code');
  p["都道府県"] = g('v-pref');
  p["病院名"] = g('v-hospital');
  p["郵便番号"] = g('v-zip');
  p["住所"] = g('v-addr');
  p["最寄駅"] = g('v-station');

  // TEL/DI分割
  const teldi = g('v-teldi');
  if (teldi && teldi !== "—") {
    const sp = teldi.split(/[／/]/);
    p["TEL"] = (sp[0] || "").trim();
    p["DI"] = (sp[1] || "").trim();
  } else {
    p["TEL"] = "";
    p["DI"] = "";
  }

  p["ファミレス"] = g('v-family');

  // テーブルデータ収集
  const collectTable = (tbody, keys) => {
    const rows = tbody.children.length;
    for (let i = 1; i <= rows; i++) {
      for (let j = 0; j < keys.length; j++) {
        const cell = tbody.querySelector(`td[data-r="${i - 1}"][data-c="${j}"]`);
        const value = cell ? cell.textContent.trim() : "";
        if (value) {
          writeSeries(p, keys[j], i, value);
        }
      }
    }
  };

  collectTable(document.getElementById('tbody'), TABLE_KEYS.main);
  collectTable(document.getElementById('facilities-tbody'), TABLE_KEYS.facilities);
  collectTable(document.getElementById('vendors-tbody'), TABLE_KEYS.vendors);

  return p;
}