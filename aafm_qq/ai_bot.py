"""The AI "group member": decides when to reply and asks the LLM.

A background worker consumes group messages so the engine reader / GUI never
block on a slow LLM request. Context (recent lines per group) is kept in memory
so replies feel like real group chat.
"""
from __future__ import annotations

import queue
import random
import re
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, List, Optional

from . import llm, websearch
from .config import AiConfig

# 粗估 token：CJK 约 1 token/字，其它字符约 4 字符/token（不需要精确，够用就行）
_CJK_RE = re.compile(r'[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]')
# 句子边界（保留分隔符）
_SENT_RE = re.compile(r'(?<=[。！？!?；;…\n])')


def estimate_tokens(text: str) -> int:
    s = str(text or '')
    if not s:
        return 0
    cjk = len(_CJK_RE.findall(s))
    return cjk + (len(s) - cjk + 3) // 4


def _trim_sentences(line: str, max_tokens: int) -> str:
    """按句子把一行裁到 ``max_tokens`` 以内（尽量不切断语义）。"""
    parts = [p for p in _SENT_RE.split(str(line or '')) if p]
    out = ''
    for p in parts:
        if estimate_tokens(out + p) > max_tokens:
            break
        out += p
    if out.strip():
        return out.strip()
    keep = max(8, int(max_tokens * 1.2))
    return str(line or '')[:keep].rstrip() + '…'


class AiBot:
    def __init__(self, config: AiConfig,
                 send_group: Callable[[str, str, str, str], bool],
                 on_log: Callable[[str, str], None],
                 affinity: Optional[object] = None,
                 send_private: Optional[Callable[[str, str, str], bool]] = None):
        self.config = config
        self._send_group = send_group   # (groupId, text, atSender, replyTo) -> bool
        # (userId, text, replyTo) -> bool；私聊（好友 / 临时会话）走这条
        self._send_private = send_private or (lambda *a, **k: False)
        self._log = on_log              # (level, message)
        # Optional 好感度 store (aafm_qq.affinity.Affinity): used to colour the
        # persona prompt and to reward members who chat with the bot.
        self._affinity = affinity
        self._q: "queue.Queue[dict]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._contexts: Dict[str, Deque[str]] = {}
        self._last_reply_at: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.self_id = ''

    # ------------------------------------------------------------------
    def load(self, config: AiConfig) -> None:
        self.config = config

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def clear_context(self) -> None:
        with self._lock:
            self._contexts.clear()

    def feed(self, ev: dict) -> None:
        if self._running:
            self._q.put(ev)

    # ------------------------------------------------------------------
    def _context(self, group_id: str) -> Deque[str]:
        want = max(0, int(self.config.contextLength or 0))
        with self._lock:
            buf = self._contexts.get(group_id)
            if buf is None or buf.maxlen != want:
                buf = deque(buf or (), maxlen=want)
                self._contexts[group_id] = buf
            return buf

    # ------------------------------------------------------------------
    # 上下文：按 token 预算取「触发消息之前的一段历史」
    # ------------------------------------------------------------------
    def _build_history(self, group_id: str, budget: int) -> str:
        """从最近往回取，直到用完 ``budget``；太长的那一行按句子裁。"""
        lines = list(self._context(group_id))
        if not lines:
            return ''
        if budget <= 0:
            return '\n'.join(lines)
        picked: List[str] = []
        used = 0
        for line in reversed(lines):
            cost = estimate_tokens(line) + 1      # +1：换行/分隔
            if used + cost <= budget:
                picked.append(line)
                used += cost
                continue
            room = budget - used
            if room >= 12:
                trimmed = _trim_sentences(line, room)
                if trimmed:
                    picked.append(trimmed)
            break
        picked.reverse()
        return '\n'.join(picked)

    def _search_query(self, content: str) -> str:
        """把消息变成搜索词：去掉开头的触发词 / @，压成一跑，限长。"""
        text = (content or '').strip()
        for tok in self._trigger_literals():
            if tok and text.lower().startswith(tok.lower()):
                text = text[len(tok):].lstrip()
                break
        text = re.sub(r'^(@\S+\s*)+', '', text).strip()
        text = re.sub(r'\s+', ' ', text)
        return text[:80]

    def _maybe_search(self, content: str) -> str:
        """按配置决定要不要联网搜。返回给模型看的文本（''=没搜/没结果）。"""
        cfg = self.config
        if not cfg.searchEnabled:
            return ''
        query = self._search_query(content)
        if not query:
            return ''
        if (cfg.searchMode or 'keywords').lower() != 'always':
            kws = [k.strip() for k in re.split(r'[,，]', cfg.searchKeywords or '') if k.strip()]
            low = content.lower()
            if not any(k.lower() in low for k in kws):
                return ''
        items, err = websearch.search_ex(query, cfg)
        if not items:
            self._log('warn', f'[联网搜索] 「{query}」没搜到：{err}')
            return ''
        self._log('info', f'[联网搜索] 「{query}」→ {len(items)} 条结果')
        return websearch.format_results(items)

    def _trigger_literals(self) -> List[str]:
        """The user-configured trigger word(s) as literal strings.

        ``triggerWord`` is a plain string the user types in (e.g. ``[AI]``);
        comma-separated values are all accepted. These are matched at the START
        of an incoming message, and stripped from outgoing replies.
        """
        raw = (self.config.triggerWord or '').strip()
        return [p.strip() for p in re.split(r'[,，]', raw) if p.strip()]

    def _compile_triggers(self) -> List[re.Pattern]:
        pats: List[re.Pattern] = []
        # 1) The user's trigger word: the message must START with it.
        for w in self._trigger_literals():
            try:
                pats.append(re.compile(r'^\s*' + re.escape(w), re.IGNORECASE))
            except re.error:
                continue
        # 2) Optional advanced regex (searched anywhere).
        raw = (self.config.triggerRegex or '').strip()
        for p in [x.strip() for x in re.split(r'[,，]', raw) if x.strip()]:
            try:
                pats.append(re.compile(p))
            except re.error:
                continue
        return pats

    def _is_blacklisted(self, sender_id: str) -> bool:
        if not sender_id:
            return False
        for b in self.config.blacklist or []:
            if str(b.get('id') or '') == str(sender_id):
                return True
        return False

    def _should_reply(self, ev: dict) -> bool:
        cfg = self.config
        if self._is_blacklisted(str(ev.get('senderId') or ev.get('userId') or '')):
            return False
        if ev.get('isPrivate'):
            # 私聊（聊天页面）：默认每条都回，不用触发词。
            if not cfg.privateReplyEnabled:
                return False
            if cfg.privateAlwaysReply:
                return True
        elif ev.get('mentioned') and cfg.mentionReply:
            return True
        content = ev.get('content') or ''
        if cfg.triggerEnabled:
            for pat in self._compile_triggers():
                if pat.search(content):
                    return True
        if not ev.get('isPrivate') and cfg.autoReply \
                and random.randint(1, 100) <= max(0, min(100, cfg.autoReplyChance)):
            return True
        return False

    @staticmethod
    def _conv_key(ev: dict) -> str:
        """上下文按会话分开：群聊一个群一份，私聊一个人一份。"""
        if ev.get('isPrivate'):
            return 'private:' + str(ev.get('userId') or '')
        return 'group:' + str(ev.get('groupId') or '')

    # ------------------------------------------------------------------
    def _loop(self) -> None:
        while self._running:
            try:
                ev = self._q.get(timeout=0.3)
            except queue.Empty:
                continue
            try:
                self._handle(ev)
            except Exception as e:  # noqa: BLE001
                self._log('error', 'AI 处理出错: ' + str(e))

    def _handle(self, ev: dict) -> None:
        is_private = bool(ev.get('isPrivate'))
        group_id = str(ev.get('groupId') or '')
        user_id = str((ev.get('userId') if is_private else ev.get('senderId')) or '')
        content = (ev.get('content') or '').strip()
        sender = ev.get('sender') or ('好友' if is_private else '群友')
        if is_private:
            if not user_id:
                return
        elif not group_id:
            return
        # Skip our own messages.
        if self.self_id and user_id and user_id == str(self.self_id):
            return
        conv = self._conv_key(ev)
        # 好感度按群记；私聊统一放在 'private' 这个桶里（同一个人跨群私聊分数一致）
        aff_key = 'private' if is_private else group_id
        if content:
            self._context(conv).append(f'{sender}: {content}')

        if not self.config.enabled or not self._should_reply(ev):
            return

        now = time.time()
        cooldown = int(self.config.cooldownSeconds or 0)
        if cooldown and now - self._last_reply_at.get(conv, 0) < cooldown:
            return
        # Record the attempt before calling the model: a failing LLM must not be
        # hammered by every matching message (there is no reply to timestamp).
        self._last_reply_at[conv] = now

        reply = self._ask(conv, sender, content, user_id,
                          aff_key=aff_key, is_private=is_private)
        if not reply:
            return
        reply = self._sanitize_reply(reply)
        if not reply:
            return
        sent = 0
        # 只引用第一条：把触发消息的 id 作为消息段第一位（不用 LLM 参与）。
        quote = str(ev.get('messageId') or '') if self.config.quoteReply else ''
        for idx, line in enumerate(self._split_reply(reply)):
            reply_to = quote if idx == 0 else ''
            if is_private:
                ok = self._send_private(user_id, line, reply_to)
            else:
                at = user_id if self.config.atReply else ''
                ok = self._send_group(group_id, line, at, reply_to)
            if ok:
                self._context(conv).append(f'我: {line}')
                sent += 1
            time.sleep(0.6)
        if sent and self._affinity is not None:
            try:  # 被搭话就涨好感度（受每日上限约束）
                self._affinity.add(aff_key, user_id, sender)
            except Exception as e:  # noqa: BLE001
                self._log('warn', '好感度更新失败: ' + str(e))

    def _ask(self, group_id: str, sender: str, content: str, sender_id: str = '',
             aff_key: str = '', is_private: bool = False) -> str:
        cfg = self.config
        try:
            provider = llm.create_provider(cfg)
        except llm.LLMError as e:
            self._log('error', 'LLM 初始化失败: ' + str(e))
            return ''
        try:
            if cfg.contextEnabled:
                history = self._build_history(group_id,
                                              int(cfg.contextTokenBudget or 0))
            else:
                history = ''
            lines = history or f'{sender}: {content}'
            if is_private:
                user = f'以下是你们最近的私聊记录：\n{lines}\n\n'
            else:
                user = f'以下是 QQ 群最近的聊天记录：\n{lines}\n\n'
            searched = self._maybe_search(content)
            if searched:
                user += ('我刚查到的联网搜索结果（可能过时，仅供参考；'
                         '能用就用，别编造）：\n' + searched + '\n\n')
            if is_private:
                user += (f'请直接回他一句（口语、简短，最多 '
                         f'{int(cfg.maxReplyMessages)} 句）。')
            else:
                user += (f'请以群友身份接一句话回复（口语、简短，最多 '
                         f'{int(cfg.maxReplyMessages)} 句）。')
            system_prompt = cfg.systemPrompt
            if self._affinity is not None:
                hint = self._affinity.hint(aff_key or group_id, sender_id, sender)
                if hint:
                    system_prompt = f'{system_prompt}\n{hint}'
            text = provider.send(system_prompt, [{'role': 'user', 'content': user}])
        except Exception as e:  # noqa: BLE001
            self._log('error', 'LLM 请求失败: ' + str(e))
            return ''
        finally:
            provider.close()
        return self._clean(text)

    def _clean(self, text: str) -> str:
        text = (text or '').strip()
        # drop reasoning tags if any
        text = re.sub(r'<think[^>]*>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'^```.*?\n|\n```$', '', text, flags=re.DOTALL).strip()
        # strip a leading "我:" etc.
        text = re.sub(r'^(?:我|AI|助手)\s*[:：]\s*', '', text)
        return text.strip().strip('"“”').strip()

    def _sanitize_reply(self, text: str) -> str:
        """Final guard before sending.

        - Remove the trigger word(s) (e.g. ``[AI]``) so the bot can never inject a
          prompt that would make itself / others re-trigger.
        - Block rude words and the literal ``纯净输出`` leak.
        Returns '' when the whole reply must be dropped.
        """
        cfg = self.config
        text = (text or '').strip()
        if not text:
            return ''
        if cfg.stripTrigger:
            for tok in self._trigger_literals():
                text = re.sub(re.escape(tok), '', text, flags=re.IGNORECASE)
            text = re.sub(r'\s{2,}', ' ', text).strip()
        if not text:
            return ''
        low = text.lower()
        for w in cfg.blockedWords or []:
            w = str(w).strip()
            if w and w.lower() in low:
                self._log('warn', f'回复含违禁词「{w}」，已拦截: {text}')
                return ''
        return text

    def _split_reply(self, text: str) -> List[str]:
        cfg = self.config
        limit = max(1, int(cfg.maxCharsPerMessage or 120))
        max_n = max(1, int(cfg.maxReplyMessages or 2))
        parts: List[str] = []
        for seg in re.split(r'\n+', text):
            seg = seg.strip()
            while seg:
                if len(seg) <= limit:
                    parts.append(seg)
                    seg = ''
                else:
                    parts.append(seg[:limit])
                    seg = seg[limit:]
        return [p for p in parts if p][:max_n]
