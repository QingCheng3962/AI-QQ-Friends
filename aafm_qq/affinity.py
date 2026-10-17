"""好感度: a per-(group, member) score that grows as members chat with the bot.

The score is used in two ways:

- it is injected into the persona prompt so the bot is noticeably warmer to
  members it has "known" longer (see :meth:`hint`), and
- members can look it up in-group with a trigger word (see :meth:`card`).

State is kept in memory and optionally persisted to ``affinity.json`` next to
the program. Writes are throttled, so a busy group does not hammer the disk.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Dict, Optional

from .config import BASE_DIR, AffinityConfig, affinity_title

AFFINITY_FILE = os.path.join(BASE_DIR, 'affinity.json')
_SAVE_INTERVAL = 20.0


class Affinity:
    def __init__(self, config: AffinityConfig,
                 on_log: Optional[Callable[[str, str], None]] = None) -> None:
        self.config = config
        self._log = on_log or (lambda level, msg: None)
        self._lock = threading.Lock()
        # group_id -> {user_id: {'score': int, 'name': str, 'day': 'YYYY-MM-DD',
        #                        'today': int}}
        self._data: Dict[str, Dict[str, dict]] = {}
        self._last_save = 0.0
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        if not os.path.exists(AFFINITY_FILE):
            return
        try:
            with open(AFFINITY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data = {str(g): dict(v or {}) for g, v in data.items()
                              if isinstance(v, dict)}
        except Exception as e:  # noqa: BLE001
            self._log('warn', f'好感度数据读取失败: {e}')

    def save(self, force: bool = False) -> None:
        if not self.config.persist:
            return
        now = time.time()
        if not force and now - self._last_save < _SAVE_INTERVAL:
            return
        self._last_save = now
        try:
            with open(AFFINITY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001
            self._log('warn', f'好感度数据保存失败: {e}')

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
        self.save(force=True)

    # ------------------------------------------------------------------
    def _entry(self, group_id: str, user_id: str, name: str = '') -> dict:
        bucket = self._data.setdefault(str(group_id), {})
        rec = bucket.get(str(user_id))
        if rec is None:
            rec = {'score': int(self.config.start), 'name': str(name or ''),
                   'day': '', 'today': 0}
            bucket[str(user_id)] = rec
        elif name and not rec.get('name'):
            rec['name'] = str(name)
        return rec

    def score(self, group_id: str, user_id: str) -> int:
        with self._lock:
            return int(self._entry(group_id, user_id).get('score', self.config.start))

    @staticmethod
    def title(score: int) -> str:
        return affinity_title(int(score))

    def add(self, group_id: str, user_id: str, name: str = '',
            amount: Optional[int] = None) -> int:
        """Increase a member's score (respecting the daily cap). Returns it."""
        cfg = self.config
        gain = int(cfg.gainPerChat if amount is None else amount)
        if gain <= 0:
            return self.score(group_id, user_id)
        day = time.strftime('%Y-%m-%d')
        with self._lock:
            rec = self._entry(group_id, user_id, name)
            if rec.get('day') != day:
                rec['day'] = day
                rec['today'] = 0
            allowed = gain
            if cfg.dailyCap > 0:
                allowed = min(gain, max(0, cfg.dailyCap - int(rec.get('today', 0))))
            if allowed <= 0:
                return int(rec.get('score', cfg.start))
            rec['score'] = min(int(cfg.maximum), int(rec.get('score', cfg.start)) + allowed)
            rec['today'] = int(rec.get('today', 0)) + allowed
            score = int(rec['score'])
        self.save()
        return score

    # ------------------------------------------------------------------
    def hint(self, group_id: str, user_id: str, name: str = '') -> str:
        """A short line to append to the persona prompt, or '' when disabled."""
        if not self.config.enabled or not self.config.promptHint:
            return ''
        try:
            score = self.score(group_id, user_id)
        except Exception:  # noqa: BLE001
            return ''
        title = self.title(score)
        who = name or '对方'
        maximum = max(1, int(self.config.maximum or 100))
        if score >= 80:
            tone = '你和他很熟，语气可以热络、随意、带点亲近感'
        elif score >= 60:
            tone = '你把他当熟人，说话轻松自然'
        elif score >= 40:
            tone = '你和他算朋友，正常聊就行'
        elif score >= 20:
            tone = '你对他只是眼熟，语气礼貌但不用太热情'
        else:
            tone = '你们还不熟，语气客气、保持距离'
        return (f'【好感度】你对 {who} 的好感度是 {score}/{maximum}（{title}）：{tone}。'
                f'这只是你的态度参考，不要直接说出数字或“好感度”这个词。')

    def card(self, group_id: str, user_id: str, name: str = '') -> str:
        """The in-group reply text for a 好感度 query."""
        score = self.score(group_id, user_id)
        title = self.title(score)
        maximum = max(1, int(self.config.maximum or 100))
        filled = max(0, min(10, round(score / maximum * 10)))
        bar = '█' * filled + '░' * (10 - filled)
        who = name or '你'
        return f'{who} 对我的好感度：{bar} {score}/{maximum}（{title}）'
