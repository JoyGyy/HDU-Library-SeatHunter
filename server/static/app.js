const API = '/api';
let logs = [];

function $(id) { return document.getElementById(id); }

function showToast(msg, duration = 2000) {
  const toast = $('toast');
  toast.textContent = msg;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), duration);
}

async function request(method, path, body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `请求失败 (${res.status})`);
  return data;
}

function addLog(msg, type = 'info') {
  const now = new Date().toLocaleTimeString('zh-CN');
  logs.unshift({ time: now, msg, type });
  if (logs.length > 50) logs.pop();
  renderLogs();
}

function renderLogs() {
  const el = $('log-list');
  if (logs.length === 0) {
    el.innerHTML = '<div class="loading">暂无日志</div>';
    return;
  }
  el.innerHTML = logs.map(l =>
    `<div class="log-item"><span class="log-time">${l.time}</span><span class="log-${l.type}">${l.msg}</span></div>`
  ).join('');
}

// 刷新状态
async function refreshStatus() {
  try {
    const data = await request('GET', '/auto/status');
    // 登录状态
    const loginEl = $('login-status');
    if (data.logged_in) {
      loginEl.textContent = `已登录 (${data.user_name || ''})`;
      loginEl.className = 'status-badge success';
    } else {
      loginEl.textContent = '未登录';
      loginEl.className = 'status-badge error';
    }
    // 预约状态
    const bookEl = $('book-status');
    if (data.auto_book_running) {
      bookEl.textContent = `运行中 (下次: ${data.next_book_time || '-'})`;
      bookEl.className = 'status-badge success';
    } else {
      bookEl.textContent = '已停止';
      bookEl.className = 'status-badge error';
    }
    // 签到状态
    const checkinEl = $('checkin-status');
    if (data.auto_checkin_running) {
      checkinEl.textContent = `运行中 (下次: ${data.next_checkin_time || '-'})`;
      checkinEl.className = 'status-badge success';
    } else {
      checkinEl.textContent = '已停止';
      checkinEl.className = 'status-badge error';
    }
  } catch (err) {
    addLog('状态刷新失败: ' + err.message, 'error');
  }
}

// 加载预约
async function loadBookings() {
  const el = $('bookings-list');
  el.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const data = await request('GET', '/auto/bookings');
    if (!data.bookings || data.bookings.length === 0) {
      el.innerHTML = '暂无预约';
      return;
    }
    el.innerHTML = data.bookings.map(b => {
      const statusClass = b.status === '已签到' ? 'success' : (b.status === '待签到' ? 'pending' : 'info');
      return `<div style="padding: 6px 0; border-bottom: 1px solid rgba(69,71,90,0.3);">
        <div>${b.user_name || ''} - ${b.room_name || '未知'} ${b.seat_num || ''}号座</div>
        <div style="font-size:13px; color: var(--subtext);">${b.time_range || ''} <span class="status-badge ${statusClass}">${b.status || ''}</span></div>
      </div>`;
    }).join('');
  } catch (err) {
    el.innerHTML = '加载失败: ' + err.message;
  }
}

// 手动预约
async function manualBook() {
  addLog('手动触发预约...');
  showToast('正在预约，请稍候...');
  try {
    const data = await request('POST', '/auto/book');
    addLog('预约完成: ' + data.message, data.success ? 'success' : 'error');
    showToast(data.message);
    loadBookings();
    refreshStatus();
  } catch (err) {
    addLog('预约失败: ' + err.message, 'error');
    showToast('预约失败: ' + err.message);
  }
}

// 手动签到
async function manualCheckin() {
  addLog('手动触发签到...');
  showToast('正在签到...');
  try {
    const data = await request('POST', '/auto/checkin');
    addLog('签到完成: ' + data.message, data.success ? 'success' : 'error');
    showToast(data.message);
    loadBookings();
  } catch (err) {
    addLog('签到失败: ' + err.message, 'error');
    showToast('签到失败: ' + err.message);
  }
}

// 初始化
async function init() {
  addLog('页面加载完成，正在初始化...');
  await refreshStatus();
  await loadBookings();
  addLog('初始化完成');

  // 每 30 秒刷新状态
  setInterval(() => {
    refreshStatus();
    loadBookings();
  }, 30000);
}

init();
