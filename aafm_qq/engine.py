"""Bridge to the Node.js OneBot 11 engine (bot_engine.js) over stdio."""
from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any, Callable, Dict, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_CONFIG_FILE = os.path.join(BASE_DIR, 'runtime_config.json')


class QqEngine:
    def __init__(self, node_bin: str = 'node', cwd: Optional[str] = None,
                 on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.node_bin = node_bin
        self.cwd = cwd or BASE_DIR
        self.on_event = on_event
        self.proc: Optional[subprocess.Popen] = None
        self._write_lock = threading.Lock()
        self._running = False
        self._stopping = False

    @property
    def running(self) -> bool:
        return self._running and self.proc is not None and self.proc.poll() is None

    def start(self, runtime_config: Dict[str, Any]) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.stop()
        with open(RUNTIME_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(runtime_config, f, ensure_ascii=False, indent=2)
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        self.proc = subprocess.Popen(
            [self.node_bin, 'bot_engine.js', RUNTIME_CONFIG_FILE],
            cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding='utf-8',
            errors='replace', bufsize=1, **kwargs)
        self._running = True
        self._stopping = False
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        try:
            for line in self.proc.stdout:
                line = (line or '').strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    ev = {'event': 'log', 'level': 'info', 'message': line}
                if self.on_event:
                    try:
                        self.on_event(ev)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._running = False
            # Notify the app when the engine exits on its own (crash / kill),
            # so the UI does not keep showing "connected".
            if not self._stopping and self.on_event:
                try:
                    self.on_event({'event': 'end', 'reason': 'engine-exited'})
                except Exception:  # noqa: BLE001
                    pass

    def _read_stderr(self) -> None:
        try:
            for line in self.proc.stderr:
                line = (line or '').strip()
                if line and self.on_event:
                    try:
                        self.on_event({'event': 'log', 'level': 'error',
                                       'message': '[engine] ' + line})
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

    def send(self, cmd: Dict[str, Any]) -> bool:
        if not self.running or self.proc is None or self.proc.stdin is None:
            return False
        try:
            with self._write_lock:
                self.proc.stdin.write(json.dumps(cmd, ensure_ascii=False) + '\n')
                self.proc.stdin.flush()
            return True
        except Exception:  # noqa: BLE001
            return False

    def send_group(self, group_id: str, text: str, at_sender: str = '',
                   reply_to: str = '') -> bool:
        return self.send({'type': 'sendGroup', 'groupId': str(group_id),
                          'text': text, 'atSender': str(at_sender or ''),
                          'replyTo': str(reply_to or '')})

    def send_private(self, user_id: str, text: str, reply_to: str = '') -> bool:
        """私聊发消息（好友 / 临时会话）。"""
        return self.send({'type': 'sendPrivate', 'userId': str(user_id),
                          'text': text, 'replyTo': str(reply_to or '')})

    def send_action(self, action: str, params: Optional[Dict[str, Any]] = None) -> bool:
        """Run any OneBot 11 action through the engine (e.g. ``send_poke``)."""
        return self.send({'type': 'action', 'action': str(action or ''),
                          'params': dict(params or {})})

    def send_poke(self, group_id: str, user_id: str) -> bool:
        """拍一拍群成员（OneBot 11 ``send_poke``）。"""
        return self.send_action('send_poke', {'group_id': str(group_id),
                                              'user_id': str(user_id)})

    def approve_friend(self, flag: str) -> bool:
        """自动同意好友申请。"""
        return self.send_action('set_friend_add_request',
                                {'flag': str(flag), 'approve': True})

    def approve_group(self, flag: str, sub_type: str = 'add') -> bool:
        """自动同意加群申请 / 入群邀请（``sub_type``: add / invite）。"""
        return self.send_action('set_group_add_request',
                                {'flag': str(flag),
                                 'sub_type': str(sub_type or 'add'),
                                 'approve': True})

    def send_group_music(self, group_id: str, platform: str = '163', songId: str = '',
                         title: str = '', artist: str = '', audio: str = '',
                         url: str = '', image: str = '') -> bool:
        """Post a music card. ``platform`` = qq / 163 / custom (see song.SongHit)."""
        return self.send({'type': 'sendGroupMusic', 'groupId': str(group_id),
                          'platform': str(platform or '163'), 'songId': str(songId or ''),
                          'title': title, 'artist': artist, 'audio': audio,
                          'url': url, 'image': image})

    def set_groups(self, groups) -> bool:
        return self.send({'type': 'setGroups', 'groups': [str(g) for g in (groups or [])]})

    def set_ignore_groups(self, groups) -> bool:
        return self.send({'type': 'setIgnoreGroups', 'groups': [str(g) for g in (groups or [])]})

    def ping(self) -> bool:
        return self.send({'type': 'ping'})

    def stop(self) -> None:
        self._stopping = True
        try:
            self.send({'type': 'quit'})
        except Exception:  # noqa: BLE001
            pass
        if self.proc is not None:
            try:
                self.proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                try:
                    self.proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
        self._running = False
