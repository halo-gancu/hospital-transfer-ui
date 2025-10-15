/* ===== メイン初期化処理 ===== */
async function initApp() {
  if (window.innerWidth < 768) {
    const warning = document.getElementById('mobile-warning');
    if (warning) {
      warning.style.display = 'block';
    }
  }

  // 各機能初期化
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
  console.log('🚀 アプリケーション起動');

  try {
    const response = await fetch('/api/session');
    if (response.ok) {
      const data = await response.json();
      if (data.ok && data.user) {
        currentUserId = data.user.id;
        currentUsername = data.user.username;
        console.log(`✅ ログイン済みユーザー: ${currentUsername} (ID: ${currentUserId})`);
        await initApp();
      } else {
        throw new Error('セッション情報が不正です。');
      }
    } else {
      console.log('🛑 未認証。ログインページにリダイレクトします。');
      window.location.href = '/login';
    }
  } catch (error) {
    console.error('セッション確認中にエラー:', error);
    setStatus('サーバーとの接続に失敗しました。ログインページに移動します。', 'error');
    setTimeout(() => { window.location.href = '/login'; }, 2000);
  }
});