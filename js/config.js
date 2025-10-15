/* ===== グローバル変数 ===== */
const API = location.origin;

// データ管理
let currentData = null;
let currentUserId = null;
let currentUsername = null;
let isLoadingData = false;

// Excel風選択機能
let selRect = null;
let anchor = null;
let isDown = false;
let isDrag = false;
let editingCell = null;

// 排他ロック機能
let socket = null;
let currentLockCode = null;
let currentLocks = {};
let LOCK_AVAILABLE = false;
let heartbeatInterval = null;

// 未保存警告
window.isDirty = false;

/* ===== 定数 ===== */
// デフォルト行数
const DEFAULT_ROWS = {
  main: 26,
  facilities: 20,
  vendors: 30
};

// 都道府県コード
const PREFS = [
  ["01", "北海道"], ["02", "青森県"], ["03", "岩手県"], ["04", "宮城県"],
  ["05", "秋田県"], ["06", "山形県"], ["07", "福島県"], ["08", "茨城県"],
  ["09", "栃木県"], ["10", "群馬県"], ["11", "埼玉県"], ["12", "千葉県"],
  ["13", "東京都"], ["14", "神奈川県"], ["15", "新潟県"], ["16", "富山県"],
  ["17", "石川県"], ["18", "福井県"], ["19", "山梨県"], ["20", "長野県"],
  ["21", "岐阜県"], ["22", "静岡県"], ["23", "愛知県"], ["24", "三重県"],
  ["25", "滋賀県"], ["26", "京都府"], ["27", "大阪府"], ["28", "兵庫県"],
  ["29", "奈良県"], ["30", "和歌山県"], ["31", "鳥取県"], ["32", "島根県"],
  ["33", "岡山県"], ["34", "広島県"], ["35", "山口県"], ["36", "徳島県"],
  ["37", "香川県"], ["38", "愛媛県"], ["39", "高知県"], ["40", "福岡県"],
  ["41", "佐賀県"], ["42", "長崎県"], ["43", "熊本県"], ["44", "大分県"],
  ["45", "宮崎県"], ["46", "鹿児島県"], ["47", "沖縄県"]
];

// テーブルキー定義
const TABLE_KEYS = {
  main: ['印', '卒業', 'Dr./出身大学', '診療科', 'PHS', '直PHS', '①', '②', '備考'],
  facilities: ['関連病院施設等', '関連病院TEL', '関連病院備考'],
  vendors: ['部署', '業者', '内線', 'TEL・メモ']
};

// 自動ログアウト設定
const IDLE_TIMEOUT = 20 * 60 * 1000; // 20分
const WARNING_BEFORE = 2 * 60 * 1000; // 2分前に警告
let idleTimer = null;

/* ===== ユーティリティ関数 ===== */
// シリーズキー生成
const seriesKey = (base, index) => `${base}_${index}`;
const readSeries = (kv, base, index) => kv[seriesKey(base, index)] ?? "";
const writeSeries = (payload, base, index, value) => payload[seriesKey(base, index)] = value;