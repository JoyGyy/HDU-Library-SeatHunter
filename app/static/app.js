// 轮询间隔（毫秒）
const POLL_INTERVAL = 5000;

// 状态轮询
async function fetchStatus() {
  try {
    const resp = await fetch('/api/auto/status');
    const data = await resp.json();
    updateUI(data);
  } catch (e) {
    console.error('获取状态失败:', e);
  }
}

function updateUI(data) {
  // 调度器状态
  const statusEl = document.getElementById('schedulerStatus');
  if (data.running) {
    statusEl.textContent = '运行中';
    statusEl.className = 'badge badge-on';
  } else {
    statusEl.textContent = '已停止';
    statusEl.className = 'badge badge-off';
  }

  // 目标座位
  document.getElementById('targetSeats').textContent =
    (data.target_seats || []).join(', ') || '-';
  document.getElementById('roomName').textContent = data.room_name || '-';

  // 时间表
  if (data.schedule) {
    document.getElementById('bookSchedule').textContent = data.schedule.book || '-';
    document.getElementById('checkinSchedule').textContent = data.schedule.checkin || '-';
  }

  // 执行结果
  document.getElementById('bookResult').textContent = data.last_book_result || '-';
  document.getElementById('checkinResult').textContent = data.last_checkin_result || '-';

  // 日志
  const logEl = document.getElementById('log');
  const logs = data.debug_log || [];
  document.getElementById('logCount').textContent = logs.length;
  logEl.innerHTML = logs.map(line =>
    `<div class="log-line">${escapeHtml(line)}</div>`
  ).join('');
  logEl.scrollTop = logEl.scrollHeight;

  // 预约列表
  fetchBookings();
}

async function fetchBookings() {
  try {
    const resp = await fetch('/api/auto/bookings');
    const data = await resp.json();
    const listEl = document.getElementById('bookingList');
    const bookings = data.bookings || [];

    if (bookings.length === 0) {
      listEl.innerHTML = '<div class="empty">暂无预约</div>';
      return;
    }

    listEl.innerHTML = `
      <table class="booking-table">
        <thead>
          <tr><th>用户</th><th>座位</th><th>时间</th><th>状态</th></tr>
        </thead>
        <tbody>
          ${bookings.map(b => `
            <tr>
              <td>${escapeHtml(b.user)}</td>
              <td>${escapeHtml(b.seatNum)}</td>
              <td>${escapeHtml(b.time)}</td>
              <td>${escapeHtml(b.status)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (e) {
    console.error('获取预约列表失败:', e);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])
  );
}

// 操作按钮
async function manualBook() {
  try {
    const resp = await fetch('/api/auto/book', { method: 'POST' });
    const data = await resp.json();
    alert(data.message || '操作已提交');
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
}

async function manualCheckin() {
  try {
    const resp = await fetch('/api/auto/checkin', { method: 'POST' });
    const data = await resp.json();
    alert(data.message || '操作已提交');
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
}

async function toggleScheduler() {
  try {
    const statusResp = await fetch('/api/auto/status');
    const status = await statusResp.json();
    const endpoint = status.running ? '/api/auto/stop' : '/api/auto/start';
    const resp = await fetch(endpoint, { method: 'POST' });
    const data = await resp.json();
    alert(data.message || '操作已完成');
    fetchStatus();
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
}

function manualRefresh() {
  fetchStatus();
}

// 启动轮询
fetchStatus();
setInterval(fetchStatus, POLL_INTERVAL);
