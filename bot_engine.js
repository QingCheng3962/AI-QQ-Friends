'use strict';

// OneBot 11 engine for "AI QQ Friends", controlled by the Python app over stdio.
// Usage: node bot_engine.js <qq-runtime-config.json>
//
// Config: {mode:"forward"|"reverse", url, accessToken, listenHost, listenPort, groups, ignoreGroups, ...}
// Events (stdout, one JSON per line):
//   {"event":"log","level":..., "message":...}
//   {"event":"status","state":"connected"|"disconnected","selfId":...}
//   {"event":"groups","groups":[{id,name}]}
//   {"event":"groupMessage","groupId","groupName","sender","senderId","content","mentioned":bool,"atAll":bool,"raw":...}
//   {"event":"error","message":...}
//   {"event":"end","reason":...}
// Commands (stdin, one JSON per line):
//   {"type":"sendGroup","groupId":...,"text":...,"atSender":bool}
//   {"type":"sendGroupMusic","groupId":...,"platform":"qq"|"163"|"custom",
//    "songId":...,"title":...,"audio":...,"url":...,"image":...}
//   {"type":"setGroups","groups":[...]} / {"type":"setIgnoreGroups","groups":[...]}
//   {"type":"ping"} / {"type":"quit"}

const fs = require('fs');
const readline = require('readline');

let WebSocket;
try {
    WebSocket = require('ws');
} catch (e) {
    process.stdout.write(JSON.stringify({ event: 'error',
        message: 'ws module not found (run "npm install"): ' + e.message }) + '\n');
    process.exit(1);
}

function emitEvent(obj) { process.stdout.write(JSON.stringify(obj) + '\n'); }
function log(level, message) { emitEvent({ event: 'log', level, message: String(message) }); }
function logError(message) { emitEvent({ event: 'error', message: String(message) }); }

function sanitizeText(value) {
    if (value == null) return '';
    const s = String(value);
    let out = '';
    for (let i = 0; i < s.length; i++) {
        const code = s.charCodeAt(i);
        if (code >= 0xD800 && code <= 0xDBFF) {
            const next = s.charCodeAt(i + 1);
            if (next >= 0xDC00 && next <= 0xDFFF) { out += s[i] + s[i + 1]; i++; }
            else { out += '?'; }
        } else if (code >= 0xDC00 && code <= 0xDFFF) { out += '?'; }
        else if (code < 0x20 || code === 0x7F || (code >= 0x80 && code <= 0x9F) ||
                 code === 0xFFFE || code === 0xFFFF) { out += '?'; }
        else { out += s[i]; }
    }
    return out;
}

const configPath = process.argv[2];
if (!configPath) { console.error('usage: node bot_engine.js <qq-runtime-config.json>'); process.exit(1); }
let config = {};
try { config = JSON.parse(fs.readFileSync(configPath, 'utf8')); }
catch (e) { console.error('Failed to read runtime config: ' + e.message); process.exit(1); }

const mode = config.mode === 'reverse' ? 'reverse' : 'forward';
const accessToken = String(config.accessToken || '');
const listenHost = String(config.listenHost || '0.0.0.0');
const listenPort = parseInt(config.listenPort, 10) || 3002;
let groupFilter = new Set((config.groups || []).map((g) => String(g).trim()).filter(Boolean));
let ignoreFilter = new Set((config.ignoreGroups || []).map((g) => String(g).trim()).filter(Boolean));

let autoReconnect = config.autoReconnect !== false;
const healthCheckSeconds = parseInt(config.healthCheckSeconds, 10) || 0;
let restricted = false;
let everOnline = false;
let lastHealthOk = false;
let healthFails = 0;
let healthTimer = null;
let healthBusy = false;
let selfId = '';

const groupNames = new Map();
let stopped = false;
let reconnectTimer = null;
let retry = 0;
let lastState = null;
const clients = new Set();
let forwardWs = null;

function setStatus(state, extra) {
    emitEvent(Object.assign({ event: 'status', state, mode }, extra || {}));
    lastState = state;
}

function stopHealthCheck() { if (healthTimer) { clearInterval(healthTimer); healthTimer = null; } }

function startHealthCheck() {
    stopHealthCheck();
    healthFails = 0;
    if (healthCheckSeconds <= 0 || stopped) return;
    healthTimer = setInterval(async () => {
        if (stopped || healthBusy) return;
        healthBusy = true;
        let res = null;
        try { res = await actionAsync('get_login_info', {}, 5000); }
        finally { healthBusy = false; }
        const d = res && res.data;
        const ok = !!(d && (d.user_id || d.nickname));
        if (ok) {
            if (d.user_id) selfId = String(d.user_id);
            everOnline = true;
            if (restricted) {
                restricted = false;
                log('info', 'QQ 已恢复在线。');
            }
            if (!lastHealthOk) {
                emitEvent({ event: 'status', state: 'connected', mode, selfId,
                            nickname: d.nickname || '' });
            }
            healthFails = 0; lastHealthOk = true;
        } else {
            lastHealthOk = false; healthFails += 1;
            if (everOnline && healthFails >= 3) {
                if (!restricted) {
                    restricted = true;
                    emitEvent({ event: 'restricted',
                        message: 'QQ 可能离线或被限制（在线检测连续失败）。仍在低频重试，恢复后会自动继续。' });
                    setStatus('disconnected');
                }
            } else {
                log('warn', '尚未检测到 QQ 在线（第 ' + healthFails + ' 次）。');
            }
        }
    }, healthCheckSeconds * 1000);
}

// --- message parsing ---
function atText(data) {
    const q = data && data.qq;
    if (q === 'all' || q === 0 || q === '0') return '@全体成员';
    const name = data && (data.name || data.card);
    return '@' + (name || q || '');
}

function segmentText(seg) {
    if (!seg || typeof seg !== 'object') return '';
    const data = seg.data || {};
    switch (seg.type) {
        case 'text': return String(data.text == null ? '' : data.text);
        case 'at': return atText(data);
        case 'image': case 'flash': return '[图片]';
        case 'face': case 'mface': return '[表情]';
        case 'record': return '[语音]';
        case 'video': return '[视频]';
        case 'file': return '[文件]';
        case 'json': case 'xml': return '[卡片]';
        case 'forward': return '[合并转发]';
        case 'share': return '[链接]';
        case 'location': return '[位置]';
        case 'music': return '[音乐]';
        case 'reply': return '';
        default: return '[' + seg.type + ']';
    }
}

function extractText(message) {
    if (message == null) return '';
    if (typeof message === 'string') return sanitizeText(message.trim());
    if (!Array.isArray(message)) return '';
    let out = '';
    for (const seg of message) out += segmentText(seg);
    return sanitizeText(out.replace(/\r?\n/g, ' ').replace(/\s+/g, ' ').trim());
}

function isMentioned(message) {
    if (!selfId) return false;
    if (typeof message === 'string') {
        // CQ-string form: [CQ:at,qq=<selfId>] or [CQ:at,qq=<selfId>,name=...]
        return new RegExp('\\[CQ:at,[^\\]]*qq=' + selfId + '(?:,|\\])').test(message);
    }
    if (!Array.isArray(message)) return false;
    for (const seg of message) {
        if (seg && seg.type === 'at' && String((seg.data || {}).qq) === selfId) return true;
    }
    return false;
}

function isAtAll(message) {
    if (typeof message === 'string') return /\[CQ:at,[^\]]*qq=all(?:,|\])/.test(message);
    if (!Array.isArray(message)) return false;
    for (const seg of message) {
        if (seg && seg.type === 'at' && String((seg.data || {}).qq) === 'all') return true;
    }
    return false;
}

function senderName(event) {
    const s = (event && event.sender) || {};
    const card = s.card ? String(s.card).trim() : '';
    const nick = s.nickname ? String(s.nickname).trim() : '';
    if (card && card !== nick) return card;
    return nick || card || ('QQ' + (s.user_id != null ? s.user_id : ''));
}

function groupName(id) { return groupNames.get(id) || ('群' + id); }

// --- outgoing ---
// Escape CQ code special characters (& [ ] ,) inside a parameter value.
function cqEscape(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/\[/g, '&#91;')
        .replace(/\]/g, '&#93;')
        .replace(/,/g, '&#44;')
        .replace(/\r?\n/g, ' ');
}

function rawSend(text) {
    let sent = false;
    if (mode === 'forward') {
        if (forwardWs && forwardWs.readyState === WebSocket.OPEN) { forwardWs.send(text); sent = true; }
    } else {
        for (const ws of clients) if (ws.readyState === WebSocket.OPEN) { ws.send(text); sent = true; }
    }
    return sent;
}

const pendingActions = new Map();
let actionSeq = 0;

function sendAction(action, params, echo) {
    const payload = { action, params: params || {}, echo: echo || (action + '_' + Date.now()) };
    rawSend(JSON.stringify(payload));
    return payload.echo;
}

function actionAsync(action, params, timeoutMs) {
    return new Promise((resolve) => {
        const echo = 'async_' + (++actionSeq);
        pendingActions.set(echo, resolve);
        sendAction(action, params, echo);
        setTimeout(() => { if (pendingActions.has(echo)) { pendingActions.delete(echo); resolve(null); } },
            timeoutMs || 4000);
    });
}

// Fetch login info once right after connecting so @-mention detection works
// immediately instead of waiting for the first meta_event / health check.
function refreshSelfId() {
    actionAsync('get_login_info', {}, 5000).then((res) => {
        const d = res && res.data;
        if (d && d.user_id != null) selfId = String(d.user_id);
    }).catch(() => {});
}

function handleGroupList(data) {
    if (!Array.isArray(data)) return;
    groupNames.clear();
    const list = [];
    for (const g of data) {
        if (!g) continue;
        const id = String(g.group_id != null ? g.group_id : g.groupId);
        if (!id) continue;
        const name = sanitizeText(g.group_name || g.groupName || ('群' + id));
        groupNames.set(id, name);
        list.push({ id, name });
    }
    emitEvent({ event: 'groups', groups: list });
}

function handleObj(obj) {
    if (!obj || typeof obj !== 'object') return;
    if (obj.echo && pendingActions.has(obj.echo)) {
        const resolve = pendingActions.get(obj.echo);
        pendingActions.delete(obj.echo);
        resolve(obj);
        return;
    }
    if (obj.echo === 'get_group_list') { handleGroupList(obj.data); return; }
    if (obj.post_type === 'meta_event') {
        if (obj.self_id != null) selfId = String(obj.self_id);
        if (obj.meta_event_type === 'lifecycle' && obj.self_id != null) {
            setStatus('connected', { selfId });
        }
        return;
    }
    if (obj.post_type !== 'message') return;
    const type = obj.message_type === 'private' ? 'private' : 'group';
    if (type !== 'group') return;

    const groupId = String(obj.group_id);
    if (ignoreFilter.has(groupId)) return;
    if (groupFilter.size && !groupFilter.has(groupId)) return;

    const message = obj.message != null ? obj.message : obj.raw_message;
    const content = extractText(message);
    const mentioned = isMentioned(message);
    const atAll = isAtAll(message);
    if (!content && !mentioned) return;

    emitEvent({
        event: 'groupMessage',
        groupId,
        groupName: sanitizeText(groupName(groupId)),
        sender: sanitizeText(senderName(obj)),
        senderId: String((obj.sender || {}).user_id != null ? obj.sender.user_id : ''),
        content,
        mentioned,
        atAll,
        raw: sanitizeText(obj.raw_message || '')
    });
}

let processChain = Promise.resolve();
function handleRaw(data) {
    if (data == null) return;
    let text = typeof data === 'string' ? data : data.toString('utf8');
    text = text.trim();
    if (!text) return;
    let obj;
    try { obj = JSON.parse(text); } catch (e) { return; }
    if (!Array.isArray(obj) && obj.echo && pendingActions.has(obj.echo)) {
        const resolve = pendingActions.get(obj.echo); pendingActions.delete(obj.echo); resolve(obj); return;
    }
    processChain = processChain
        .then(() => (Array.isArray(obj) ? obj.forEach(handleObj) : handleObj(obj)))
        .catch(() => {});
}

function scheduleReconnect(reason) {
    if (stopped || mode !== 'forward') return;
    if (!autoReconnect) { log('info', '自动重连已关闭（' + reason + '）。'); return; }
    if (restricted) log('warn', '账号可能受限，将以低频继续尝试重连。');
    retry += 1;
    const delay = Math.min(30000, 1000 * Math.pow(2, Math.min(retry, 5)));
    log('warn', 'QQ 连接断开（' + reason + '），' + Math.round(delay / 1000) + ' 秒后重连…');
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connectForward, delay);
}

function connectForward() {
    if (stopped || mode !== 'forward') return;
    let url = String(config.url || '').trim() || 'ws://127.0.0.1:3001';
    if (accessToken && !/[?&]access_token=/.test(url)) {
        url += (url.indexOf('?') >= 0 ? '&' : '?') + 'access_token=' + encodeURIComponent(accessToken);
    }
    const options = {};
    if (accessToken) options.headers = { Authorization: 'Bearer ' + accessToken };

    let ws;
    try { ws = new WebSocket(url, options); }
    catch (e) { logError('无法创建 WebSocket: ' + (e && e.message)); scheduleReconnect('create failed'); return; }
    forwardWs = ws;

    ws.on('open', () => {
        retry = 0;
        log('info', '已连接 OneBot 正向 WebSocket: ' + url);
        setStatus('connected');
        sendAction('get_group_list', {}, 'get_group_list');
        refreshSelfId();
        startHealthCheck();
    });
    ws.on('message', (data) => handleRaw(data));
    ws.on('close', (code, reason) => {
        stopHealthCheck();
        const why = reason ? reason.toString() : String(code);
        if (lastState !== 'disconnected') setStatus('disconnected');
        scheduleReconnect('closed ' + why);
    });
    ws.on('error', (err) => {
        const code = err && err.code;
        const msg = err && err.message ? err.message : String(err);
        if (code === 'ECONNREFUSED') {
            logError('无法连接 ' + url + '（ECONNREFUSED）。请确认 SnowLuma/NapCat 已启动并开启正向 WS。');
        } else { logError('QQ WebSocket 错误: ' + msg); }
    });
}

function startReverse() {
    if (typeof WebSocket.Server !== 'function') {
        logError('当前 ws 版本不支持反向 WebSocket，请用正向模式。');
        emitEvent({ event: 'end', reason: 'reverse-unsupported' }); process.exit(1);
    }
    let wss;
    try { wss = new WebSocket.Server({ host: listenHost, port: listenPort }); }
    catch (e) { logError('无法监听 ' + listenHost + ':' + listenPort + ' -> ' + (e && e.message));
        emitEvent({ event: 'end', reason: 'listen-failed' }); process.exit(1); }

    wss.on('listening', () => log('info', 'QQ 反向 WebSocket 正在监听 ' + listenHost + ':' + listenPort));
    wss.on('connection', (ws, req) => {
        if (accessToken) {
            const header = (req.headers && (req.headers['authorization'] || req.headers['Authorization'])) || '';
            let token = String(header).replace(/^Bearer\s+/i, '').trim();
            if (!token && req.url && req.url.indexOf('access_token=') >= 0) {
                for (const pair of (req.url.split('?')[1] || '').split('&')) {
                    const kv = pair.split('=');
                    if (kv[0] === 'access_token') token = decodeURIComponent(kv[1] || '');
                }
            }
            if (token !== accessToken) { log('warn', '拒绝未授权连接。'); try { ws.close(1008, 'invalid token'); } catch (e) {} return; }
        }
        clients.add(ws);
        log('info', 'OneBot 反向连接已建立。');
        setStatus('connected');
        sendAction('get_group_list', {}, 'get_group_list');
        refreshSelfId();
        startHealthCheck();
        ws.on('message', (data) => handleRaw(data));
        const drop = () => { clients.delete(ws); if (clients.size === 0) { stopHealthCheck(); setStatus('disconnected'); } };
        ws.on('close', drop); ws.on('error', drop);
    });
    wss.on('error', (err) => logError('反向 WebSocket 错误: ' + (err && err.message ? err.message : String(err))));
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });
function handleCommand(cmd) {
    switch (cmd.type) {
        case 'sendGroup': {
            const gid = String(cmd.groupId == null ? '' : cmd.groupId).trim();
            let text = String(cmd.text || '');
            if (!gid || !text) return;
            if (cmd.atSender) text = '[CQ:at,qq=' + String(cmd.atSender) + '] ' + text;
            sendAction('send_group_msg', { group_id: gid, message: text });
            break;
        }
        case 'sendGroupMusic': {
            const gid = String(cmd.groupId == null ? '' : cmd.groupId).trim();
            if (!gid) return;
            const platform = String(cmd.platform || '163');
            let card;
            if (platform === 'custom') {
                const audio = String(cmd.audio || '');
                if (!audio) { log('warn', '自定义音乐卡片缺少音频地址，已跳过。'); return; }
                card = '[CQ:music,type=custom'
                    + ',url=' + cqEscape(cmd.url || audio)
                    + ',audio=' + cqEscape(audio)
                    + ',title=' + cqEscape(cmd.title || '')
                    + ',image=' + cqEscape(cmd.image || '') + ']';
            } else {
                if (!cmd.songId) { log('warn', '音乐卡片缺少歌曲 id，已跳过。'); return; }
                card = '[CQ:music,type=' + cqEscape(platform)
                    + ',id=' + cqEscape(cmd.songId) + ']';
            }
            actionAsync('send_group_msg', { group_id: gid, message: card }, 8000)
                .then((res) => {
                    const ok = res && (res.status === 'ok' ||
                        (res.retcode != null && res.retcode === 0));
                    if (!ok) {
                        log('warn', '音乐卡片发送失败: ' +
                            JSON.stringify((res && (res.message || res.wording)) || res));
                    }
                });
            break;
        }
        case 'setGroups':
            groupFilter = new Set((cmd.groups || []).map((g) => String(g).trim()).filter(Boolean));
            log('info', '群白名单：' + (groupFilter.size ? Array.from(groupFilter).join(',') : '全部群'));
            break;
        case 'setIgnoreGroups':
            ignoreFilter = new Set((cmd.groups || []).map((g) => String(g).trim()).filter(Boolean));
            break;
        case 'ping': emitEvent({ event: 'pong' }); break;
        case 'quit':
            stopped = true; stopHealthCheck();
            if (reconnectTimer) clearTimeout(reconnectTimer);
            try { if (forwardWs) forwardWs.close(); } catch (e) {}
            for (const ws of clients) { try { ws.close(); } catch (e) {} }
            emitEvent({ event: 'end', reason: 'quit' });
            setTimeout(() => process.exit(0), 100);
            break;
        default: log('warn', '未知命令: ' + cmd.type);
    }
}
rl.on('line', (line) => {
    line = line.trim(); if (!line) return;
    let cmd; try { cmd = JSON.parse(line); } catch (e) { logError('非法命令: ' + line); return; }
    try { handleCommand(cmd); } catch (e) { logError('命令执行出错: ' + e.message); }
});

process.on('SIGINT', () => handleCommand({ type: 'quit' }));
process.on('SIGTERM', () => handleCommand({ type: 'quit' }));

if (mode === 'reverse') startReverse(); else connectForward();
log('info', 'QQ 引擎已启动（模式: ' + mode + '）。');
