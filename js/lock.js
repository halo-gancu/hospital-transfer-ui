/* ===== ロックAPI検出 ===== */
async function detectLockAPI() {
  try {
    const r = await fetch(`${API}/api/lock/status`);
    const j = await safeJSON(r);
    if (r.ok && j.ok) {
      LOCK_AVAILABLE = true;
      console.log('✅ Lock API enabled');
      currentLocks = j.locks || {};
      updateActiveUsersCount();
    } else {
      LOCK_AVAILABLE = false;
      console.log('⚠️ Lock API not available');
    }
  } catch (e) {
    LOCK_AVAILABLE = false;
    console.log('⚠️ Lock API error:', e);
  }
}

/* ===== ハートビート（生存確認） ===== */
function startHeartbeat() {
  if (!LOCK_AVAILABLE || !currentLockCode) return;
  stopHeartbeat();
  heartbeatInterval = setInterval(async () => {
    if (currentLockCode) {
      try {
        await fetch(`${API}/api/lock/heartbeat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            code: currentLockCode,
            user_id: currentUserId,
            timestamp: Date.now()
          })
        });
      } catch (e) {
        console.warn('Heartbeat failed:', e);
      }
    }
  }, 30000); // 30秒ごと
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
  }
}

/* ===== ロック取得・解放 ===== */
async function acquireLock(code) {
  if (!LOCK_AVAILABLE) return true;

  const existingLock = currentLocks[code];
  if (existingLock && existingLock.user_id !== currentUserId) {
    setStatus(`このコードは ${existingLock.username || existingLock.user_id} が使用中です`, 'error');
    return false;
  }

  try {
    const r = await fetch(`${API}/api/lock/acquire`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, user_id: currentUserId, username: currentUsername })
    });
    const j = await safeJSON(r);

    if (r.ok && j.ok) {
      currentLockCode = code;
      currentLocks[code] = { user_id: currentUserId, username: currentUsername };
      decorateCodeSelect();
      updateActiveUsersCount();
      startHeartbeat();
      return true;
    }

    if (j._nonjson || j._parseError) {
      LOCK_AVAILABLE = false;
      currentLockCode = null;
      currentLocks = {};
      decorateCodeSelect();
      setStatus('ロックAPIが無効のためロック無しで続行します。', 'success');
      return true;
    }

    setStatus('ロック取得に失敗しました', 'error');
    return false;
  } catch (e) {
    LOCK_AVAILABLE = false;
    currentLockCode = null;
    currentLocks = {};
    decorateCodeSelect();
    setStatus('ロックAPIに接続できないためロック無しで続行します。', 'success');
    return true;
  }
}

async function releaseLock(code) {
  if (!code) return;
  stopHeartbeat();
  if (!LOCK_AVAILABLE) {
    currentLockCode = null;
    return;
  }

  try {
    const payload = JSON.stringify({ code, user_id: currentUserId });
    if (document.visibilityState === 'hidden') {
      const blob = new Blob([payload], { type: 'application/json' });
      navigator.sendBeacon?.(`${API}/api/lock/release`, blob);
    } else {
      await fetch(`${API}/api/lock/release`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload
      });
    }
  } catch (e) {
    console.warn('ロック解除エラー:', e);
  } finally {
    if (currentLocks[code] && currentLocks[code].user_id === currentUserId) {
      delete currentLocks[code];
    }
    if (currentLockCode === code) currentLockCode = null;
    decorateCodeSelect();
    updateActiveUsersCount();
  }
}

/* ===== ロック一覧取得 ===== */
async function fetchLocks() {
  if (!LOCK_AVAILABLE) return;
  try {
    const r = await fetch(`${API}/api/lock/status`);
    const j = await safeJSON(r);
    if (r.ok && j.ok && j.locks) {
      currentLocks = j.locks;
      updateActiveUsersCount();
    }
  } catch (e) {
    console.warn('ロック一覧の取得に失敗:', e);
  }
}

/* ===== コード選択肢の装飾 ===== */
function decorateCodeSelect() {
  const codeSel = document.getElementById('codeSelect');
  if (!codeSel) return;

  const selected = codeSel.value;
  [...codeSel.options].forEach(opt => {
    if (!opt.value) return;

    const baseText = opt.getAttribute('data-base-text') || opt.textContent;
    opt.setAttribute('data-base-text', baseText);

    if (LOCK_AVAILABLE) {
      const lock = currentLocks[opt.value];
      if (lock && lock.user_id && lock.user_id !== currentUserId) {
        const lockTime = lock.locked_at ? new Date(lock.locked_at) : null;
        const timeInfo = lockTime ? ` (${formatLockTime(lockTime)})` : '';
        opt.textContent = `${baseText} 🔒 ${lock.username || lock.user_id}${timeInfo}`;
        opt.disabled = true;
        opt.style.color = '#999';
        opt.style.fontStyle = 'italic';
        opt.style.textDecoration = 'line-through';
      } else {
        opt.textContent = baseText;
        opt.disabled = false;
        opt.style.color = '';
        opt.style.fontStyle = '';
        opt.style.textDecoration = '';
      }
    } else {
      opt.textContent = baseText;
      opt.disabled = false;
      opt.style.color = '';
      opt.style.fontStyle = '';
    }
  });

  if (currentLockCode) {
    const opt = [...codeSel.options].find(o => o.value === currentLockCode);
    if (opt) {
      opt.disabled = false;
      opt.style.color = '#28a745';
      opt.style.fontWeight = 'bold';
      opt.style.textDecoration = '';
    }
  }

  codeSel.value = selected;
}

function formatLockTime(lockTime) {
  const now = new Date();
  const diff = Math.floor((now - lockTime) / 1000 / 60);
  if (diff < 1) return '今';
  if (diff < 60) return `${diff}分前`;
  const hours = Math.floor(diff / 60);
  if (hours < 24) return `${hours}時間前`;
  const days = Math.floor(hours / 24);
  return `${days}日前`;
}

/* ===== Socket.IO初期化 ===== */
function initSocket() {
  socket = io(API, { transports: ['websocket', 'polling'] });

  socket.on('connect', () => {
    console.log('🔌 Socket.IO接続成功');
    socket.emit('user_join', { user_id: currentUserId, username: currentUsername });
  });

  socket.on('disconnect', () => {
    console.log('🔌 Socket.IO切断');
  });

  socket.on('lock_acquired', (payload) => {
    if (!LOCK_AVAILABLE || !payload || !payload.code) return;
    console.log('🔒 ロック取得通知:', payload);
    currentLocks[payload.code] = payload.user || { user_id: 'unknown' };
    decorateCodeSelect();
    updateActiveUsersCount();
    updateActiveUsersList(); // ← 追加：リアルタイム更新
  });

  socket.on('lock_released', (payload) => {
    if (!LOCK_AVAILABLE || !payload || !payload.code) return;
    console.log('🔓 ロック解放通知:', payload);
    delete currentLocks[payload.code];
    decorateCodeSelect();
    updateActiveUsersCount();
    updateActiveUsersList(); // ← 追加：リアルタイム更新
  });

  socket.on('lock_status_update', (payload) => {
    if (!LOCK_AVAILABLE || !payload) return;
    console.log('📊 ロック状態更新:', payload);
    currentLocks = payload.locks || {};
    decorateCodeSelect();
    updateActiveUsersCount();
    updateActiveUsersList(); // ← 追加：リアルタイム更新
  });
}

/* ===== 作業中ユーザーパネル ===== */
function updateActiveUsersCount() {
  const count = Object.keys(currentLocks).length;
  const countEl = document.getElementById('active-users-count');
  if (countEl) countEl.textContent = count;
}

function toggleActiveUsersPanel() {
  const panel = document.getElementById('active-users-panel');
  if (panel.style.display === 'none' || !panel.style.display) {
    updateActiveUsersList();
    panel.style.display = 'block';
  } else {
    panel.style.display = 'none';
  }
}

/* ===== 病院名取得ヘルパー関数 ===== */
function getHospitalName(code) {
  // codeSelectから病院名を取得
  const codeSel = document.getElementById('codeSelect');
  if (codeSel) {
    const option = [...codeSel.options].find(opt => opt.value === code);
    if (option) {
      const baseText = option.getAttribute('data-base-text') || option.textContent;
      // 「コード - 病院名」形式から病院名を抽出
      const match = baseText.match(/^\s*[\w\-]+\s*-\s*(.+)$/);
      return match ? match[1].trim() : baseText;
    }
  }
  
  // hospitalDataから取得（グローバル変数がある場合）
  if (typeof hospitalData !== 'undefined' && hospitalData && hospitalData[code]) {
    return hospitalData[code]['病院名'] || hospitalData[code].hospital || code;
  }
  
  return code; // 見つからない場合はコードを返す
}

function updateActiveUsersList() {
  const list = document.getElementById('active-users-list');
  if (!list) return;

  if (Object.keys(currentLocks).length === 0) {
    list.innerHTML = '<p style="color: #999; margin: 0;">現在作業中のユーザーはいません</p>';
    return;
  }

  let html = '<ul style="margin: 0; padding-left: 20px; list-style: none;">';
  for (const [code, lock] of Object.entries(currentLocks)) {
    const username = lock.username || lock.user_id || '不明';
    const hospitalName = getHospitalName(code); // ← 病院名を取得
    const time = lock.locked_at ? formatLockTime(new Date(lock.locked_at)) : '';
    const isSelf = lock.user_id === currentUserId;
    const selfBadge = isSelf ? '<span style="background:#28a745;color:white;padding:2px 6px;border-radius:3px;font-size:10px;margin-left:5px;">あなた</span>' : '';

    html += `<li style="margin-bottom: 12px; padding: 8px; background: ${isSelf ? '#e8f5e9' : '#f8f9fa'}; border-radius: 6px; border-left: 3px solid ${isSelf ? '#28a745' : '#667eea'};">
      <div style="display: flex; align-items: center; margin-bottom: 4px;">
        <strong style="font-size: 14px; color: #333;">👤 ${username}</strong>${selfBadge}
      </div>
      <div style="font-size: 13px; color: #555; margin-bottom: 2px;">
        🏥 <strong>${hospitalName}</strong>
      </div>
      <div style="font-size: 11px; color: #666;">
        📋 コード: ${code}
        ${time ? `<span style="color: #999;"> • ${time}</span>` : ''}
      </div>
    </li>`;
  }
  html += '</ul>';
  list.innerHTML = html;
}