/* ===== テーブル行の構築 ===== */
function buildRows(tbody, rows, cols, idPrefix) {
  const existingRows = tbody.children.length;
  for (let i = 0; i < rows; i++) {
    const tr = document.createElement('tr');
    let h = '';
    const rowIndex = existingRows + i;
    for (let j = 0; j < cols; j++) {
      const center = (idPrefix === 'main' && (j === 0 || j === 1 || j === 6 || j === 7)) ? 'center' : '';
      h += `<td class="editable ${center}" contenteditable="plaintext-only" data-r="${rowIndex}" data-c="${j}"></td>`;
    }
    tr.innerHTML = h;
    tbody.appendChild(tr);
  }
}

/* ===== 行追加・削除 ===== */
function addTableRows(type, count = 1) {
  let tbody, cols, maxRows, idPrefix;
  
  if (type === 'main') {
    tbody = document.getElementById('tbody');
    cols = 9;
    maxRows = 200;
    idPrefix = 'main';
  } else if (type === 'facilities') {
    tbody = document.getElementById('facilities-tbody');
    cols = 3;
    maxRows = 100;
    idPrefix = 'facilities';
  } else {
    tbody = document.getElementById('vendors-tbody');
    cols = 4;
    maxRows = 200;
    idPrefix = 'vendors';
  }

  const cur = tbody.children.length;
  if (cur + count > maxRows && !confirm(`最大推奨行数${maxRows}を超えます。続行しますか？`)) {
    return;
  }

  buildRows(tbody, count, cols, idPrefix);
  updateRowCountBadges();
  setStatus(`${type}テーブルに${count}行追加しました`, 'success');
}

function removeTableRows(type, count = 1) {
  const tbody = document.getElementById(type === 'main' ? 'tbody' : `${type}-tbody`);
  const cur = tbody.children.length;
  if (!cur) return;
  
  const rm = Math.min(count, cur);
  for (let i = 0; i < rm; i++) {
    tbody.removeChild(tbody.lastElementChild);
  }
  
  updateRowCountBadges();
  setStatus(`${type}テーブルから${rm}行削除しました`, 'success');
}

function updateRowCountBadges() {
  const m = document.getElementById('main-row-count');
  if (m) m.textContent = document.getElementById('tbody').children.length;
  
  const f = document.getElementById('facilities-row-count');
  if (f) f.textContent = document.getElementById('facilities-tbody').children.length;
  
  const v = document.getElementById('vendors-row-count');
  if (v) v.textContent = document.getElementById('vendors-tbody').children.length;
}

/* ===== データ行数取得 ===== */
function getRowCountFromData(kv, keys) {
  let maxRow = 0;
  for (const key in kv) {
    const parts = key.split('_');
    if (parts.length === 2 && keys.includes(parts[0])) {
      const rowNum = parseInt(parts[1], 10);
      const value = kv[key];
      if (!isNaN(rowNum) && value && value.trim() !== '') {
        if (rowNum > maxRow) {
          maxRow = rowNum;
        }
      }
    }
  }
  return maxRow;
}

/* ===== メタ情報設定 ===== */
function setMeta(kv) {
  const g = id => document.getElementById(id);
  
  g('v-code').textContent = kv['コード'] || "—";
  g('v-pref').textContent = kv['都道府県'] || "—";
  g('v-hospital').textContent = kv['病院名'] || "—";
  g('v-zip').textContent = kv['郵便番号'] || "—";
  g('v-addr').textContent = kv['住所'] || "—";
  g('v-station').textContent = kv['最寄駅'] || "—";
  
  const tel = kv['TEL'] || "";
  const di = kv['DI'] || "";
  g('v-teldi').textContent = (tel && di) ? `${tel}／${di}` : (tel || di || "—");
  g('v-family').textContent = kv['ファミレス'] || "—";
  
  syncMetaFields();
}

/* ===== テーブルデータ設定 ===== */
function setTableData(tbody, kv, cols, keys, minRows, idPrefix) {
  const dataRows = getRowCountFromData(kv, keys);
  const displayRows = Math.max(dataRows, minRows);
  
  tbody.innerHTML = '';
  buildRows(tbody, displayRows, cols, idPrefix);
  
  const cells = tbody.querySelectorAll('.editable[contenteditable]');
  for (let i = 0; i < displayRows; i++) {
    const n = i + 1;
    for (let j = 0; j < cols; j++) {
      const cell = cells[i * cols + j];
      if (cell) {
        const value = i < dataRows ? readSeries(kv, keys[j], n) : '';
        cell.textContent = value || '';
      }
    }
  }
  
  updateRowCountBadges();
}

/* ===== メタ情報同期 ===== */
function syncMetaFields() {
  const syncPairs = [
    ['v-code', 'v2-code'],
    ['v-hospital', 'v2-hospital']
  ];
  
  const teldi = document.getElementById('v-teldi').textContent || "";
  const parts = teldi.split(/[／/]/);
  const tel = (parts[0] || "").trim();
  const di = (parts[1] || "").trim();
  
  document.getElementById('v2-tel').textContent = tel || "—";
  document.getElementById('v2-di').textContent = di || "—";
  
  syncPairs.forEach(([source, target]) => {
    const sourceEl = document.getElementById(source);
    const targetEl = document.getElementById(target);
    if (sourceEl && targetEl) {
      targetEl.textContent = sourceEl.textContent;
    }
  });
}