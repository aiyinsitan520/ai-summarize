const form = document.getElementById('task-form');
const message = document.getElementById('form-message');
const resultCard = document.getElementById('result-card');
const taskList = document.getElementById('task-list');
const providerStatus = document.getElementById('provider-status');
let activeTask = null;
let timer = null;

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

function showTask(task) {
  activeTask = task.id;
  resultCard.hidden = false;
  document.getElementById('video-title').textContent = task.result?.title || task.url;
  document.getElementById('video-meta').textContent = task.result
    ? `${task.platform} · ${task.result.uploader} · ${Math.round(task.result.duration_seconds / 60)} 分钟 · ${task.result.audio_segments} 段音频 · ${task.result.frames_analyzed} 张画面`
    : task.platform;
  document.getElementById('status-badge').textContent = task.status === 'completed' ? '已完成' : task.status === 'failed' ? '失败' : '处理中';
  document.getElementById('progress-fill').style.width = `${task.progress}%`;
  document.getElementById('stage').textContent = task.stage;
  const report = document.getElementById('report');
  report.hidden = !task.result;
  report.textContent = task.result?.report || '';
  const error = document.getElementById('error');
  error.hidden = !task.error;
  error.textContent = task.error || '';
  if (timer) clearTimeout(timer);
  if (task.status === 'queued' || task.status === 'running') {
    timer = setTimeout(async () => {
      try { showTask(await request(`/api/tasks/${task.id}`)); }
      catch (err) { message.textContent = err.message; }
    }, 1800);
  } else {
    loadHistory();
  }
}

async function loadHistory() {
  try {
    const tasks = await request('/api/tasks');
    taskList.replaceChildren();
    if (!tasks.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = '还没有任务';
      taskList.append(empty);
      return;
    }
    for (const task of tasks) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'task';
      const title = document.createElement('span');
      title.className = 'task-title';
      title.textContent = task.result?.title || task.url;
      const status = document.createElement('span');
      status.className = 'task-status';
      status.textContent = task.status === 'completed' ? '已完成' : task.status === 'failed' ? '失败' : '处理中';
      button.append(title, status);
      button.addEventListener('click', () => showTask(task));
      taskList.append(button);
    }
  } catch (err) { message.textContent = err.message; }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  message.textContent = '';
  const submit = document.getElementById('submit');
  submit.disabled = true;
  try {
    const task = await request('/api/tasks', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        url: document.getElementById('url').value,
        language: document.getElementById('language').value,
        focus: document.getElementById('focus').value,
      }),
    });
    showTask(task);
    loadHistory();
  } catch (err) { message.textContent = err.message; }
  finally { submit.disabled = false; }
});
document.getElementById('refresh').addEventListener('click', loadHistory);
request('/api/health').then((health) => {
  const ai = `${health.ai_provider} ${health.ai_key_configured ? '已配置' : '缺少密钥'}`;
  const asr = `${health.asr_provider} ${health.asr_key_configured ? '已配置' : '缺少密钥'}`;
  providerStatus.textContent = `画面与总结：${ai} · 语音转写：${asr}`;
}).catch(() => { providerStatus.textContent = '无法读取模型配置'; });
loadHistory();
