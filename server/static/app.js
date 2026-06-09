// API 基础地址（同源）
const API_BASE = '/api';

// 全局状态
let enginePollTimer = null;

// 工具函数
function $(id) {
  return document.getElementById(id);
}

function showToast(msg, duration = 2000) {
  const toast = $('toast');
  toast.textContent = msg;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), duration);
}

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API_BASE + path, opts);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `请求失败 (${res.status})`);
  }
  return data;
}

// ==================== 页面导航 ====================

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === name);
  });
  document.querySelectorAll('.tab-content').forEach(c => {
    c.classList.toggle('active', c.id === `tab-${name}`);
  });
  // 加载数据
  if (name === 'bookings') loadBookings();
  if (name === 'plans') loadPlans();
  if (name === 'scheduler') { loadSchedules(); startEnginePolling(); }
  if (name === 'friends') loadFriends();
  if (name !== 'scheduler') stopEnginePolling();
}

// ==================== 登录 ====================

async function handleLogin() {
  const studentId = $('student-id').value.trim();
  const password = $('password').value.trim();
  const errorEl = $('login-error');
  const btn = $('login-btn');

  if (!studentId || !password) {
    errorEl.textContent = '请输入学号和密码';
    return;
  }

  errorEl.textContent = '';
  btn.disabled = true;
  btn.textContent = '登录中...';

  try {
    const data = await request('POST', '/auth/login', {
      student_id: studentId,
      password: password,
    });
    if (data.success) {
      saveCredentials();
      $('user-name').textContent = `已登录: ${data.name}`;
      $('settings-user-name').textContent = `${data.name} (${studentId})`;
      showMainPage();
      loadBookings();
    } else {
      errorEl.textContent = data.message || '登录失败';
    }
  } catch (err) {
    errorEl.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '登 录';
  }
}

async function handleLogout() {
  try { await request('POST', '/auth/logout'); } catch {}
  showLoginPage();
}

function showMainPage() {
  $('login-page').classList.add('hidden');
  $('main-page').classList.remove('hidden');
}

function showLoginPage() {
  $('main-page').classList.add('hidden');
  $('login-page').classList.remove('hidden');
  $('password').value = '';
}

// ==================== 记住密码 ====================

function saveCredentials() {
  const remember = $('remember-me').checked;
  if (remember) {
    localStorage.setItem('seathunter_student_id', $('student-id').value);
    localStorage.setItem('seathunter_password', btoa($('password').value));
    localStorage.setItem('seathunter_remember', 'true');
  } else {
    localStorage.removeItem('seathunter_student_id');
    localStorage.removeItem('seathunter_password');
    localStorage.removeItem('seathunter_remember');
  }
}

function loadCredentials() {
  const remember = localStorage.getItem('seathunter_remember') === 'true';
  if (remember) {
    $('student-id').value = localStorage.getItem('seathunter_student_id') || '';
    $('password').value = atob(localStorage.getItem('seathunter_password') || '');
    $('remember-me').checked = true;
  }
}

async function autoLogin() {
  const remember = localStorage.getItem('seathunter_remember') === 'true';
  const studentId = localStorage.getItem('seathunter_student_id');
  const password = localStorage.getItem('seathunter_password');
  if (!remember || !studentId || !password) return false;
  try {
    const data = await request('POST', '/auth/login', {
      student_id: studentId,
      password: atob(password),
    });
    if (data.success) {
      $('user-name').textContent = `已登录: ${data.name}`;
      $('settings-user-name').textContent = `${data.name} (${studentId})`;
      showMainPage();
      loadBookings();
      return true;
    }
  } catch {}
  return false;
}

// ==================== 预约 ====================

async function loadBookings() {
  const list = $('bookings-list');
  list.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const data = await request('GET', '/bookings');
    if (!data.bookings || data.bookings.length === 0) {
      list.innerHTML = '<div class="empty">暂无预约</div>';
      return;
    }
    list.innerHTML = data.bookings.map(b => `
      <div class="card">
        <div class="card-title">${b.room_name || '未知房间'} ${b.seat_num ? '- ' + b.seat_num + ' 号座' : ''}</div>
        <div class="card-info">
          时间: ${formatTime(b.begin_time)} ~ ${formatTime(b.end_time)}<br>
          状态: <span class="status-badge ${getStatusClass(b.status)}">${b.status || '-'}</span>
          ${b.booking_id ? '<br>ID: ' + b.booking_id : ''}
        </div>
        ${b.booking_id ? `
        <div class="card-actions">
          <button class="btn small primary" onclick="doCheckin('${b.booking_id}')">签到</button>
        </div>` : ''}
      </div>
    `).join('');
  } catch (err) {
    list.innerHTML = `<div class="empty">加载失败: ${err.message}</div>`;
  }
}

function getStatusClass(status) {
  if (!status) return '';
  if (status.includes('成功') || status.includes('confirmed')) return 'success';
  if (status.includes('待') || status.includes('pending')) return 'pending';
  return 'error';
}

function formatTime(t) {
  if (!t) return '-';
  // ISO datetime → HH:MM
  if (typeof t === 'string' && t.includes('T')) {
    try {
      const d = new Date(t);
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } catch { return t; }
  }
  return t;
}

async function doCheckin(bookingId) {
  try {
    const data = await request('POST', `/checkin/do/${bookingId}`);
    showToast(data.message || '签到成功');
    loadBookings();
  } catch (err) {
    showToast('签到失败: ' + err.message);
  }
}

// ==================== 方案 ====================

async function loadPlans() {
  const list = $('plans-list');
  list.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const data = await request('GET', '/plans');
    if (!data.plans || data.plans.length === 0) {
      list.innerHTML = '<div class="empty">暂无方案，点击右上角创建</div>';
      return;
    }
    list.innerHTML = data.plans.map(p => `
      <div class="card">
        <div class="card-title">${p.name || p.id || '未命名方案'}</div>
        <div class="card-info">
          房间: ${p.room_name || '-'}<br>
          楼层: ${p.floor_name || '-'}<br>
          座位: ${(p.seats || []).map(s => s.seat_num || s.seat_id).join(', ') || '-'}<br>
          时间: ${p.begin_time || '-'}，时长: ${p.duration_hours || '-'} 小时
        </div>
        <div class="card-actions">
          <button class="btn small danger" onclick="deletePlan('${p.id}')">删除</button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    list.innerHTML = `<div class="empty">加载失败: ${err.message}</div>`;
  }
}

async function showCreatePlan() {
  $('create-plan-modal').classList.remove('hidden');
  $('plan-name').value = '';
  $('plan-begin-time').value = '08:00';
  $('plan-duration').value = '4';
  // 加载房间列表
  try {
    const data = await request('GET', '/rooms');
    const select = $('plan-room');
    select.innerHTML = '<option value="">选择房间</option>';
    (data.rooms || []).forEach(r => {
      select.innerHTML += `<option value="${r}">${r}</option>`;
    });
  } catch (err) {
    showToast('加载房间失败: ' + err.message);
  }
  $('plan-floor').innerHTML = '<option value="">选择楼层</option>';
  $('plan-seat').innerHTML = '<option value="">选择座位</option>';
}

function hideCreatePlan() {
  $('create-plan-modal').classList.add('hidden');
}

async function onRoomChange() {
  const room = $('plan-room').value;
  const floorSelect = $('plan-floor');
  const seatSelect = $('plan-seat');
  floorSelect.innerHTML = '<option value="">选择楼层</option>';
  seatSelect.innerHTML = '<option value="">选择座位</option>';
  if (!room) return;
  try {
    const data = await request('GET', `/rooms/${encodeURIComponent(room)}/floors`);
    (data.floors || []).forEach(f => {
      floorSelect.innerHTML += `<option value="${f}">${f}</option>`;
    });
  } catch (err) {
    showToast('加载楼层失败: ' + err.message);
  }
}

async function onFloorChange() {
  const room = $('plan-room').value;
  const floor = $('plan-floor').value;
  const seatSelect = $('plan-seat');
  seatSelect.innerHTML = '<option value="">选择座位</option>';
  if (!room || !floor) return;
  try {
    const data = await request('GET', `/rooms/${encodeURIComponent(room)}/floors/${encodeURIComponent(floor)}/seats`);
    (data.seats || []).forEach(s => {
      const label = s.title || s.seatNum || s.seat_num || s.id || s.seatId || '未知';
      const value = s.id || s.seatId || s.seat_id || '';
      seatSelect.innerHTML += `<option value="${value}">${label}</option>`;
    });
  } catch (err) {
    showToast('加载座位失败: ' + err.message);
  }
}

async function createPlan() {
  const name = $('plan-name').value.trim();
  const room = $('plan-room').value;
  const floor = $('plan-floor').value;
  const seatId = $('plan-seat').value;
  const seatNum = $('plan-seat').options[$('plan-seat').selectedIndex]?.text || '';
  const beginTime = $('plan-begin-time').value;
  const duration = parseInt($('plan-duration').value);

  if (!room || !floor || !seatId) {
    showToast('请选择房间、楼层和座位');
    return;
  }

  // 生成唯一 ID
  const planId = 'plan_' + Date.now();

  try {
    await request('POST', '/plans', {
      id: planId,
      name: name || `${room} ${seatNum}`,
      room_name: room,
      floor_name: floor,
      begin_time: beginTime + ':00',
      duration_hours: duration,
      seats: [{ seat_id: seatId, seat_num: seatNum }],
    });
    showToast('方案创建成功');
    hideCreatePlan();
    loadPlans();
  } catch (err) {
    showToast('创建失败: ' + err.message);
  }
}

async function deletePlan(planId) {
  if (!confirm('确定删除该方案？')) return;
  try {
    await request('DELETE', `/plans/${planId}`);
    showToast('已删除');
    loadPlans();
  } catch (err) {
    showToast('删除失败: ' + err.message);
  }
}

// ==================== 调度 ====================

async function loadSchedules() {
  const list = $('schedules-list');
  list.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const data = await request('GET', '/schedules');
    if (!data.schedules || data.schedules.length === 0) {
      list.innerHTML = '<div class="empty">暂无定时任务</div>';
      return;
    }
    const weekNames = ['日','一','二','三','四','五','六'];
    list.innerHTML = data.schedules.map((s, idx) => {
      let trigger = '';
      if (s.mode === 'weekday') {
        const days = (s.target_weekdays || []).map(d => '周' + weekNames[d]).join('、');
        trigger = `每${days}`;
      } else {
        const dates = (s.mappings || []).map(m => m.target_date).join('、');
        trigger = dates || '指定日期';
      }
      const planIds = (s.plan_ids || []).join(', ');
      return `
        <div class="card">
          <div class="card-title">方案: ${planIds || '未指定'}</div>
          <div class="card-info">
            触发: ${trigger}<br>
            状态: ${s.enabled ? '✅ 启用' : '⏸ 禁用'}
          </div>
          <div class="card-actions">
            <button class="btn small danger" onclick="deleteSchedule(${idx})">删除</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    list.innerHTML = `<div class="empty">加载失败: ${err.message}</div>`;
  }
}

async function showAddSchedule() {
  $('add-schedule-modal').classList.remove('hidden');
  $('schedule-date-group').classList.add('hidden');
  $('schedule-weekday-group').classList.remove('hidden');
  $('schedule-time').value = '07:30';
  // 加载方案列表
  try {
    const data = await request('GET', '/plans');
    const select = $('schedule-plan');
    select.innerHTML = '<option value="">选择方案</option>';
    (data.plans || []).forEach(p => {
      select.innerHTML += `<option value="${p.id}">${p.name || p.id}</option>`;
    });
  } catch (err) {
    showToast('加载方案失败: ' + err.message);
  }
}

function hideAddSchedule() {
  $('add-schedule-modal').classList.add('hidden');
}

function onScheduleTypeChange() {
  const type = $('schedule-type').value;
  if (type === 'weekday') {
    $('schedule-weekday-group').classList.remove('hidden');
    $('schedule-date-group').classList.add('hidden');
  } else {
    $('schedule-weekday-group').classList.add('hidden');
    $('schedule-date-group').classList.remove('hidden');
  }
}

async function addSchedule() {
  const planId = $('schedule-plan').value;
  const type = $('schedule-type').value;
  const time = $('schedule-time').value;

  if (!planId) {
    showToast('请选择方案');
    return;
  }

  // 构建符合 API 格式的 body
  const body = {
    mode: type, // 'weekday' 或 'date'
    enabled: true,
    plan_ids: [planId],
    target_weekdays: [],
    mappings: [],
  };

  if (type === 'weekday') {
    body.target_weekdays = [parseInt($('schedule-weekday').value)];
  } else {
    const dateVal = $('schedule-date').value;
    if (!dateVal) {
      showToast('请选择日期');
      return;
    }
    body.mappings = [{ target_date: dateVal, plan_ids: [planId] }];
  }

  try {
    await request('POST', '/schedules', body);
    showToast('定时任务添加成功');
    hideAddSchedule();
    loadSchedules();
  } catch (err) {
    showToast('添加失败: ' + err.message);
  }
}

async function deleteSchedule(scheduleId) {
  if (!confirm('确定删除该定时任务？')) return;
  try {
    await request('DELETE', `/schedules/${scheduleId}`);
    showToast('已删除');
    loadSchedules();
  } catch (err) {
    showToast('删除失败: ' + err.message);
  }
}

// ==================== 引擎 ====================

async function loadEngineStatus() {
  try {
    const data = await request('GET', '/schedules/status');
    const statusEl = $('engine-status');
    const nextEl = $('engine-next-trigger');
    const countdownEl = $('engine-countdown');
    const startBtn = $('engine-start-btn');
    const stopBtn = $('engine-stop-btn');

    if (data.running) {
      statusEl.textContent = '运行中';
      statusEl.className = 'status-badge success';
      nextEl.textContent = data.trigger_time || '-';
      if (data.remaining_seconds != null) {
        const min = Math.floor(data.remaining_seconds / 60);
        const sec = data.remaining_seconds % 60;
        countdownEl.textContent = `${min}分${sec}秒`;
      } else {
        countdownEl.textContent = '-';
      }
      startBtn.disabled = true;
      stopBtn.disabled = false;
    } else {
      statusEl.textContent = '已停止';
      statusEl.className = 'status-badge error';
      nextEl.textContent = '-';
      countdownEl.textContent = '-';
      startBtn.disabled = false;
      stopBtn.disabled = true;
    }
  } catch {}
}

function startEnginePolling() {
  loadEngineStatus();
  if (enginePollTimer) return;
  enginePollTimer = setInterval(loadEngineStatus, 5000);
}

function stopEnginePolling() {
  if (enginePollTimer) {
    clearInterval(enginePollTimer);
    enginePollTimer = null;
  }
}

async function startEngine() {
  try {
    const data = await request('POST', '/schedules/start');
    showToast(data.message || '引擎已启动');
    loadEngineStatus();
  } catch (err) {
    showToast('启动失败: ' + err.message);
  }
}

async function stopEngine() {
  try {
    const data = await request('POST', '/schedules/stop');
    showToast(data.message || '引擎已停止');
    loadEngineStatus();
  } catch (err) {
    showToast('停止失败: ' + err.message);
  }
}

// ==================== 好友 ====================

async function loadFriends() {
  const list = $('friends-list');
  list.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const data = await request('GET', '/friends');
    if (!data.friends || data.friends.length === 0) {
      list.innerHTML = '<div class="empty">暂无好友，点击右上角添加</div>';
      return;
    }
    list.innerHTML = data.friends.map(f => `
      <div class="card">
        <div class="card-title">${f.name || '未知'}</div>
        <div class="card-info">学号: ${f.student_id}</div>
        <div class="card-actions">
          <button class="btn small" onclick="testFriend('${f.student_id}')">测试登录</button>
          <button class="btn small danger" onclick="deleteFriend('${f.student_id}')">删除</button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    list.innerHTML = `<div class="empty">加载失败: ${err.message}</div>`;
  }
}

function showAddFriend() {
  $('add-friend-modal').classList.remove('hidden');
  $('friend-id').value = '';
  $('friend-password').value = '';
}

function hideAddFriend() {
  $('add-friend-modal').classList.add('hidden');
}

async function addFriend() {
  const studentId = $('friend-id').value.trim();
  const password = $('friend-password').value.trim();
  if (!studentId || !password) {
    showToast('请输入学号和密码');
    return;
  }
  try {
    await request('POST', '/friends', { student_id: studentId, password });
    showToast('添加成功');
    hideAddFriend();
    loadFriends();
  } catch (err) {
    showToast('添加失败: ' + err.message);
  }
}

async function testFriend(studentId) {
  showToast('测试中...');
  try {
    const data = await request('POST', `/friends/${studentId}/test`);
    showToast(data.message || '测试成功');
  } catch (err) {
    showToast('测试失败: ' + err.message);
  }
}

async function deleteFriend(studentId) {
  if (!confirm(`确定删除好友 ${studentId}？`)) return;
  try {
    await request('DELETE', `/friends/${studentId}`);
    showToast('已删除');
    loadFriends();
  } catch (err) {
    showToast('删除失败: ' + err.message);
  }
}

// ==================== 初始化 ====================

async function init() {
  try {
    const data = await request('GET', '/auth/status');
    if (data.logged_in) {
      $('user-name').textContent = `已登录: ${data.name}`;
      $('settings-user-name').textContent = `${data.name} (${data.student_id})`;
      showMainPage();
      loadBookings();
      return;
    }
  } catch {}
  loadCredentials();
  await autoLogin();
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !$('login-page').classList.contains('hidden')) {
    handleLogin();
  }
});

init();
