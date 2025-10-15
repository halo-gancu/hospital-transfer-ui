/* ===== 選択情報更新 ===== */
function updateSelectionInfo(table, rect) {
  const tableId = table.id;
  let infoId = 'selection-info';
  if (tableId.includes('facilities')) infoId = 'selection-info-facilities';
  else if (tableId.includes('vendors')) infoId = 'selection-info-vendors';
  
  const info = document.getElementById(infoId);
  if (!info) return;
  
  if (rect && (rect.r1 !== rect.r2 || rect.c1 !== rect.c2)) {
    const rows = rect.r2 - rect.r1 + 1;
    const cols = rect.c2 - rect.c1 + 1;
    info.textContent = `${rows}行 × ${cols}列`;
    info.classList.add('show');
  } else {
    info.classList.remove('show');
  }
}

/* ===== カーソル配置 ===== */
function placeCaret(td, atEnd = false) {
  td.focus();
  const sel = window.getSelection();
  if (sel.rangeCount > 0) sel.removeAllRanges();
  const range = document.createRange();
  range.selectNodeContents(td);
  range.collapse(atEnd);
  sel.addRange(range);
}

/* ===== 選択クリア ===== */
function clearAllSelections() {
  document.querySelectorAll('td.sel').forEach(td => td.classList.remove('sel', 'anchor'));
  document.querySelectorAll('.selection-info').forEach(el => el.classList.remove('show'));
  if (!editingCell) {
    document.querySelectorAll('td.editable').forEach(td => {
      if (td === document.activeElement && !isEditing(td)) {
        td.blur();
      }
    });
  }
  selRect = null;
  anchor = null;
}

/* ===== 範囲選択適用 ===== */
function applyRectSelection(table, r1, c1, r2, c2) {
  document.querySelectorAll('td.sel').forEach(td => td.classList.remove('sel', 'anchor'));
  document.querySelectorAll('.selection-info').forEach(el => el.classList.remove('show'));
  
  const rr1 = Math.min(r1, r2), rr2 = Math.max(r1, r2);
  const cc1 = Math.min(c1, c2), cc2 = Math.max(c1, c2);
  
  for (let r = rr1; r <= rr2; r++) {
    for (let c = cc1; c <= cc2; c++) {
      const td = table.querySelector(`td[data-r="${r}"][data-c="${c}"]`);
      if (td) td.classList.add('sel');
    }
  }
  
  const anchorCell = table.querySelector(`td[data-r="${r1}"][data-c="${c1}"]`);
  if (anchorCell) {
    anchorCell.classList.add('anchor');
    if (!isEditing(anchorCell)) {
      anchorCell.focus();
    }
  }
  
  selRect = { table, r1: rr1, c1: cc1, r2: rr2, c2: cc2 };
  updateSelectionInfo(table, selRect);
}

/* ===== 編集状態管理 ===== */
function isEditing(td) {
  return td && td.getAttribute('data-editing') === 'true';
}

function enterEdit(td, options = {}) {
  const { clearContent = false, placeCaretAtEnd = false } = options;
  if (editingCell && editingCell !== td) exitEdit();
  if (isEditing(td)) return;
  
  editingCell = td;
  if (clearContent) td.textContent = '';
  td.setAttribute('data-editing', 'true');
  td.focus();
  if (placeCaretAtEnd) placeCaret(td, true);
}

function exitEdit() {
  if (editingCell) {
    editingCell.blur();
    editingCell.removeAttribute('data-editing');
    editingCell = null;
  }
}

/* ===== セル移動 ===== */
function moveFocusCell(table, r, c, startEdit = false) {
  const td = table.querySelector(`td[data-r="${r}"][data-c="${c}"]`);
  if (!td) return;
  
  exitEdit();
  applyRectSelection(table, r, c, r, c);
  anchor = { table, r, c };
  if (startEdit) enterEdit(td);
}

/* ===== 全選択 ===== */
function selectAll(table) {
  const tbody = table.tBodies[0];
  if (!tbody || !tbody.rows.length) return;
  
  const maxR = tbody.rows.length - 1;
  const maxC = table.tHead.rows[0].cells.length - 1;
  applyRectSelection(table, 0, 0, maxR, maxC);
  exitEdit();
}

/* ===== TSV変換 ===== */
function rectToTSV(rect) {
  if (!rect) return '';
  const { table, r1, c1, r2, c2 } = rect;
  const out = [];
  
  for (let r = r1; r <= r2; r++) {
    const row = [];
    for (let c = c1; c <= c2; c++) {
      const td = table.querySelector(`td[data-r="${r}"][data-c="${c}"]`);
      row.push(td ? td.innerText : '');
    }
    out.push(row.join('\t'));
  }
  return out.join('\n');
}

/* ===== 範囲塗りつぶし ===== */
function fillRange(rect, valueFn) {
  if (!rect) return;
  const { table, r1, c1, r2, c2 } = rect;
  
  for (let r = r1; r <= r2; r++) {
    for (let c = c1; c <= c2; c++) {
      const td = table.querySelector(`td[data-r="${r}"][data-c="${c}"]`);
      if (td) td.textContent = valueFn(r, c);
    }
  }
}

/* ===== TSV貼り付け ===== */
function pasteTSVIntoRect(table, startR, startC, text) {
  const rows = (text || '').replace(/\r/g, '').split('\n').map(r => r.split('\t'));
  const h = rows.length;
  if (h === 0) return;
  const w = rows[0].length;
  
  const requiredRows = startR + h;
  const currentRows = table.tBodies[0].rows.length;
  
  if (requiredRows > currentRows) {
    const type = table.id.split('-')[0];
    const cols = table.tHead.rows[0].cells.length;
    buildRows(table.tBodies[0], requiredRows - currentRows, cols, type);
    updateRowCountBadges();
  }
  
  for (let i = 0; i < h; i++) {
    for (let j = 0; j < w; j++) {
      const r = startR + i, c = startC + j;
      const td = table.querySelector(`td[data-r="${r}"][data-c="${c}"]`);
      if (td) {
        td.textContent = (rows[i] && rows[i][j] !== undefined) ? rows[i][j] : '';
      }
    }
  }
  
  const maxR = table.tBodies[0].rows.length - 1;
  const maxC = table.tHead.rows[0].cells.length - 1;
  applyRectSelection(table, startR, startC, Math.min(maxR, startR + h - 1), Math.min(maxC, startC + w - 1));
}

/* ===== コピー効果 ===== */
function showCopyEffect(rect) {
  if (!rect) return;
  const { table, r1, c1, r2, c2 } = rect;
  
  for (let r = r1; r <= r2; r++) {
    for (let c = c1; c <= c2; c++) {
      const td = table.querySelector(`td[data-r="${r}"][data-c="${c}"]`);
      if (td) {
        td.classList.add('copying');
        setTimeout(() => td.classList.remove('copying'), 600);
      }
    }
  }
}

/* ===== Excel風選択初期化 ===== */
function initExcelLikeSelection() {
  // マウスダウン
  document.querySelectorAll('table.selectable-table').forEach(table => {
    table.addEventListener('mousedown', e => {
      document.body.classList.add('noselect');
      const td = e.target.closest('td.editable');
      if (!td) return;
      if (isEditing(td)) return;
      
      e.preventDefault();
      exitEdit();
      isDown = true;
      isDrag = false;
      
      const r = +td.dataset.r, c = +td.dataset.c;
      if (e.shiftKey && anchor && anchor.table === table) {
        applyRectSelection(table, anchor.r, anchor.c, r, c);
      } else {
        applyRectSelection(table, r, c, r, c);
        anchor = { table, r, c };
      }
    });
  });

  // マウスムーブ
  document.addEventListener('mousemove', e => {
    if (!isDown || !anchor) return;
    const targetTd = e.target.closest('td.editable');
    if (isEditing(targetTd) || !targetTd || targetTd.closest('table') !== anchor.table) return;
    
    isDrag = true;
    applyRectSelection(anchor.table, anchor.r, anchor.c, +targetTd.dataset.r, +targetTd.dataset.c);
  });

  // マウスアップ
  document.addEventListener('mouseup', () => {
    document.body.classList.remove('noselect');
    if (isDown && !isDrag && anchor) {
      const td = anchor.table.querySelector(`td[data-r="${anchor.r}"][data-c="${anchor.c}"]`);
      if (td && !isEditing(td)) td.focus();
    }
    isDown = false;
    isDrag = false;
  });

  // ダブルクリック
  document.addEventListener('dblclick', e => {
    const td = e.target.closest('td.editable');
    if (td) enterEdit(td);
  });

  // キーボード操作
  document.addEventListener('keydown', e => {
    const activeTd = document.activeElement.closest('td.editable');
    if (!activeTd) return;
    
    const table = activeTd.closest('table.selectable-table');
    const r = +activeTd.dataset.r, c = +activeTd.dataset.c;
    const maxR = table.tBodies[0].rows.length - 1;
    const maxC = table.tHead.rows[0].cells.length - 1;
    const editing = isEditing(activeTd);

    // Ctrl+A
    if (e.ctrlKey || e.metaKey) {
      if (e.key.toLowerCase() === 'a') {
        e.preventDefault();
        selectAll(table);
      }
      return;
    }

    switch (e.key) {
      case 'Enter':
        e.preventDefault();
        if (editing && e.altKey) {
          document.execCommand('insertLineBreak');
          return;
        }
        const nr_enter = e.shiftKey ? Math.max(0, r - 1) : Math.min(maxR, r + 1);
        moveFocusCell(table, nr_enter, c, editing);
        break;

      case 'Tab':
        e.preventDefault();
        let nr_tab = r, nc_tab = c;
        if (e.shiftKey) {
          if (c > 0) nc_tab--;
          else { nc_tab = maxC; nr_tab = Math.max(0, r - 1); }
        } else {
          if (c < maxC) nc_tab++;
          else { nc_tab = 0; nr_tab = Math.min(maxR, r + 1); }
        }
        moveFocusCell(table, nr_tab, nc_tab, editing);
        break;

      case 'ArrowUp':
      case 'ArrowDown':
      case 'ArrowLeft':
      case 'ArrowRight':
        if (editing) return;
        e.preventDefault();
        let nr_arrow = r, nc_arrow = c;
        if (e.key === 'ArrowUp') nr_arrow = Math.max(0, r - 1);
        if (e.key === 'ArrowDown') nr_arrow = Math.min(maxR, r + 1);
        if (e.key === 'ArrowLeft') nc_arrow = Math.max(0, c - 1);
        if (e.key === 'ArrowRight') nc_arrow = Math.min(maxC, c + 1);
        
        if (e.shiftKey) {
          if (!anchor) anchor = { table, r, c };
          applyRectSelection(table, anchor.r, anchor.c, nr_arrow, nc_arrow);
          table.querySelector(`td[data-r="${nr_arrow}"][data-c="${nc_arrow}"]`)?.focus();
        } else {
          moveFocusCell(table, nr_arrow, nc_arrow);
        }
        break;

      case 'F2':
        e.preventDefault();
        if (!editing) enterEdit(activeTd, { placeCaretAtEnd: true });
        break;

      case 'Escape':
        e.preventDefault();
        if (editing) {
          exitEdit();
          activeTd.focus();
        } else {
          clearAllSelections();
        }
        break;

      case 'Delete':
      case 'Backspace':
        if (!editing) {
          e.preventDefault();
          fillRange(selRect, () => '');
        }
        break;

      default:
        if (!editing && e.key.length === 1 && !e.altKey) {
          enterEdit(activeTd, { clearContent: true });
        }
        break;
    }
  });

  // 貼り付け
  document.addEventListener('paste', e => {
    if (isEditing(document.activeElement)) return;
    const activeTd = document.activeElement.closest('td.editable');
    if (!activeTd) return;
    
    e.preventDefault();
    const pastedText = e.clipboardData.getData('text/plain') || '';
    const table = activeTd.closest('table.selectable-table');
    const r = selRect ? selRect.r1 : +activeTd.dataset.r;
    const c = selRect ? selRect.c1 : +activeTd.dataset.c;
    
    if (/\t|\n/.test(pastedText)) {
      pasteTSVIntoRect(table, r, c, pastedText);
    } else {
      if (selRect) {
        fillRange(selRect, () => pastedText);
      } else {
        activeTd.textContent = pastedText;
      }
    }
  });

  // コピー
  document.addEventListener('copy', e => {
    if (isEditing(document.activeElement)) return;
    const activeTd = document.activeElement.closest('td.editable');
    if (!activeTd || !selRect) return;
    
    e.preventDefault();
    e.clipboardData.setData('text/plain', rectToTSV(selRect));
    showCopyEffect(selRect);
  });

  // カット
  document.addEventListener('cut', e => {
    if (isEditing(document.activeElement)) return;
    const activeTd = document.activeElement.closest('td.editable');
    if (!activeTd || !selRect) return;
    
    e.preventDefault();
    e.clipboardData.setData('text/plain', rectToTSV(selRect));
    showCopyEffect(selRect);
    fillRange(selRect, () => '');
  });
}