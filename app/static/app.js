'use strict';

const form = document.getElementById('task-form');
const message = document.getElementById('form-message');
const resultCard = document.getElementById('result-card');
const taskList = document.getElementById('task-list');
const providerStatus = document.getElementById('provider-status');

const PLATFORM_LABELS = {
  youtube: 'YouTube', douyin: '抖音', tiktok: 'TikTok',
  bilibili: 'Bilibili', xiaohongshu: '小红书',
};
const STATUS_LABELS = {queued: '排队中', running: '处理中', completed: '已完成', failed: '失败'};

let activeTask = null;
let activeResult = null;
let timer = null;

/* ---------- 安全的 Markdown 渲染 ----------
   模型输出不可信任：先把整段文本做 HTML 转义，再解析 Markdown 结构，
   生成的所有标签均来自本文件，链接仅放行 http(s)。 */

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function safeUrl(url) {
  const trimmed = url.trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : null;
}

function renderInline(text) {
  const codeSpans = [];
  let out = text.replace(/`([^`\n]+)`/g, (_, code) => {
    codeSpans.push(code);
    return `\u0000${codeSpans.length - 1}\u0000`;
  });
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label, url) => {
    const href = safeUrl(url);
    return href
      ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
      : match;
  });
  out = out
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, '$1<em>$2</em>')
    .replace(/~~([^~\n]+)~~/g, '<del>$1</del>');
  return out.replace(/\u0000(\d+)\u0000/g, (_, index) => `<code>${codeSpans[Number(index)]}</code>`);
}

const CJK_EDGE = /[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]/;

function joinLines(parts) {
  return parts.reduce((acc, part) => {
    if (!acc) return part;
    const noSpace = CJK_EDGE.test(acc[acc.length - 1]) && CJK_EDGE.test(part[0]);
    return acc + (noSpace ? '' : ' ') + part;
  }, '');
}

function splitTableRow(row) {
  return row.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((cell) => cell.trim());
}

function isTableSeparator(line) {
  return /^[|:\-\s]+$/.test(line) && line.includes('-') && line.includes('|');
}

function renderList(items, ordered) {
  const root = {text: '', children: []};
  const stack = [{node: root, indent: -1}];
  for (const item of items) {
    const entry = {text: item.text, children: []};
    while (stack.length > 1 && item.indent <= stack[stack.length - 1].indent) stack.pop();
    stack[stack.length - 1].node.children.push(entry);
    stack.push({node: entry, indent: item.indent});
  }
  const toHtml = (node, useOrdered) => {
    if (!node.children.length) return '';
    const tag = useOrdered ? 'ol' : 'ul';
    const inner = node.children
      .map((child) => `<li>${renderInline(child.text)}${toHtml(child, false)}</li>`)
      .join('');
    return `<${tag}>${inner}</${tag}>`;
  };
  return toHtml(root, ordered);
}

function renderLines(lines) {
  const out = [];
  let paragraph = [];
  const flushParagraph = () => {
    if (paragraph.length) out.push(`<p>${renderInline(joinLines(paragraph))}</p>`);
    paragraph = [];
  };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { flushParagraph(); i += 1; continue; }
    if (/^`{3,}/.test(line.trim())) {
      flushParagraph();
      const code = [];
      i += 1;
      while (i < lines.length && !/^`{3,}/.test(lines[i].trim())) { code.push(lines[i]); i += 1; }
      i += 1;
      out.push(`<pre><code>${code.join('\n')}</code></pre>`);
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      const level = Math.min(heading[1].length, 4);
      out.push(`<h${level}>${renderInline(heading[2].trim())}</h${level}>`);
      i += 1;
      continue;
    }
    if (/^ {0,3}([-*_])\s*(?:\1\s*){2,}$/.test(line)) {
      flushParagraph();
      out.push('<hr>');
      i += 1;
      continue;
    }
    if (line.includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      flushParagraph();
      const header = splitTableRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      let table = '<div class="table-wrap"><table><thead><tr>';
      table += header.map((cell) => `<th>${renderInline(cell)}</th>`).join('');
      table += '</tr></thead><tbody>';
      for (const row of rows) {
        table += `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join('')}</tr>`;
      }
      table += '</tbody></table></div>';
      out.push(table);
      continue;
    }
    /* 文本已整体转义，原始的 ">" 在这里是 "&gt;" */
    if (/^ {0,3}&gt;/.test(line)) {
      flushParagraph();
      const quoted = [];
      while (i < lines.length && /^ {0,3}&gt;/.test(lines[i])) {
        quoted.push(lines[i].replace(/^ {0,3}&gt;\s?/, ''));
        i += 1;
      }
      out.push(`<blockquote>${renderLines(quoted)}</blockquote>`);
      continue;
    }
    const bullet = line.match(/^(\s*)[-*+]\s+(.*)$/);
    const orderedItem = line.match(/^(\s*)\d+[.)]\s+(.*)$/);
    if (bullet || orderedItem) {
      flushParagraph();
      const isOrdered = Boolean(orderedItem);
      const pattern = isOrdered ? /^(\s*)\d+[.)]\s+(.*)$/ : /^(\s*)[-*+]\s+(.*)$/;
      const items = [];
      while (i < lines.length) {
        const match = lines[i].match(pattern);
        if (!match) break;
        items.push({indent: match[1].length, text: match[2].trim()});
        i += 1;
      }
      out.push(renderList(items, isOrdered));
      continue;
    }
    paragraph.push(line.trim());
    i += 1;
  }
  flushParagraph();
  return out.join('\n');
}

function renderMarkdown(source) {
  const escaped = escapeHtml(String(source || '').replace(/\r\n?/g, '\n'));
  return renderLines(escaped.split('\n'));
}

/* ---------- 工具 ---------- */

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

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return true; } catch { /* 降级到 execCommand */ }
  }
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.append(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { ok = false; }
  area.remove();
  return ok;
}

function formatRelative(iso) {
  const stamp = Date.parse(iso);
  if (Number.isNaN(stamp)) return '';
  const seconds = Math.max(0, (Date.now() - stamp) / 1000);
  if (seconds < 60) return '刚刚';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  if (seconds < 86400 * 7) return `${Math.floor(seconds / 86400)} 天前`;
  const date = new Date(stamp);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

/* ---------- 渲染 ---------- */

function setStatusBadge(status) {
  const badge = document.getElementById('status-badge');
  badge.dataset.status = status;
  badge.textContent = STATUS_LABELS[status] || status;
}

function renderTranscript(result) {
  const box = document.getElementById('transcript');
  box.replaceChildren();
  const segments = result?.transcript || [];
  if (!segments.length) {
    const empty = document.createElement('p');
    empty.className = 'empty';
    empty.textContent = '没有可用语音转写';
    box.append(empty);
    return;
  }
  for (const segment of segments) {
    const row = document.createElement('div');
    row.className = 'segment';
    const time = document.createElement('span');
    time.className = 'segment-time';
    time.textContent = segment.start;
    const text = document.createElement('p');
    text.className = 'segment-text';
    text.textContent = segment.text;
    row.append(time, text);
    box.append(row);
  }
}

function showTask(task, options = {}) {
  const switched = activeTask !== task.id;
  if (switched) {
    const transcript = document.getElementById('transcript');
    transcript.hidden = true;
    const toggle = document.getElementById('toggle-transcript');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '查看语音转写';
  }
  activeTask = task.id;
  activeResult = task.result;
  resultCard.hidden = false;
  if (switched || options.scroll) {
    resultCard.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }
  const platform = PLATFORM_LABELS[task.platform] || task.platform;
  document.getElementById('video-title').textContent = task.result?.title || task.url;
  document.getElementById('video-meta').textContent = task.result
    ? [
        platform,
        task.result.uploader,
        `${Math.max(1, Math.round(task.result.duration_seconds / 60))} 分钟`,
        `${task.result.audio_segments} 段音频`,
        `${task.result.frames_analyzed} 张画面`,
      ].filter(Boolean).join(' · ')
    : platform;
  setStatusBadge(task.status);
  const running = task.status === 'queued' || task.status === 'running';
  document.getElementById('progress-area').hidden = !running;
  document.getElementById('progress-fill').style.width = `${task.progress}%`;
  document.getElementById('stage').textContent = running ? `${task.stage} · ${task.progress}%` : '';
  const report = document.getElementById('report');
  report.hidden = !task.result;
  report.innerHTML = task.result ? renderMarkdown(task.result.report) : '';
  document.getElementById('result-actions').hidden = !task.result;
  renderTranscript(task.result);
  const error = document.getElementById('error');
  error.hidden = !task.error;
  error.textContent = task.error || '';
  if (timer) clearTimeout(timer);
  if (running) {
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
      empty.textContent = '还没有任务，粘贴一个视频链接开始吧';
      taskList.append(empty);
      return;
    }
    for (const task of tasks) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'task';
      button.dataset.status = task.status;
      const dot = document.createElement('span');
      dot.className = 'task-dot';
      dot.setAttribute('aria-hidden', 'true');
      const body = document.createElement('span');
      body.className = 'task-body';
      const title = document.createElement('span');
      title.className = 'task-title';
      title.textContent = task.result?.title || task.url;
      const sub = document.createElement('span');
      sub.className = 'task-sub';
      sub.textContent = [
        PLATFORM_LABELS[task.platform] || task.platform,
        formatRelative(task.created_at),
      ].filter(Boolean).join(' · ');
      body.append(title, sub);
      const status = document.createElement('span');
      status.className = 'task-status';
      status.textContent = STATUS_LABELS[task.status] || task.status;
      button.append(dot, body, status);
      button.addEventListener('click', () => showTask(task, {scroll: true}));
      taskList.append(button);
    }
  } catch (err) { message.textContent = err.message; }
}

function providerChip(text, ok) {
  const chip = document.createElement('span');
  chip.className = ok ? 'chip chip-ok' : 'chip chip-bad';
  const dot = document.createElement('span');
  dot.className = 'chip-dot';
  dot.setAttribute('aria-hidden', 'true');
  const label = document.createElement('span');
  label.textContent = text;
  chip.append(dot, label);
  return chip;
}

/* ---------- 事件 ---------- */

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

document.getElementById('copy-report').addEventListener('click', async (event) => {
  if (!activeResult) return;
  const button = event.currentTarget;
  const done = await copyText(activeResult.report);
  button.textContent = done ? '已复制 ✓' : '复制失败';
  button.disabled = true;
  setTimeout(() => { button.textContent = '复制报告'; button.disabled = false; }, 1600);
});

document.getElementById('download-transcript').addEventListener('click', () => {
  if (activeResult) downloadText(`${activeTask}-transcript.txt`, transcriptText(activeResult), 'text/plain;charset=utf-8');
});

/* ---------- 启动 ---------- */

request('/api/health').then((health) => {
  providerStatus.replaceChildren(
    providerChip(`画面与总结 · ${health.ai_provider} ${health.ai_key_configured ? '已就绪' : '缺少密钥'}`, health.ai_key_configured),
    providerChip(`语音转写 · ${health.asr_provider} ${health.asr_key_configured ? '已就绪' : '缺少密钥'}`, health.asr_key_configured),
  );
}).catch(() => {
  providerStatus.replaceChildren(providerChip('无法读取模型配置', false));
});
loadHistory();
