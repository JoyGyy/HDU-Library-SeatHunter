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
  logEl.innerHTML = logs.map(line => renderLogEntry(line)).join('');
  logEl.scrollTop = logEl.scrollHeight;

  // 预约列表
  fetchBookings();
}

function renderLogEntry(line) {
  // 解析时间戳 [HH:MM:SS]
  const timeMatch = line.match(/^\[(\d{2}:\d{2}:\d{2})\]\s*(.+)$/);
  if (!timeMatch) {
    return `<div class="log-entry log-info">
      <span class="log-icon">📝</span>
      <span class="log-content">${escapeHtml(line)}</span>
    </div>`;
  }

  const time = timeMatch[1];
  const msg = timeMatch[2];

  // 根据内容判断类型和图标
  let type = 'log-info';
  let icon = '📋';

  if (msg.includes('成功') || msg.includes('✅')) {
    type = 'log-success';
    icon = '✅';
  } else if (msg.includes('失败') || msg.includes('❌') || msg.includes('异常')) {
    type = 'log-error';
    icon = '❌';
  } else if (msg.includes('过期') || msg.includes('重新登录') || msg.includes('刷新')) {
    type = 'log-warning';
    icon = '🔄';
  } else if (msg.includes('开始') || msg.includes('触发')) {
    icon = '🚀';
  } else if (msg.includes('完成')) {
    type = 'log-success';
    icon = '✨';
  } else if (msg.includes('已尝试') || msg.includes('次尝试')) {
    type = 'log-progress';
    icon = '⏳';
  } else if (msg.includes('预约日期') || msg.includes('自动预约')) {
    icon = '📅';
  } else if (msg.includes('登录')) {
    icon = '🔐';
  }

  // 高亮关键信息
  let content = escapeHtml(msg);
  content = content.replace(/(✅|❌)/g, '<strong>$1</strong>');
  content = content.replace(/(座位\d+)/g, '<strong>$1</strong>');
  content = content.replace(/(\d{4}-\d{2}-\d{2})/g, '<strong style="color:var(--info)">$1</strong>');
  content = content.replace(/(我|同伴)/g, '<strong style="color:var(--warn)">$1</strong>');

  return `<div class="log-entry ${type}">
    <span class="log-icon">${icon}</span>
    <span class="log-time">${time}</span>
    <span class="log-content">${content}</span>
  </div>`;
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
