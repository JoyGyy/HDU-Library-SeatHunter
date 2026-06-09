// API 基础地址（同源，不需要配置）
const API_BASE = '/api';

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

// 页面切换
function switchTab(name) {
  // 更新导航按钮
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === name);
  });
  // 更新内容区域
  document.querySelectorAll('.tab-content').forEach(c => {
    c.classList.toggle('active', c.id === `tab-${name}`);
  });
  // 加载数据
  if (name === 'bookings') loadBookings();
  if (name === 'friends') loadFriends();
}

// 登录
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
      saveCredentials(); // 保存密码
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

// 登出
async function handleLogout() {
  try {
    await request('POST', '/auth/logout');
  } catch {}
  showLoginPage();
}

// 显示主页面
function showMainPage() {
  $('login-page').classList.add('hidden');
  $('main-page').classList.remove('hidden');
}

// 显示登录页面
function showLoginPage() {
  $('main-page').classList.add('hidden');
  $('login-page').classList.remove('hidden');
  $('password').value = '';
}

// 加载预约列表
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
          时间: ${b.begin_time || '-'} ~ ${b.end_time || '-'}<br>
          状态: <span class="status-badge ${getStatusClass(b.status)}">${b.status || '-'}</span>
          ${b.booking_id ? '<br>ID: ' + b.booking_id : ''}
        </div>
        ${b.booking_id ? `
        <div class="card-actions">
          <button class="btn small primary" onclick="doCheckin('${b.booking_id}')">签到</button>
        </div>
        ` : ''}
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

// 签到
async function doCheckin(bookingId) {
  try {
    const data = await request('POST', `/checkin/do/${bookingId}`);
    showToast(data.message || '签到成功');
    loadBookings();
  } catch (err) {
    showToast('签到失败: ' + err.message);
  }
}

// 加载好友列表
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

// 添加好友
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
    await request('POST', '/friends', {
      student_id: studentId,
      password: password,
    });
    showToast('添加成功');
    hideAddFriend();
    loadFriends();
  } catch (err) {
    showToast('添加失败: ' + err.message);
  }
}

// 测试好友登录
async function testFriend(studentId) {
  showToast('测试中...');
  try {
    const data = await request('POST', `/friends/${studentId}/test`);
    showToast(data.message || '测试成功');
  } catch (err) {
    showToast('测试失败: ' + err.message);
  }
}

// 删除好友
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

// 保存/读取密码
function saveCredentials() {
  const remember = $('remember-me').checked;
  if (remember) {
    localStorage.setItem('seathunter_student_id', $('student-id').value);
    localStorage.setItem('seathunter_password', btoa($('password').value)); // base64 编码
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

// 自动登录
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

// 页面初始化
async function init() {
  // 先尝试用已保存的 session
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

  // 加载保存的密码
  loadCredentials();

  // 尝试自动登录
  const autoLogged = await autoLogin();
  if (!autoLogged) {
    // 显示登录页，密码已填充
  }
}

// 回车键登录
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !$('login-page').classList.contains('hidden')) {
    handleLogin();
  }
});

// 启动
init();
