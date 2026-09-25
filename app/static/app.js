const form = document.getElementById('task-form');
const message = document.getElementById('form-message');
const resultCard = document.getElementById('result-card');
const taskList = document.getElementById('task-list');
const providerStatus = document.getElementById('provider-status');
let activeTask = null;
let activeResult = null;
let timer = null;

function transcriptText(result) {
  return (result?.transcript || [])
    .map((segment) => `[${segment.start}]\n${segment.text}`)
    .join('\n\n');
}

function downloadText(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

function showTask(task) {
  if (activeTask !== task.id) {
    document.getElementById('transcript').hidden = true;
    document.getElementById('toggle-transcript').setAttribute('aria-expanded', 'false');
    document.getElementById('toggle-transcript').textContent = '查看语音转写';
  }
  activeTask = task.id;
  activeResult = task.result;
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
  document.getElementById('result-actions').hidden = !task.result;
  document.getElementById('transcript').textContent = transcriptText(task.result) || '没有可用语音转写';
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
document.getElementById('toggle-transcript').addEventListener('click', () => {
  const transcript = document.getElementById('transcript');
  transcript.hidden = !transcript.hidden;
  const button = document.getElementById('toggle-transcript');
  button.setAttribute('aria-expanded', String(!transcript.hidden));
  button.textContent = transcript.hidden ? '查看语音转写' : '收起语音转写';
});
document.getElementById('download-report').addEventListener('click', () => {
  if (activeResult) downloadText(`${activeTask}-report.md`, activeResult.report, 'text/markdown;charset=utf-8');
});
document.getElementById('download-transcript').addEventListener('click', () => {
  if (activeResult) downloadText(`${activeTask}-transcript.txt`, transcriptText(activeResult), 'text/plain;charset=utf-8');
});
request('/api/health').then((health) => {
  const ai = `${health.ai_provider} ${health.ai_key_configured ? '已配置' : '缺少密钥'}`;
  const asr = `${health.asr_provider} ${health.asr_key_configured ? '已配置' : '缺少密钥'}`;
  providerStatus.textContent = `画面与总结：${ai} · 语音转写：${asr}`;
}).catch(() => { providerStatus.textContent = '无法读取模型配置'; });
loadHistory();
