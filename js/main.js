/* ===== セッション情報取得 ===== */
async function initSessionInfo() {
  console.log('🔐 セッション情報を取得中...');
  
  try {
    const response = await fetch('/api/session');
    const data = await response.json();
    
    console.log('📡 /api/session レスポンス:', data);
    
    if (response.ok && data.ok && data.logged_in && data.user) {
      currentUserId = data.user.id;
      currentUsername = data.user.username;
      currentUserRole = data.user.role;
      
      console.log(`✅ セッション確認成功: ${currentUsername} (${currentUserRole})`);
      
      // ユーザー名を表示
      const usernameText = document.getElementById('username-text');
      if (usernameText) {
        usernameText.textContent = currentUsername;
      }
      
      // 管理者メニューを表示
      if (currentUserRole === 'admin') {
        const adminMenu = document.getElementById('admin-menu');
        if (adminMenu) {
          adminMenu.style.display = 'inline';
        }
      }
      
      return true;
    } else {
      console.error('❌ セッション確認失敗:', data);
      return false;
    }
  } catch (error) {
    console.error('❌ セッション取得エラー:', error);
    return false;
  }
}

/* ===== メイン初期化処理 ===== */
async function initApp() {
  console.log('🚀 アプリケーション初期化開始');
  
  // モバイル警告
  if (window.innerWidth < 768) {
    const warning = document.getElementById('mobile-warning');
    if (warning) {
      warning.style.display = 'block';
    }
  }

  // 各機能初期化
  try {
    await detectLockAPI();
    buildRows(document.getElementById('tbody'), DEFAULT_ROWS.main, 9, 'main');
    buildRows(document.getElementById('facilities-tbody'), DEFAULT_ROWS.facilities, 3, 'facilities');
    buildRows(document.getElementById('vendors-tbody'), DEFAULT_ROWS.vendors, 4, 'vendors');
    updateRowCountBadges();
    initDropdowns();
    initFileInput();
    initExcelLikeSelection();
    initSocket();
    initDirtyTracking();
    initLogoutHandler();
    initAutoLogout();
    await initSessionInfo();
    await testConnection();
    
    console.log('✅ アプリケーション初期化完了');
  } catch (error) {
    console.error('❌ 初期化エラー:', error);
    setStatus('初期化中にエラーが発生しました', 'error');
  }

  // ページ離脱/非表示時のロック解放
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden' && currentLockCode) {
      releaseLock(currentLockCode);
    }
  });
  
  window.addEventListener('pagehide', () => {
    if (currentLockCode) {
      releaseLock(currentLockCode);
    }
  });
}

/* ===== DOMContentLoaded イベント (エントリーポイント) ===== */
document.addEventListener('DOMContentLoaded', async () => {
  console.log('📄 DOMContentLoaded イベント発火');
  console.log('🔐 セッション確認開始');

  try {
    const response = await fetch('/api/session');
    
    console.log('📡 /api/session ステータス:', response.status);
    
    if (!response.ok) {
      console.error('❌ セッションAPI呼び出し失敗:', response.status);
      throw new Error(`HTTP ${response.status}`);
    }
    
    const data = await response.json();
    console.log('📦 セッションデータ:', data);
    
    // レスポンス形式の確認
    if (data.ok && data.logged_in && data.user) {
      currentUserId = data.user.id;
      currentUsername = data.user.username;
      currentUserRole = data.user.role;
      
      console.log(`✅ 認証成功: ${currentUsername} (ID: ${currentUserId}, Role: ${currentUserRole})`);
      
      // アプリ初期化
      await initApp();
      
    } else if (data.logged_in === false) {
      // 明示的に未ログイン
      console.warn('🔒 未認証状態を検出');
      console.log('🔄 ログインページにリダイレクトします...');
      
      // 3秒待ってからリダイレクト（デバッグ用）
      setTimeout(() => {
        window.location.href = '/login';
      }, 1000);
      
    } else {
      // 予期しないレスポンス形式
      console.error('❌ 予期しないレスポンス形式:', data);
      throw new Error('Invalid session response format');
    }
    
  } catch (error) {
    console.error('❌ セッション確認中にエラー:', error);
    console.error('エラー詳細:', {
      message: error.message,
      stack: error.stack
    });
    
    setStatus('サーバーとの接続に失敗しました。', 'error');
    
    // 2秒後にログインページへ
    setTimeout(() => {
      console.log('🔄 エラーのためログインページにリダイレクト');
      window.location.href = '/login';
    }, 2000);
  }
});

/* ===== ログアウトハンドラ ===== */
function initLogoutHandler() {
  const logoutLink = document.getElementById('logout-link');
  if (logoutLink) {
    logoutLink.addEventListener('click', async (e) => {
      e.preventDefault();
      
      if (window.isDirty) {
        if (!confirm('保存していない変更があります。ログアウトしますか？')) {
          return;
        }
      }
      
      // ロック解放
      if (currentLockCode) {
        await releaseLock(currentLockCode);
      }
      
      // ログアウト
      window.location.href = '/logout';
    });
  }
}

/* ===== 自動ログアウト ===== */
let autoLogoutTimer = null;
const AUTO_LOGOUT_TIME = 30 * 60 * 1000; // 30分

function initAutoLogout() {
  function resetTimer() {
    if (autoLogoutTimer) {
      clearTimeout(autoLogoutTimer);
    }
    
    autoLogoutTimer = setTimeout(() => {
      console.warn('⏰ 自動ログアウト（30分間操作なし）');
      alert('30分間操作がなかったため、自動的にログアウトします。');
      window.location.href = '/logout';
    }, AUTO_LOGOUT_TIME);
  }
  
  // 操作イベントで自動ログアウトをリセット
  ['mousedown', 'keydown', 'scroll', 'touchstart'].forEach(event => {
    document.addEventListener(event, resetTimer, true);
  });
  
  resetTimer();
}

/* ===== ステータス表示 ===== */
function setStatus(msg, type = '') {
  const status = document.getElementById('status');
  const status2 = document.getElementById('status2');
  
  if (status) {
    status.textContent = msg;
    status.className = type;
  }
  
  if (status2 && type === 'success') {
    status2.textContent = msg;
    status2.className = type;
  }
  
  console.log(`📊 ステータス更新 [${type}]: ${msg}`);
}

/* ===== ボタン有効/無効制御 ===== */
function setButtons(enabled) {
  const buttons = ['fillBtn', 'saveBtn', 'fillBtn2', 'saveBtn2'];
  buttons.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) {
      btn.disabled = !enabled;
    }
  });
}

/* ===== Dirty tracking ===== */
function initDirtyTracking() {
  window.isDirty = false;
  
  // contenteditable要素の監視
  document.querySelectorAll('[contenteditable]').forEach(el => {
    el.addEventListener('input', () => {
      if (!isLoadingData) {
        window.isDirty = true;
      }
    });
  });
  
  // ページ離脱時の警告
  window.addEventListener('beforeunload', (e) => {
    if (window.isDirty) {
      e.preventDefault();
      e.returnValue = '';
      return '';
    }
  });
}

/* ===== ページ切り替え ===== */
function showPage(pageName) {
  console.log(`📄 ページ切り替え: ${pageName}`);
  
  // すべてのページを非表示
  document.querySelectorAll('.page').forEach(page => {
    page.classList.remove('active');
  });
  
  // すべてのタブを非アクティブ化
  document.querySelectorAll('.nav-bar button').forEach(btn => {
    btn.classList.remove('active');
  });
  
  // 指定されたページを表示
  const targetPage = document.getElementById(`page-${pageName}`);
  if (targetPage) {
    targetPage.classList.add('active');
  }
  
  // 対応するタブをアクティブ化
  const targetTab = document.getElementById(`tab-${pageName}`);
  if (targetTab) {
    targetTab.classList.add('active');
  }
}

/* ===== クリアボタン ===== */
function clearForm() {
  if (window.isDirty) {
    if (!confirm('保存していない変更があります。クリアしますか？')) {
      return;
    }
  }
  
  // ロック解放
  if (currentLockCode) {
    releaseLock(currentLockCode);
  }
  
  // メタ情報クリア
  const metaIds = ['v-code', 'v-pref', 'v-hospital', 'v-zip', 'v-addr', 'v-station', 'v-teldi', 'v-family'];
  metaIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = '—';
  });
  
  const meta2Ids = ['v2-code', 'v2-hospital', 'v2-tel', 'v2-di'];
  meta2Ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = '—';
  });
  
  // テーブルクリア
  clearTableData(document.getElementById('tbody'), 9);
  clearTableData(document.getElementById('facilities-tbody'), 3);
  clearTableData(document.getElementById('vendors-tbody'), 4);
  
  currentData = null;
  window.isDirty = false;
  
  setStatus('フォームをクリアしました', 'success');
  setButtons(false);
  
  // ドロップダウンリセット
  const codeSelect = document.getElementById('codeSelect');
  if (codeSelect) {
    codeSelect.value = '';
    codeSelect.disabled = true;
  }
}

/* ===== テーブルデータクリア ===== */
function clearTableData(tbody, cols) {
  if (!tbody) return;
  
  Array.from(tbody.children).forEach(tr => {
    Array.from(tr.children).forEach(td => {
      td.textContent = '';
    });
  });
}

/* ===== メタ情報設定 ===== */
function setMeta(kv) {
  const set = (id, key, def = '—') => {
    const el = document.getElementById(id);
    if (el) {
      const val = kv[key];
      el.textContent = (val !== undefined && val !== null && val !== '') ? val : def;
    }
  };

  // ページ1
  set('v-code', 'コード');
  set('v-pref', '都道府県');
  set('v-hospital', '病院名');
  set('v-zip', '郵便番号');
  set('v-addr', '住所');
  set('v-station', '最寄駅');
  
  // TEL/DI結合
  const tel = kv['TEL'] || '';
  const di = kv['DI'] || '';
  const teldi = (tel || di) ? `${tel}／${di}` : '—';
  set('v-teldi', null, teldi);
  
  set('v-family', 'ファミレス');

  // ページ2
  set('v2-code', 'コード');
  set('v2-hospital', '病院名');
  set('v2-tel', 'TEL');
  set('v2-di', 'DI');
}

/* ===== メタ情報同期 ===== */
function syncMetaFields() {
  const get = id => {
    const el = document.getElementById(id);
    return el ? el.textContent : '';
  };

  // ページ2にコピー
  const code = get('v-code');
  const hospital = get('v-hospital');
  const teldi = get('v-teldi');
  
  const el2Code = document.getElementById('v2-code');
  if (el2Code) el2Code.textContent = code;
  
  const el2Hospital = document.getElementById('v2-hospital');
  if (el2Hospital) el2Hospital.textContent = hospital;
  
  // TEL/DI分割
  if (teldi && teldi !== '—') {
    const parts = teldi.split('／');
    const tel = (parts[0] || '').trim();
    const di = (parts[1] || '').trim();
    
    const el2Tel = document.getElementById('v2-tel');
    if (el2Tel) el2Tel.textContent = tel || '—';
    
    const el2Di = document.getElementById('v2-di');
    if (el2Di) el2Di.textContent = di || '—';
  }
}

console.log('✅ main.js ロード完了');