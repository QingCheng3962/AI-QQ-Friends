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

from . import llm
from .config import AiConfig


class AiBot:
    def __init__(self, config: AiConfig,
                 send_group: Callable[[str, str, str], bool],
                 on_log: Callable[[str, str], None]):
        self.config = config
        self._send_group = send_group   # (groupId, text, atSender) -> bool
        self._log = on_log              # (level, message)
        self._q: "queue.Queue[dict]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._contexts: Dict[str, Deque[str]] = {}
        self._last_reply_at: Dict[str, float] = {}
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
        self._contexts.clear()

    def feed(self, ev: dict) -> None:
        if self._running:
            self._q.put(ev)

    # ------------------------------------------------------------------
    def _context(self, group_id: str) -> Deque[str]:
        buf = self._contexts.get(group_id)
        if buf is None:
            buf = deque(maxlen=max(0, int(self.config.contextLength or 20)))
            self._contexts[group_id] = buf
        return buf

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
        if self._is_blacklisted(ev.get('senderId', '')):
            return False
        if ev.get('mentioned') and cfg.mentionReply:
            return True
        content = ev.get('content') or ''
        if cfg.triggerEnabled:
            for pat in self._compile_triggers():
                if pat.search(content):
                    return True
        if cfg.autoReply and random.randint(1, 100) <= max(0, min(100, cfg.autoReplyChance)):
            return True
        return False

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
        group_id = str(ev.get('groupId') or '')
        content = (ev.get('content') or '').strip()
        sender = ev.get('sender') or '群友'
        sender_id = str(ev.get('senderId') or '')
        if not group_id:
            return
        # Skip our own messages.
        if self.self_id and sender_id and sender_id == str(self.self_id):
            return
        if content:
            self._context(group_id).append(f'{sender}: {content}')

        if not self.config.enabled or not self._should_reply(ev):
            return

        now = time.time()
        cooldown = int(self.config.cooldownSeconds or 0)
        if cooldown and now - self._last_reply_at.get(group_id, 0) < cooldown:
            return

        reply = self._ask(group_id, sender, content)
        if not reply:
            return
        reply = self._sanitize_reply(reply)
        if not reply:
            return
        self._last_reply_at[group_id] = now
        for line in self._split_reply(reply):
            at = sender_id if (self.config.atReply and self.config.mentionReply) else ''
            if self._send_group(group_id, line, at):
                self._log('ai', f'[{ev.get("groupName") or group_id}] 回复: {line}')
                self._context(group_id).append(f'我: {line}')
            time.sleep(0.6)

    def _ask(self, group_id: str, sender: str, content: str) -> str:
        cfg = self.config
        try:
            provider = llm.create_provider(cfg)
        except llm.LLMError as e:
            self._log('error', 'LLM 初始化失败: ' + str(e))
            return ''
        try:
            recent = list(self._context(group_id)) if cfg.contextEnabled else []
            recent = recent[-max(1, int(cfg.contextLength or 20)):]
            lines = '\n'.join(recent) if recent else f'{sender}: {content}'
            user = (f'以下是 QQ 群最近的聊天记录：\n{lines}\n\n'
                    f'请以群友身份接一句话回复（口语、简短，最多 '
                    f'{int(cfg.maxReplyMessages)} 句）。')
            text = provider.send(cfg.systemPrompt, [{'role': 'user', 'content': user}])
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
