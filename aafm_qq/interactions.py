"""Group interactions that go beyond chatting.

Currently two are handled here, both triggered by a message that **starts with**
a configurable word (same convention as the AI trigger):

- 点歌 (``[点歌] 歌名``): search a song and post an OneBot music card.
- 好感度 (``[好感度]``): show the sender how much the bot likes them.

Handled messages are consumed here and never reach the chat AI, so the large
model does not also "answer" a command. This class also owns the :class:`Affinity`
store, which the AI bot uses to colour its persona.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

from . import song
from .affinity import Affinity
from .config import AppConfig


def _after_trigger(content: str, trigger: str) -> Optional[str]:
    """Return the text after ``trigger`` when the message starts with it."""
    t = (trigger or '').strip()
    if not t:
        return None
    m = re.match(r'^\s*' + re.escape(t), content, re.IGNORECASE)
    if not m:
        return None
    return content[m.end():].strip()


class Interactions:
    def __init__(self, config: AppConfig,
                 send_group: Callable[[str, str, str], bool],
                 send_music: Callable[..., bool],
                 on_log: Callable[[str, str], None]) -> None:
        self.config = config
        self._send_group = send_group     # (groupId, text, atSender) -> bool
        self._send_music = send_music     # (**card kwargs) -> bool
        self._log = on_log                # (level, message)
        self.affinity = Affinity(config.affinity, on_log)
        self._last_song_at: dict = {}
        self._lock = threading.Lock()

    def load(self, config: AppConfig) -> None:
        """Re-point at a freshly validated config (GUI mutates it in place)."""
        self.config = config
        self.affinity.config = config.affinity

    # ------------------------------------------------------------------
    def handle(self, ev: dict) -> bool:
        """Try to consume a group message. True when it was a command."""
        content = (ev.get('content') or '').strip()
        group_id = str(ev.get('groupId') or '')
        if not content or not group_id:
            return False
        sender = ev.get('sender') or '群友'
        sender_id = str(ev.get('senderId') or '')

        song_cfg = self.config.song
        if song_cfg.enabled:
            keyword = _after_trigger(content, song_cfg.trigger)
            if keyword is not None:
                self._on_song(group_id, sender_id, keyword, ev)
                return True

        aff_cfg = self.config.affinity
        if aff_cfg.enabled and _after_trigger(content, aff_cfg.queryTrigger) is not None:
            self._on_affinity(group_id, sender, sender_id)
            return True
        return False

    # ------------------------------------------------------------------
    # 点歌
    # ------------------------------------------------------------------
    def _on_song(self, group_id: str, sender_id: str, keyword: str, ev: dict) -> None:
        cfg = self.config.song
        now = time.time()
        cooldown = int(cfg.cooldownSeconds or 0)
        with self._lock:
            if cooldown and now - self._last_song_at.get(group_id, 0) < cooldown:
                return
            self._last_song_at[group_id] = now
        if not keyword:
            self._send_group(
                group_id,
                f'想听什么？发送「{cfg.trigger} 歌名」，例如 {cfg.trigger} 起风了',
                sender_id)
            return
        threading.Thread(target=self._do_song,
                         args=(group_id, sender_id, keyword, ev),
                         daemon=True).start()

    def _do_song(self, group_id: str, sender_id: str, keyword: str, ev: dict) -> None:
        cfg = self.config.song
        gname = ev.get('groupName') or group_id
        self._log('info', f'[{gname}] 点歌: {keyword}')
        try:
            hit = song.search(keyword, cfg.platform, timeout=cfg.timeoutSeconds,
                              log=lambda m: self._log('warn', '点歌 · ' + m))
        except Exception as e:  # noqa: BLE001
            self._log('error', '点歌出错: ' + str(e))
            hit = None
        if not hit:
            self._send_group(group_id, f'没搜到「{keyword}」，换个关键词试试～', sender_id)
            return
        try:
            ok = self._send_music(group_id, **hit.card())
        except Exception as e:  # noqa: BLE001
            self._log('error', '点歌发送出错: ' + str(e))
            ok = False
        if ok:
            self._log('info', f'[{gname}] 已发送音乐卡片: {hit.label()}')
            return
        self._log('warn', f'[{gname}] 音乐卡片发送失败: {hit.label()}')
        link = hit.page_url or hit.audio_url
        tail = f'：{link}' if link else ''
        self._send_group(group_id, f'找到《{hit.label()}》了，但卡片没发出去{tail}', sender_id)

    # ------------------------------------------------------------------
    # 好感度
    # ------------------------------------------------------------------
    def _on_affinity(self, group_id: str, sender: str, sender_id: str) -> None:
        try:
            text = self.affinity.card(group_id, sender_id, sender)
        except Exception as e:  # noqa: BLE001
            self._log('error', '好感度查询出错: ' + str(e))
            return
        self._send_group(group_id, text, sender_id)
