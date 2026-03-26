#!/usr/bin/env python3
# ✨ Magic Factory Chat — part of NVIDIA DGX Spark Magic Factory
# Copyright 2026 Chris Morley / Lantern Light AI (https://www.lanternlight.ai)
# chris.morley@lanternlight.ai | depahelix@gmail.com
# Made with love in Massachusetts
#
# ptr c0010001

import argparse
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("SPARK_MODEL", "qwen3-coder-next")

# ── Chat persistence ─────────────────────────────────────────
CHAT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "chats")

def _ensure_chat_dir():
    os.makedirs(CHAT_DIR, exist_ok=True)
    idx = os.path.join(CHAT_DIR, "index.json")
    if not os.path.exists(idx):
        with open(idx, "w") as f:
            json.dump([], f)

def _read_index():
    _ensure_chat_dir()
    with open(os.path.join(CHAT_DIR, "index.json")) as f:
        return json.load(f)

def _write_index(index):
    _ensure_chat_dir()
    with open(os.path.join(CHAT_DIR, "index.json"), "w") as f:
        json.dump(index, f, indent=2)

def chat_list():
    return sorted(_read_index(), key=lambda c: c.get("updated", ""), reverse=True)

def chat_create(title="New chat"):
    cid = uuid.uuid4().hex[:12]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    entry = {"id": cid, "title": title, "created": now, "updated": now}
    chat_data = {"id": cid, "title": title, "messages": [], "created": now, "updated": now}
    _ensure_chat_dir()
    with open(os.path.join(CHAT_DIR, f"{cid}.json"), "w") as f:
        json.dump(chat_data, f, indent=2)
    index = _read_index()
    index.append(entry)
    _write_index(index)
    return chat_data

def chat_load(cid):
    path = os.path.join(CHAT_DIR, f"{cid}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)

def chat_save(cid, data):
    _ensure_chat_dir()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    data["updated"] = now
    with open(os.path.join(CHAT_DIR, f"{cid}.json"), "w") as f:
        json.dump(data, f, indent=2)
    index = _read_index()
    for entry in index:
        if entry["id"] == cid:
            entry["title"] = data.get("title", entry["title"])
            entry["updated"] = now
            break
    _write_index(index)

def chat_delete(cid):
    path = os.path.join(CHAT_DIR, f"{cid}.json")
    if os.path.exists(path):
        os.remove(path)
    index = _read_index()
    index = [e for e in index if e["id"] != cid]
    _write_index(index)

# ptr c0010002

def ollama_models():
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        return []

def ollama_stream(model, messages):
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": True,
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=600) as resp:
        buf = b""
        while True:
            chunk = resp.read(1)
            if not chunk:
                break
            buf += chunk
            if chunk == b"\n":
                if buf.strip():
                    obj = json.loads(buf)
                    content = obj.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if obj.get("done"):
                        break
                buf = b""

# ptr c0010003

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>✨ Magic Factory Chat</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

:root {
  --bg: #050507;
  --bg-chat: #0a0a0f;
  --bg-input: #0e0e16;
  --bg-user: #111118;
  --bg-ai: transparent;
  --border: #1a1a28;
  --border-focus: #2d4a2d;
  --text: #c8c8d0;
  --text-dim: #555568;
  --text-bright: #ededf0;
  --accent: #44cc77;
  --accent-dim: rgba(68,204,119,0.06);
  --accent-glow: rgba(68,204,119,0.12);
  --user-accent: #6688bb;
  --mono: 'JetBrains Mono', 'SF Mono', 'Cascadia Code', 'Consolas', 'Liberation Mono', monospace;
  --sans: 'Space Grotesk', 'SF Pro Display', 'Segoe UI', system-ui, sans-serif;
  --radius: 4px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--mono);
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  display: flex;
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
}

/* ── Sidebar ───────────────────────── */
.sidebar {
  width: 260px; min-width: 260px;
  background: #08080c;
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  flex-shrink: 0;
}
.sidebar-header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.sidebar-title {
  font-family: var(--sans); font-weight: 600; font-size: 0.85rem;
  color: var(--text-dim); letter-spacing: 0.06em; text-transform: uppercase;
}
.new-chat-btn {
  font-family: var(--mono); font-size: 0.8rem; padding: 4px 10px;
  background: var(--accent-dim); border: 1px solid var(--border-focus);
  color: var(--accent); border-radius: var(--radius); cursor: pointer;
  transition: all 0.15s; white-space: nowrap;
}
.new-chat-btn:hover { background: var(--accent-glow); }
.chat-list {
  flex: 1; overflow-y: auto; padding: 6px 0;
}
.chat-list::-webkit-scrollbar { width: 3px; }
.chat-list::-webkit-scrollbar-track { background: transparent; }
.chat-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.chat-item {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px; cursor: pointer;
  font-size: 0.82rem; color: var(--text-dim);
  border-left: 2px solid transparent;
  transition: all 0.12s;
}
.chat-item:hover { background: rgba(255,255,255,0.02); color: var(--text); }
.chat-item.active {
  background: rgba(68,204,119,0.04); color: var(--text-bright);
  border-left-color: var(--accent);
}
.chat-item-title {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.chat-item-date {
  font-size: 0.65rem; color: var(--text-dim); white-space: nowrap; opacity: 0.6;
}
.chat-item-delete {
  background: none; border: none; color: var(--text-dim); cursor: pointer;
  font-size: 0.7rem; padding: 2px 4px; border-radius: 2px;
  opacity: 0; transition: all 0.12s; line-height: 1;
}
.chat-item:hover .chat-item-delete { opacity: 1; }
.chat-item-delete:hover { color: #ee6666; background: rgba(238,68,68,0.1); }
.sidebar-empty {
  padding: 20px 14px; font-size: 0.78rem; color: var(--text-dim);
  text-align: center; line-height: 1.6;
}

/* ── Main column ───────────────────── */
.main-col {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; min-width: 0;
}

/* ── Header ─────────────────────────── */
.header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.logo {
  font-family: var(--sans); font-weight: 700; font-size: 1.1rem;
  color: var(--accent); letter-spacing: 0.04em;
}
.logo span { filter: drop-shadow(0 0 8px rgba(68,204,119,0.5)); }
.model-tag {
  font-size: 0.75rem; color: var(--text-dim); padding: 3px 8px;
  border: 1px solid var(--border); border-radius: 3px;
  font-weight: 400;
}
.header-right { display: flex; align-items: center; gap: 10px; }
.local-badge {
  font-size: 0.7rem; color: var(--accent); padding: 2px 8px;
  border: 1px solid var(--border-focus); border-radius: 3px;
  letter-spacing: 0.06em; text-transform: uppercase; font-weight: 600;
}
.clear-btn {
  font-family: var(--mono); font-size: 0.8rem; padding: 4px 10px;
  background: transparent; border: 1px solid var(--border); color: var(--text-dim);
  border-radius: var(--radius); cursor: pointer; transition: all 0.15s;
}
.clear-btn:hover { border-color: var(--text-dim); color: var(--text); }

/* ── Chat area ──────────────────────── */
.chat-area {
  flex: 1; overflow-y: auto; padding: 20px 0;
  scroll-behavior: smooth;
}
.chat-area::-webkit-scrollbar { width: 4px; }
.chat-area::-webkit-scrollbar-track { background: transparent; }
.chat-area::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.message {
  padding: 12px 24px;
  line-height: 1.65;
  font-size: 1rem;
  animation: fadeIn 0.2s ease;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

.message.user {
  background: var(--bg-user);
  border-left: 2px solid var(--user-accent);
  color: var(--text-bright);
}
.message.assistant {
  background: var(--bg-ai);
  border-left: 2px solid transparent;
}
.message .role {
  font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; margin-bottom: 6px;
}
.message.user .role { color: var(--user-accent); }
.message.assistant .role { color: var(--accent); }
.message .content { word-wrap: break-word; }
.message .content p { margin: 0.4em 0; }
.message .content p:first-child { margin-top: 0; }
.message .content p:last-child { margin-bottom: 0; }
.message .content code {
  background: rgba(255,255,255,0.06); padding: 1px 5px;
  border-radius: 2px; font-size: 0.92rem;
}
.message .content pre {
  background: #08080c; padding: 12px; margin: 8px 0;
  border-radius: var(--radius); border: 1px solid var(--border);
  overflow-x: auto; font-size: 0.9rem; position: relative;
}
.message .content pre code { background: none; padding: 0; display: block; white-space: pre; }
.message .content ul, .message .content ol { margin: 0.4em 0; padding-left: 1.6em; }
.message .content li { margin: 0.2em 0; }
.message .content blockquote {
  border-left: 2px solid var(--border); padding-left: 10px;
  margin: 0.4em 0; color: var(--text-dim);
}
.message .content h1, .message .content h2, .message .content h3,
.message .content h4, .message .content h5, .message .content h6 {
  color: var(--text-bright); margin: 0.6em 0 0.3em; font-size: 1rem; font-weight: 600;
}
.message .content h1 { font-size: 1.2rem; }
.message .content h2 { font-size: 1.1rem; }
.message .content hr { border: none; border-top: 1px solid var(--border); margin: 0.6em 0; }
.message .content table { border-collapse: collapse; margin: 0.4em 0; font-size: 0.9rem; }
.message .content th, .message .content td {
  border: 1px solid var(--border); padding: 4px 8px; text-align: left;
}
.message .content th { background: rgba(255,255,255,0.03); }
.message .content a { color: var(--accent); text-decoration: none; }
.message .content a:hover { text-decoration: underline; }

/* ── Copy button ───────────────────── */
.message-wrapper { position: relative; }
.copy-btn {
  position: absolute; top: 8px; right: 12px;
  background: transparent; border: 1px solid var(--border);
  color: var(--text-dim); border-radius: 3px;
  width: 28px; height: 28px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s; opacity: 0; z-index: 1;
}
.message-wrapper:hover .copy-btn { opacity: 1; }
.copy-btn:hover { border-color: var(--text-dim); color: var(--text); background: rgba(255,255,255,0.03); }
.copy-btn.copied { border-color: var(--accent); color: var(--accent); opacity: 1; }
.copy-btn svg { width: 14px; height: 14px; }

.typing-indicator {
  display: inline-block; width: 6px; height: 14px;
  background: var(--accent); border-radius: 1px;
  animation: blink 0.8s infinite;
  vertical-align: text-bottom;
  margin-left: 1px;
}
@keyframes blink { 0%,50% { opacity: 1; } 51%,100% { opacity: 0; } }

/* ── Welcome ────────────────────────── */
.welcome {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 16px;
  color: var(--text-dim); text-align: center; padding: 40px;
}
.welcome-icon { font-size: 2.5rem; filter: drop-shadow(0 0 20px rgba(68,204,119,0.3)); }
.welcome h2 {
  font-family: var(--sans); font-weight: 700; font-size: 1.5rem;
  color: var(--text); letter-spacing: 0.02em;
}
.welcome p { font-size: 0.88rem; max-width: 400px; line-height: 1.6; }
.welcome .privacy-note {
  font-size: 0.6rem; color: var(--accent); padding: 6px 14px;
  border: 1px solid var(--border-focus); border-radius: 3px;
  margin-top: 8px;
}

/* ── Input area ─────────────────────── */
.input-area {
  border-top: 1px solid var(--border);
  padding: 12px 20px;
  background: var(--bg);
  flex-shrink: 0;
}
.input-row { display: flex; gap: 8px; max-width: 900px; margin: 0 auto; }
.input-box {
  flex: 1; font-family: var(--mono); font-size: 1rem;
  background: var(--bg-input); color: var(--text-bright);
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 12px 16px; resize: none; outline: none;
  min-height: 48px; max-height: 200px;
  transition: border-color 0.15s;
  line-height: 1.5;
}
.input-box:focus { border-color: var(--border-focus); }
.input-box::placeholder { color: var(--text-dim); }
.send-btn {
  font-family: var(--mono); font-size: 1rem; font-weight: 600;
  padding: 0 20px; background: var(--accent-dim);
  border: 1px solid var(--border-focus); color: var(--accent);
  border-radius: var(--radius); cursor: pointer;
  transition: all 0.15s; white-space: nowrap;
}
.send-btn:hover:not(:disabled) {
  background: var(--accent-glow);
  box-shadow: 0 0 12px rgba(68,204,119,0.1);
}
.send-btn:disabled { opacity: 0.3; cursor: default; }

.input-hint {
  font-size: 0.7rem; color: var(--text-dim); text-align: center;
  margin-top: 6px;
}

/* ── Error ──────────────────────────── */
.error-banner {
  background: rgba(238,68,68,0.08); border: 1px solid rgba(238,68,68,0.2);
  color: #ee6666; padding: 10px 20px; font-size: 0.85rem;
  text-align: center; display: none;
}
.error-banner.visible { display: block; }

@media (max-width: 768px) {
  .sidebar { width: 220px; min-width: 220px; }
}
@media (max-width: 600px) {
  .sidebar { display: none; }
  .message { padding: 10px 14px; }
  .input-box { font-size: 0.9rem; }
  .header { padding: 8px 14px; }
}
</style>
</head>
<body>

<div class="sidebar">
  <div class="sidebar-header">
    <span class="sidebar-title">History</span>
    <button class="new-chat-btn" onclick="newChat()">+ New</button>
  </div>
  <div class="chat-list" id="chat-list">
    <div class="sidebar-empty">No conversations yet</div>
  </div>
</div>

<div class="main-col">

<div class="header">
  <div class="header-left">
    <div class="logo"><span>✨</span> Magic Factory Chat</div>
    <span class="model-tag" id="model-name">loading…</span>
  </div>
  <div class="header-right">
    <span class="local-badge">100% local</span>
    <button class="clear-btn" onclick="clearChat()">Clear</button>
  </div>
</div>

<div id="error-banner" class="error-banner"></div>

<div class="chat-area" id="chat-area">
  <div class="welcome" id="welcome">
    <div class="welcome-icon">✨</div>
    <h2>Magic Factory Chat</h2>
    <p>Direct conversation with your local model via Ollama.<br>
    No accounts. No cloud. No telemetry. Just you and the model.</p>
    <div class="privacy-note">All data stays on this machine</div>
    <div style="margin-top:1.2rem;font-size:0.75rem;color:#555568;">
      &copy; 2026 Chris Morley · <a href="https://www.lanternlight.ai" target="_blank" style="color:#44cc77;text-decoration:none;">Lantern Light AI</a> · Made with &#10084;&#65039; with Claude Code, in Massachusetts<br>
      <a href="mailto:chris.morley@lanternlight.ai" style="color:#555568;text-decoration:none;">chris.morley@lanternlight.ai</a>
    </div>
    <!-- Psst — the person who built this does contract work. 100% remote. Just saying. -->
  </div>
</div>

<div class="input-area">
  <div class="input-row">
    <textarea class="input-box" id="input" placeholder="Type a message…" rows="1"
              onkeydown="handleKey(event)" autofocus></textarea>
    <button class="send-btn" id="send-btn" onclick="sendMessage()">Send</button>
  </div>
  <div class="input-hint">Enter to send · Shift+Enter for newline</div>
</div>

</div><!-- /main-col -->

<script>
const chatArea = document.getElementById('chat-area');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');
const modelTag = document.getElementById('model-name');
const errorBanner = document.getElementById('error-banner');

let messages = [];
let streaming = false;
let currentModel = '';
let currentChatId = null;
const chatListEl = document.getElementById('chat-list');

// ── Lightweight Markdown renderer ────────────────────────────
function renderMarkdown(src) {
  // Normalize line endings
  src = src.replace(/\r\n/g, '\n');

  // Extract fenced code blocks first to protect them
  const codeBlocks = [];
  src = src.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    codeBlocks.push('<pre><code>' + escapeHtml(code.replace(/\n$/, '')) + '</code></pre>');
    return '\x00CODE' + (codeBlocks.length - 1) + '\x00';
  });

  // Inline code (protect from further processing)
  const inlineCode = [];
  src = src.replace(/`([^`\n]+)`/g, (_, code) => {
    inlineCode.push('<code>' + escapeHtml(code) + '</code>');
    return '\x00INLINE' + (inlineCode.length - 1) + '\x00';
  });

  // Process line-based elements
  const lines = src.split('\n');
  let html = '';
  let inList = false;
  let listType = '';
  let i = 0;

  while (i < lines.length) {
    let line = lines[i];

    // Check for code block placeholder
    const codePlaceholder = line.match(/^\x00CODE(\d+)\x00$/);
    if (codePlaceholder) {
      if (inList) { html += '</' + listType + '>'; inList = false; }
      html += codeBlocks[parseInt(codePlaceholder[1])];
      i++; continue;
    }

    // Headings
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      if (inList) { html += '</' + listType + '>'; inList = false; }
      const level = headingMatch[1].length;
      html += '<h' + level + '>' + inlineFormat(headingMatch[2]) + '</h' + level + '>';
      i++; continue;
    }

    // Horizontal rule
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      if (inList) { html += '</' + listType + '>'; inList = false; }
      html += '<hr>';
      i++; continue;
    }

    // Unordered list
    const ulMatch = line.match(/^(\s*)[*\-+]\s+(.+)$/);
    if (ulMatch) {
      if (!inList || listType !== 'ul') {
        if (inList) html += '</' + listType + '>';
        html += '<ul>'; inList = true; listType = 'ul';
      }
      html += '<li>' + inlineFormat(ulMatch[2]) + '</li>';
      i++; continue;
    }

    // Ordered list
    const olMatch = line.match(/^(\s*)\d+\.\s+(.+)$/);
    if (olMatch) {
      if (!inList || listType !== 'ol') {
        if (inList) html += '</' + listType + '>';
        html += '<ol>'; inList = true; listType = 'ol';
      }
      html += '<li>' + inlineFormat(olMatch[2]) + '</li>';
      i++; continue;
    }

    // Blockquote
    if (line.match(/^>\s?/)) {
      if (inList) { html += '</' + listType + '>'; inList = false; }
      let bq = '';
      while (i < lines.length && lines[i].match(/^>\s?/)) {
        bq += lines[i].replace(/^>\s?/, '') + '\n';
        i++;
      }
      html += '<blockquote>' + inlineFormat(bq.trim()) + '</blockquote>';
      continue;
    }

    // Close list if non-list line
    if (inList) { html += '</' + listType + '>'; inList = false; }

    // Empty line
    if (line.trim() === '') { i++; continue; }

    // Table detection
    if (i + 1 < lines.length && /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      let tableHtml = '<table>';
      // Header row
      const headers = parseTableRow(line);
      tableHtml += '<tr>' + headers.map(h => '<th>' + inlineFormat(h.trim()) + '</th>').join('') + '</tr>';
      i += 2; // skip header and separator
      while (i < lines.length && lines[i].includes('|')) {
        const cells = parseTableRow(lines[i]);
        tableHtml += '<tr>' + cells.map(c => '<td>' + inlineFormat(c.trim()) + '</td>').join('') + '</tr>';
        i++;
      }
      html += tableHtml + '</table>';
      continue;
    }

    // Paragraph
    html += '<p>' + inlineFormat(line) + '</p>';
    i++;
  }

  if (inList) html += '</' + listType + '>';

  // Restore inline code
  html = html.replace(/\x00INLINE(\d+)\x00/g, (_, idx) => inlineCode[parseInt(idx)]);

  return html;
}

function parseTableRow(line) {
  return line.replace(/^\|/, '').replace(/\|$/, '').split('|');
}

function inlineFormat(text) {
  // Bold + italic
  text = text.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  text = text.replace(/___(.+?)___/g, '<strong><em>$1</em></strong>');
  // Bold
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/__(.+?)__/g, '<strong>$1</strong>');
  // Italic
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(/_(.+?)_/g, '<em>$1</em>');
  // Strikethrough
  text = text.replace(/~~(.+?)~~/g, '<del>$1</del>');
  // Links
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return text;
}

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Copy to clipboard ────────────────────────────────────────
const COPY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>';
const CHECK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';

function copyToClipboard(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    btn.innerHTML = CHECK_ICON;
    btn.classList.add('copied');
    setTimeout(() => {
      btn.innerHTML = COPY_ICON;
      btn.classList.remove('copied');
    }, 2000);
  });
}

// ── Init: fetch model info ───────────────────────────────────
async function init() {
  try {
    const r = await fetch('/api/info');
    const d = await r.json();
    currentModel = d.model;
    modelTag.textContent = d.model;
    if (d.models && d.models.length > 0) {
      modelTag.title = 'Available: ' + d.models.join(', ');
    }
    if (!d.ollama_ok) {
      showError('Ollama is not responding at ' + d.ollama_host + '. Is it running?');
    } else if (!d.model_available) {
      showError('Model "' + d.model + '" not found. Available: ' + (d.models||[]).join(', '));
    }
  } catch(e) {
    showError('Cannot reach chat server.');
  }
}

function showError(msg) {
  errorBanner.textContent = msg;
  errorBanner.classList.add('visible');
}
function hideError() {
  errorBanner.classList.remove('visible');
}

// ── Auto-resize textarea ─────────────────────────────────────
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 200) + 'px';
});

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

// ── Send message ─────────────────────────────────────────────
async function sendMessage() {
  const text = input.value.trim();
  if (!text || streaming) return;

  hideError();
  const wel = chatArea.querySelector('.welcome');
  if (wel) wel.remove();

  // Add user message
  messages.push({ role: 'user', content: text });
  appendMessage('user', text);

  input.value = '';
  input.style.height = 'auto';
  streaming = true;
  sendBtn.disabled = true;

  // Add assistant placeholder
  const aiWrapper = appendMessage('assistant', '');
  const contentEl = aiWrapper.querySelector('.content');
  contentEl.innerHTML = '<span class="typing-indicator"></span>';

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      fullText += chunk;
      contentEl.textContent = fullText;
      chatArea.scrollTop = chatArea.scrollHeight;
    }

    // Render final markdown
    contentEl.innerHTML = renderMarkdown(fullText);
    // Update copy button to use raw text
    aiWrapper._rawText = fullText;
    const copyBtn = aiWrapper.querySelector('.copy-btn');
    copyBtn.onclick = () => copyToClipboard(copyBtn, fullText);
    messages.push({ role: 'assistant', content: fullText });

    // Auto-save to history
    saveCurrentChat();

  } catch(e) {
    contentEl.textContent = '⚠ Error: ' + e.message;
    contentEl.style.color = '#ee6666';
    // Remove failed assistant message from history
  }

  streaming = false;
  sendBtn.disabled = false;
  input.focus();
}

function appendMessage(role, text) {
  const wrapper = document.createElement('div');
  wrapper.className = 'message-wrapper';
  const div = document.createElement('div');
  div.className = 'message ' + role;
  div.innerHTML = `<div class="role">${role === 'user' ? 'You' : currentModel || 'assistant'}</div><div class="content"></div>`;
  const contentEl = div.querySelector('.content');
  if (role === 'user') {
    contentEl.textContent = text;
  } else {
    contentEl.innerHTML = text ? renderMarkdown(text) : '';
  }
  // Copy button
  const copyBtn = document.createElement('button');
  copyBtn.className = 'copy-btn';
  copyBtn.title = 'Copy to clipboard';
  copyBtn.innerHTML = COPY_ICON;
  copyBtn.onclick = () => copyToClipboard(copyBtn, text || contentEl.innerText);
  wrapper.appendChild(copyBtn);
  wrapper.appendChild(div);
  wrapper._rawText = text;
  chatArea.appendChild(wrapper);
  chatArea.scrollTop = chatArea.scrollHeight;
  return wrapper;
}

function clearChat() {
  messages = [];
  currentChatId = null;
  chatArea.innerHTML = '';
  hideError();
  renderChatList();
  showWelcome();
}

function showWelcome() {
  chatArea.innerHTML = `
    <div class="welcome">
      <div class="welcome-icon">✨</div>
      <h2>Magic Factory Chat</h2>
      <p>Direct conversation with your local model via Ollama.<br>
      No accounts. No cloud. No telemetry. Just you and the model.</p>
      <div class="privacy-note">All data stays on this machine</div>
      <div style="margin-top:1.2rem;font-size:0.75rem;color:#555568;">
        &copy; 2026 Chris Morley · <a href="https://www.lanternlight.ai" target="_blank" style="color:#44cc77;text-decoration:none;">Lantern Light AI</a> · Made with &#10084;&#65039; with Claude Code, in Massachusetts<br>
        <a href="mailto:chris.morley@lanternlight.ai" style="color:#555568;text-decoration:none;">chris.morley@lanternlight.ai</a>
      </div>
    </div>`;
}

// ── Chat history API ─────────────────────────────────────────
async function fetchChatList() {
  try {
    const r = await fetch('/api/chats');
    return await r.json();
  } catch(e) { return []; }
}

function renderChatList(chats) {
  if (!chats) { fetchChatList().then(renderChatList); return; }
  if (chats.length === 0) {
    chatListEl.innerHTML = '<div class="sidebar-empty">No conversations yet</div>';
    return;
  }
  chatListEl.innerHTML = chats.map(c => {
    const active = c.id === currentChatId ? ' active' : '';
    const date = c.updated ? c.updated.slice(5, 10) : '';
    return `<div class="chat-item${active}" data-id="${c.id}" onclick="loadChat('${c.id}')">
      <span class="chat-item-title">${escapeHtml(c.title)}</span>
      <span class="chat-item-date">${date}</span>
      <button class="chat-item-delete" onclick="event.stopPropagation();deleteChat('${c.id}')" title="Delete">×</button>
    </div>`;
  }).join('');
}

async function newChat() {
  if (streaming) return;
  currentChatId = null;
  messages = [];
  chatArea.innerHTML = '';
  showWelcome();
  renderChatList();
  input.focus();
}

async function loadChat(id) {
  if (streaming) return;
  try {
    const r = await fetch('/api/chats/' + id);
    if (!r.ok) return;
    const data = await r.json();
    currentChatId = data.id;
    messages = data.messages || [];
    chatArea.innerHTML = '';
    hideError();
    for (const msg of messages) {
      appendMessage(msg.role, msg.content);
    }
    renderChatList();
  } catch(e) {}
}

async function saveCurrentChat() {
  if (messages.length === 0) return;
  const title = messages[0].content.slice(0, 60) + (messages[0].content.length > 60 ? '...' : '');
  if (!currentChatId) {
    // Create new chat
    try {
      const r = await fetch('/api/chats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, messages }),
      });
      const data = await r.json();
      currentChatId = data.id;
    } catch(e) {}
  } else {
    // Update existing
    try {
      await fetch('/api/chats/' + currentChatId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, messages }),
      });
    } catch(e) {}
  }
  renderChatList();
}

async function deleteChat(id) {
  try {
    await fetch('/api/chats/' + id, { method: 'DELETE' });
    if (currentChatId === id) {
      currentChatId = null;
      messages = [];
      chatArea.innerHTML = '';
      showWelcome();
    }
    renderChatList();
  } catch(e) {}
}

init();
renderChatList();
</script>
</body>
</html>"""


# ptr c0010004

class ChatHandler(BaseHTTPRequestHandler):
    model = DEFAULT_MODEL

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())

        elif path == "/api/info":
            models = ollama_models()
            resolved = self.model
            for m in models:
                base = m.split(":")[0]
                if self.model == base or self.model == m:
                    resolved = m
                    break
            self.model = resolved  # update for subsequent chat calls
            model_available = resolved in models
            ollama_ok = len(models) > 0 or self._ollama_ping()
            self.send_json({
                "model": resolved,
                "models": models,
                "model_available": model_available,
                "ollama_ok": ollama_ok,
                "ollama_host": OLLAMA_BASE,
            })

        elif path == "/api/chats":
            self.send_json(chat_list())

        elif path.startswith("/api/chats/"):
            cid = path.split("/")[-1]
            data = chat_load(cid)
            if data:
                self.send_json(data)
            else:
                self.send_error(404)

        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            messages = body.get("messages", [])

            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                for token in ollama_stream(self.model, messages):
                    chunk = f"{len(token.encode()):x}\r\n{token}\r\n"
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()

                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()

            except Exception as e:
                try:
                    err = f"\n\n⚠ Stream error: {e}"
                    chunk = f"{len(err.encode()):x}\r\n{err}\r\n0\r\n\r\n"
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()
                except Exception:
                    pass

        elif path == "/api/chats":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            data = chat_create(body.get("title", "New chat"))
            data["messages"] = body.get("messages", [])
            chat_save(data["id"], data)
            self.send_json(data)

        else:
            self.send_error(404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if path.startswith("/api/chats/"):
            cid = path.split("/")[-1]
            existing = chat_load(cid)
            if not existing:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            existing["messages"] = body.get("messages", existing["messages"])
            existing["title"] = body.get("title", existing["title"])
            chat_save(cid, existing)
            self.send_json(existing)
        else:
            self.send_error(404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/chats/"):
            cid = path.split("/")[-1]
            chat_delete(cid)
            self.send_json({"ok": True})
        else:
            self.send_error(404)

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ollama_ping(self):
        try:
            req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception:
            return False


def main():
    parser = argparse.ArgumentParser(description="Magic Factory Chat — local Ollama chat UI")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--port", type=int, default=7722, help="Port (default: 7722)")
    args = parser.parse_args()

    ChatHandler.model = args.model

    models = ollama_models()
    if models:
        resolved = args.model
        for m in models:
            if args.model == m.split(":")[0] or args.model == m:
                resolved = m
                break
        ChatHandler.model = resolved
        match = resolved in models
        print(f"✨ Magic Factory Chat")
        print(f"  Model:    {resolved} {'✓' if match else '⚠ not found in Ollama'}")
        print(f"  Ollama:   {OLLAMA_BASE}")
        print(f"  Models:   {', '.join(models) if models else 'none'}")
    else:
        print(f"✨ Magic Factory Chat")
        print(f"  ⚠ Ollama not responding at {OLLAMA_BASE}")
        print(f"  Model:    {args.model}")

    print(f"  Open:     http://localhost:{args.port}")
    print(f"  Privacy:  100% local — no data leaves this machine")
    print()

    server = HTTPServer(("127.0.0.1", args.port), ChatHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
