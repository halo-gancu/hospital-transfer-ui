/* ===== ページ切り替え ===== */
function showPage(type) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-bar button').forEach(b => b.classList.remove('active'));
  document.getElementById(`page-${type}`).classList.add('active');
  document.getElementById(`tab-${type}`).classList.add('active');
}

/* ===== ステータス表示 ===== */
function setStatus(msg, type = 'normal', id = 'status') {
  const s = document.getElementById(id);
  if (!s) return;
  
  s.textContent = msg;
  s.className = (type === 'error' ? 'status-error' : (type === 'success' ? 'status-success' : ''));
  
  if (id === 'status') {
    const s2 = document.getElementById('status2');
    if (s2) {
      s2.textContent = msg;
      s2.className = s.className;
    }
  }
}

/* ===== ボタン有効/無効 ===== */
function setButtons(on) {
  ['fillBtn', 'saveBtn', 'saveBtn2', 'fillBtn2'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = !on;
  });
}

/* ===== フォームクリア ===== */
async function clearForm() {
  const codeSel = document.getElementById('codeSelect');
  const prefSel = document.getElementById('prefSelect');
  
  // ロック解放
  if (currentLockCode) {
    await releaseLock(currentLockCode);
  }
  
  if (codeSel) {
    codeSel.value = '';
    codeSel.disabled = true;
    codeSel.innerHTML = '<option value="">選択</option>';
  }
  if (prefSel) prefSel.value = '';
  
  // メタ情報クリア
  ['v-code', 'v-pref', 'v-hospital', 'v-zip', 'v-addr', 'v-station', 'v-teldi', 'v-family',
   'v2-code', 'v2-hospital', 'v2-tel', 'v2-di'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = '—';
  });
  
  // テーブルクリア
  document.querySelectorAll('tbody').forEach(tb => tb.innerHTML = '');
  buildRows(document.getElementById('tbody'), DEFAULT_ROWS.main, 9, 'main');
  buildRows(document.getElementById('facilities-tbody'), DEFAULT_ROWS.facilities, 3, 'facilities');
  buildRows(document.getElementById('vendors-tbody'), DEFAULT_ROWS.vendors, 4, 'vendors');
  
  updateRowCountBadges();
  clearAllSelections();
  currentData = null;
  setButtons(false);
  decorateCodeSelect();
  updateActiveUsersCount();
  setStatus('フォームをクリアしました', 'success');
  window.isDirty = false;
}

/* ===== ドロップダウン初期化 ===== */
function initDropdowns() {
  const prefSel = document.getElementById('prefSelect');
  const codeSel = document.getElementById('codeSelect');
  
  // 都道府県選択肢追加
  PREFS.forEach(([no, name]) => {
    const o = document.createElement('option');
    o.value = no;
    o.textContent = `${parseInt(no, 10)} ${name}`;
    prefSel.appendChild(o);
  });
  
  // 都道府県変更時
  prefSel.addEventListener('change', async () => {
    const pref = prefSel.value;
    codeSel.innerHTML = '<option value="">選択</option>';
    codeSel.disabled = true;
    if (!pref) return;
    
    const items = await fetchCodes(`${pref}-`);
    if (items.length) {
      codeSel.disabled = false;
      items.forEach(it => {
        const o = document.createElement('option');
        o.value = it.code;
        o.textContent = it.hospital ? `${it.code} ${it.hospital}` : it.code;
        o.setAttribute('data-base-text', o.textContent);
        codeSel.appendChild(o);
      });
      await fetchLocks();
      decorateCodeSelect();
    }
  });
  
  // コード変更時
  codeSel.addEventListener('change', async () => {
    const v = codeSel.value;
    if (!v) return;
    await fillFromServer();
  });
}

/* ===== CSVファイル入力初期化 ===== */
function initFileInput() {
  const fileInput = document.getElementById('mdataFile');
  fileInput.addEventListener('change', async e => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    
    setStatus('CSVファイルを読み込み中...');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const resp = await fetch(`${API}/api/mdata/import_csv`, { method: 'POST', body: fd });
      const result = await safeJSON(resp);
      
      if (resp.ok && result.ok) {
        setStatus(`読み込み完了: ${result.imported ?? '---'}件`, 'success');
        const prefSel = document.getElementById('prefSelect');
        if (prefSel.value) {
          prefSel.dispatchEvent(new Event('change'));
        }
      } else {
        setStatus(`エラー: ${(result && result.error) || resp.statusText}`, 'error');
      }
    } catch (err) {
      setStatus(`エラー: ${err.message}`, 'error');
    }
    fileInput.value = '';
  });
}

/* ===== 未保存対策：変更検知 ===== */
window.markDirty = function() {
  if (isLoadingData) return;
  window.isDirty = true;
};

function initDirtyTracking() {
  // input イベント
  document.addEventListener('input', (e) => {
    const t = e.target;
    if (!t) return;
    
    if (t.id === 'prefSelect' || t.id === 'codeSelect' || t.id === 'mdataFile') {
      return;
    }
    
    if (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName)) {
      window.markDirty();
    }
  }, true);

  // keydown イベント
  document.addEventListener('keydown', (e) => {
    const t = e.target;
    if (t && t.isContentEditable) {
      window.markDirty();
    }
  }, true);
}

/* ===== ログアウト処理 ===== */
function initLogoutHandler() {
  const logoutEl = document.getElementById('logout-link');
  if (!logoutEl) return;

  logoutEl.addEventListener('click', async (e) => {
    e.preventDefault();
    
    // ロック解放
    if (currentLockCode) {
      await releaseLock(currentLockCode);
    }
    
    if (!window.isDirty) {
      location.href = '/logout';
      return;
    }
    
    // カスタムダイアログ
    const dialog = document.createElement('div');
    dialog.innerHTML = `
      <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;">
        <div style="background:white;padding:30px;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.3);max-width:400px;">
          <h3 style="margin:0 0 20px;font-size:18px;color:#333;">未保存の変更があります</h3>
          <p style="margin:0 0 25px;font-size:14px;color:#666;">どうしますか？</p>
          <div style="display:flex;gap:10px;justify-content:flex-end;">
            <button id="logout-cancel" style="padding:10px 20px;background:#6c757d;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px;font-weight:600;">キャンセル</button>
            <button id="logout-discard" style="padding:10px 20px;background:#dc3545;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px;font-weight:600;">破棄してログアウト</button>
            <button id="logout-save" style="padding:10px 20px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px;font-weight:600;">保存してログアウト</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(dialog);

    document.getElementById('logout-cancel').onclick = () => {
      dialog.remove();
    };

    document.getElementById('logout-discard').onclick = () => {
      window.isDirty = false;
      if (currentLockCode) {
        releaseLock(currentLockCode);
      }
      dialog.remove();
      location.href = '/logout';
    };

    document.getElementById('logout-save').onclick = async () => {
      try {
        await saveToServer();
        window.isDirty = false;
        if (currentLockCode) {
          await releaseLock(currentLockCode);
        }
        dialog.remove();
        location.href = '/logout';
      } catch (err) {
        alert('保存に失敗しました。');
        dialog.remove();
      }
    };
  });
}

/* ===== 自動ログアウトタイマー ===== */
function resetIdleTimer() {
  if (idleTimer) clearTimeout(idleTimer);
  
  idleTimer = setTimeout(() => {
    // 警告ダイアログ
    const dialog = document.createElement('div');
    dialog.innerHTML = `
      <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;">
        <div style="background:white;padding:30px;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.3);max-width:450px;">
          <h3 style="margin:0 0 20px;font-size:18px;color:#dc3545;">⚠️ 自動ログアウト警告</h3>
          <p style="margin:0 0 25px;font-size:14px;color:#666;">20分間操作がありませんでした。<br>2分後に自動ログアウトします。</p>
          <div style="display:flex;gap:10px;justify-content:flex-end;">
            <button id="auto-logout-continue" style="padding:10px 20px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px;font-weight:600;">作業を続ける</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(dialog);

    let finalTimer = setTimeout(async () => {
      dialog.remove();
      
      if (window.isDirty) {
        const saveDialog = document.createElement('div');
        saveDialog.innerHTML = `
          <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;">
            <div style="background:white;padding:30px;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.3);max-width:400px;">
              <h3 style="margin:0 0 20px;font-size:18px;color:#333;">未保存の変更があります</h3>
              <p style="margin:0 0 25px;font-size:14px;color:#666;">保存してログアウトしますか？</p>
              <div style="display:flex;gap:10px;justify-content:flex-end;">
                <button id="auto-logout-discard" style="padding:10px 20px;background:#dc3545;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px;font-weight:600;">破棄</button>
                <button id="auto-logout-save" style="padding:10px 20px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px;font-weight:600;">保存</button>
              </div>
            </div>
          </div>
        `;
        document.body.appendChild(saveDialog);

        document.getElementById('auto-logout-discard').onclick = () => {
          window.isDirty = false;
          if (currentLockCode) {
            releaseLock(currentLockCode);
          }
          location.href = '/logout';
        };

        document.getElementById('auto-logout-save').onclick = async () => {
          try {
            await saveToServer();
            window.isDirty = false;
            if (currentLockCode) {
              await releaseLock(currentLockCode);
            }
            location.href = '/logout';
          } catch (err) {
            alert('保存に失敗しました。');
            location.href = '/logout';
          }
        };
      } else {
        location.href = '/logout';
      }
    }, WARNING_BEFORE);

    document.getElementById('auto-logout-continue').onclick = () => {
      clearTimeout(finalTimer);
      dialog.remove();
      resetIdleTimer();
    };
  }, IDLE_TIMEOUT - WARNING_BEFORE);
}

function initAutoLogout() {
  ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click', 'input'].forEach(event => {
    document.addEventListener(event, resetIdleTimer, true);
  });
  resetIdleTimer();
  console.log('⏰ 自動ログアウトタイマー開始（20分）');
}

/* ===== セッション情報取得 ===== */
async function initSessionInfo() {
  try {
    const response = await fetch('/api/session');
    const data = await response.json();
    
    if (data.ok && data.user) {
      const usernameDisplay = document.getElementById('username-text');
      if (usernameDisplay) {
        const displayName = data.user.username || data.user.user_id || '不明';
        usernameDisplay.textContent = displayName;
      }
      
      if (data.user.role === 'admin') {
        document.getElementById('admin-menu').style.display = 'inline';
      }
    }
  } catch (error) {
    console.error('セッション情報の取得に失敗:', error);
    const usernameDisplay = document.getElementById('username-text');
    if (usernameDisplay) {
      usernameDisplay.textContent = 'ゲスト';
    }
  }
}