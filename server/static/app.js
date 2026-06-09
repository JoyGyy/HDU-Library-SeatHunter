/* ── 工具函数 ── */
function escHtml(str) {
  if (!str && str !== 0) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function qs(id) { return document.getElementById(id); }

function log(msg) {
  const c = qs('log');
  if (!c) return;
  const t = document.createElement('div');
  t.className = 'log-line';
  t.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  c.appendChild(t);
  c.scrollTop = c.scrollHeight;
  if (c.children.length > 200) c.removeChild(c.firstChild);
  const cnt = qs('logCount');
  if (cnt) cnt.textContent = c.children.length;
}

/* ── API 调用 ── */
function refreshStatus() {
  fetch('/api/auto/status')
    .then(r => r.json())
    .then(d => {
      // 登录状态
      const loginEl = qs('loginStatus');
      if (loginEl) {
        loginEl.textContent = d.logged_in ? '✅ 已登录' : '❌ 未登录';
        loginEl.className = 'badge ' + (d.logged_in ? 'badge-on' : 'badge-off');
      }
      // 调度状态
      const schedEl = qs('schedulerStatus');
      if (schedEl) {
        schedEl.textContent = d.running ? '🟢 运行中' : '🔴 已停止';
        schedEl.className = 'badge ' + (d.running ? 'badge-on' : 'badge-off');
      }
      // 目标座位
      const seatsEl = qs('targetSeats');
      if (seatsEl) seatsEl.textContent = (d.target_seats || []).join(', ') || '-';
      // 预约结果
      const bookResEl = qs('bookResult');
      if (bookResEl) bookResEl.textContent = d.last_book_result || '-';
      // 签到结果
      const checkResEl = qs('checkinResult');
      if (checkResEl) checkResEl.textContent = d.last_checkin_result || '-';
      // 后端调试日志
      if (d.debug_log && d.debug_log.length) {
        const logEl = qs('log');
        if (logEl) {
          // 只添加新的日志行
          const existing = logEl.querySelectorAll('.log-line.backend-log');
          const existingTexts = new Set();
          existing.forEach(el => existingTexts.add(el.textContent));
          d.debug_log.forEach(line => {
            if (!existingTexts.has(line)) {
              const t = document.createElement('div');
              t.className = 'log-line backend-log';
              t.textContent = line;
              logEl.appendChild(t);
            }
          });
          logEl.scrollTop = logEl.scrollHeight;
          const cnt = qs('logCount');
          if (cnt) cnt.textContent = logEl.children.length;
        }
      }
    })
    .catch(e => log('状态刷新失败: ' + e));
}

function loadBookings() {
  const tbody = qs('bookingList');
  if (!tbody) return;
  tbody.innerHTML = '<div class="empty">加载中…</div>';

  fetch('/api/auto/bookings')
    .then(r => r.json())
    .then(d => {
      const list = d.bookings || [];
      if (!list.length) {
        tbody.innerHTML = '<div class="empty">暂无预约</div>';
        return;
      }
      tbody.innerHTML = list.map(b => {
        // 时间显示：beginTime 已经格式化为 "YYYY-MM-DD HH:MM"
        const timeStr = b.beginTime
          ? (b.endTime ? `${b.beginTime} ~ ${b.endTime}` : b.beginTime)
          : '时间未知';
        const statusClass = b.status === '已签到' ? 'status-active' :
          b.status === '待签到' ? 'status-pending' : 'status-ended';
        return `<div class="booking-item">
          <div class="booking-header">
            <span class="booking-user">${escHtml(b.user)}</span>
            <span class="badge ${statusClass}">${escHtml(b.status)}</span>
          </div>
          <div class="booking-detail">${escHtml(b.roomName)} 座位 ${escHtml(b.seatNum)}</div>
          <div class="booking-time">${escHtml(timeStr)}</div>
        </div>`;
      }).join('');
    })
    .catch(e => {
      tbody.innerHTML = '<div class="empty">加载失败</div>';
      log('预约列表加载失败: ' + e);
    });
}

function manualBook() {
  if (!confirm('确认立即预约？')) return;
  log('手动预约…');
  fetch('/api/auto/book', { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      log('预约请求: ' + (d.message || JSON.stringify(d)));
      // 等待后台任务执行
      setTimeout(refreshStatus, 3000);
      setTimeout(loadBookings, 5000);
    })
    .catch(e => log('预约失败: ' + e));
}

function manualCheckin() {
  if (!confirm('确认立即签到？')) return;
  log('手动签到…');
  fetch('/api/auto/checkin', { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      log('签到请求: ' + (d.message || JSON.stringify(d)));
      setTimeout(refreshStatus, 3000);
      setTimeout(loadBookings, 5000);
    })
    .catch(e => log('签到失败: ' + e));
}

function toggleScheduler() {
  const btn = qs('toggleBtn');
  const isRunning = btn && btn.textContent.includes('停止');
  const url = isRunning ? '/api/auto/stop' : '/api/auto/start';
  log(isRunning ? '停止调度器…' : '启动调度器…');
  fetch(url, { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      log(d.message || JSON.stringify(d));
      refreshStatus();
    })
    .catch(e => log('操作失败: ' + e));
}

function manualRefresh() {
  log('手动刷新…');
  refreshStatus();
  loadBookings();
}

/* ── 初始化 ── */
document.addEventListener('DOMContentLoaded', () => {
  refreshStatus();
  loadBookings();
  setInterval(() => {
    refreshStatus();
    loadBookings();
  }, 30000);
});
