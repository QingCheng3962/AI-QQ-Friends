"""Controller: ties the OneBot engine, the AI group member and the config.

Also auto-detects the running SnowLuma/NapCat and probes the OneBot WS token so
connecting works on any machine without hand-copying tokens.
"""
from __future__ import annotations

import base64
import json
import os
import queue
import re
import socket
import subprocess
import threading
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from .ai_bot import AiBot
from .config import AppConfig
from .engine import QqEngine, BASE_DIR
from .interactions import Interactions
from .procutil import node_process_paths


class Controller:
    def __init__(self) -> None:
        self.config = AppConfig.load()
        self.ui_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()

        self._engine = QqEngine(cwd=BASE_DIR, on_event=self._on_event)
        self.interactions = Interactions(self.config, self._ai_send,
                                         self._send_music, self._log)
        self.ai = AiBot(self.config.ai, self._ai_send, self._log,
                        affinity=self.interactions.affinity)
        self.ai.self_id = ''

        self._running = False
        self._connected = False
        self._qq_nicknames: Dict[str, str] = {}
        self._snowluma_detected = ''
        self._snowluma_detect_at = 0.0
        self._snowluma_detected_marker = ''
        self._snowluma_uin = ''

    def _log(self, level: str, message: str) -> None:
        self.ui_queue.put({'kind': 'log', 'level': level, 'message': message})

    def drain_ui(self, max_items: int = 500) -> List[Dict[str, Any]]:
        out = []
        try:
            for _ in range(max_items):
                out.append(self.ui_queue.get_nowait())
        except queue.Empty:
            pass
        return out

    def _ai_send(self, group_id: str, text: str, at_sender: str = '') -> bool:
        return self._engine.send_group(group_id, text, at_sender)

    def send_manual(self, group_id: str, text: str) -> bool:
        """Send a test message from the GUI. Returns whether it was queued."""
        return self._engine.send_group(group_id, text)

    def _send_music(self, group_id: str, **card) -> bool:
        return self._engine.send_group_music(group_id, **card)

    # ------------------------------------------------------------------
    # OneBot endpoint auto-detection (SnowLuma / NapCat)
    # ------------------------------------------------------------------
    def _detect_running_dir(self, marker: str) -> str:
        """Find the install dir of a running framework by a marker file.

        For SnowLuma the full Windows package ships its own ``node.exe`` beside
        ``index.mjs``; marker='index.mjs'. NapCat ships ``launcher-win10.bat``.
        """
        now = time.time()
        if (self._snowluma_detected and self._snowluma_detected_marker == marker
                and now - self._snowluma_detect_at < 5):
            return self._snowluma_detected
        found = ''
        try:
            for _ in range(2):
                for p in node_process_paths():
                    d = os.path.dirname(p)
                    if os.path.isfile(os.path.join(d, marker)):
                        found = d
                        break
                if found:
                    break
        except Exception:  # noqa: BLE001
            found = ''
        if found:
            self._snowluma_detected = found
            self._snowluma_detect_at = now
            self._snowluma_detected_marker = marker
        return found

    def _snowluma_config_dir(self) -> str:
        bases = []
        p = (self.config.snowluma.launcherPath or '').strip()
        if p:
            bases.append(p)
        det = self._detect_running_dir('index.mjs')
        if det:
            bases.append(det)
        bases.append(os.path.join(BASE_DIR, 'SnowLuma'))
        for base in bases:
            cfg = os.path.join(base, 'config')
            if os.path.isdir(cfg):
                return cfg
        return os.path.join(bases[0], 'config')

    def _snowluma_candidates(self) -> List[dict]:
        cfg_dir = self._snowluma_config_dir()
        if not os.path.isdir(cfg_dir):
            return []
        try:
            names = [n for n in os.listdir(cfg_dir)
                     if n.startswith('onebot_') and n.endswith('.json')]
        except OSError:
            return []
        last = (self.config.lastLoginUin or '').strip()

        def mtime(n):
            try:
                return os.path.getmtime(os.path.join(cfg_dir, n))
            except OSError:
                return 0.0

        def rank(n):
            uin = n[len('onebot_'):-len('.json')]
            return (0 if (last and uin == last) else 1, -mtime(n))

        out = []
        for name in sorted(names, key=rank):
            try:
                with open(os.path.join(cfg_dir, name), 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:  # noqa: BLE001
                continue
            servers = ((data.get('networks') or {}).get('wsServers') or [])
            if not servers:
                continue
            s = servers[0]
            try:
                port = int(s.get('port') or 3001)
            except (TypeError, ValueError):
                port = 3001
            out.append({'uin': name[len('onebot_'):-len('.json')],
                        'host': str(s.get('host') or '127.0.0.1'),
                        'port': port, 'token': str(s.get('accessToken') or '')})
        return out

    def _probe_ws_token(self, host: str, port: int, token: str, timeout: float = 1.5):
        query = ('?access_token=' + urllib.parse.quote(token, safe='')) if token else ''
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        req = (f'GET /{query} HTTP/1.1\r\nHost: {host}:{port}\r\n'
               'Upgrade: websocket\r\nConnection: Upgrade\r\n'
               f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n')
        try:
            sock = socket.create_connection((host, int(port)), timeout=timeout)
        except OSError:
            return None
        try:
            sock.sendall(req.encode('ascii'))
            data = sock.recv(64)
        except OSError:
            return None
        finally:
            try:
                sock.close()
            except OSError:
                pass
        return data.startswith(b'HTTP/1.1 101') or data.startswith(b'HTTP/1.0 101')

    def snowluma_ws_auth(self):
        """(host, port, token) that actually handshakes with the running SnowLuma."""
        self._snowluma_uin = ''
        cands = self._snowluma_candidates()
        if not cands:
            return None
        for c in cands:
            if self._probe_ws_token(c['host'], c['port'], c['token']):
                self._snowluma_uin = c['uin']
                return (c['host'], c['port'], c['token'])
        c = cands[0]
        self._snowluma_uin = c['uin']
        return (c['host'], c['port'], c['token'])

    def _build_runtime_config(self) -> Dict[str, Any]:
        ep = self.config.active()
        url = (ep.url or '').strip()
        token = ep.accessToken or ''
        if self.config.framework == 'snowluma':
            det = self.snowluma_ws_auth()
            if det:
                host, port, det_token = det
                if det_token:
                    token = det_token
                if not url:
                    url = f'ws://{host}:{port}'
                if self._snowluma_uin:
                    self._log('info', f'[QQ] SnowLuma 账号 UIN={self._snowluma_uin}：'
                                      f'已自动读取端口/token。')
        return {
            'mode': ep.mode,
            'url': url or 'ws://127.0.0.1:3001',
            'accessToken': token,
            'listenHost': ep.listenHost or '0.0.0.0',
            'listenPort': ep.listenPort,
            'groups': list(self.config.groups or []),
            'ignoreGroups': list(self.config.ignoreGroups or []),
            'autoReconnect': bool(self.config.autoReconnect),
            'healthCheckSeconds': int(self.config.healthCheckSeconds),
        }

    # ------------------------------------------------------------------
    # Launch / connect
    # ------------------------------------------------------------------
    def _resolve_launcher(self, path: str):
        if os.path.isdir(path):
            for name in ('launcher.bat', 'launcher-win10.bat', 'launcher.cmd',
                         'launcher.exe', 'start.bat', 'launcher.sh'):
                cand = os.path.join(path, name)
                if os.path.isfile(cand):
                    return self._argv_for(cand), os.path.dirname(cand) or None
            for name in sorted(os.listdir(path)):
                low = name.lower()
                if ('launcher' in low or 'start' in low) and low.endswith(
                        ('.bat', '.cmd', '.exe')):
                    cand = os.path.join(path, name)
                    return self._argv_for(cand), path
            for name in sorted(os.listdir(path)):
                if name.lower().endswith('.exe') and not any(
                        w in name.lower() for w in ('uninstall', 'update', 'remove')):
                    return [os.path.join(path, name)], path
            return None, path
        return self._argv_for(path), os.path.dirname(path) or None

    @staticmethod
    def _argv_for(target: str):
        if target.lower().endswith(('.bat', '.cmd')):
            return ['cmd', '/c', target]
        return [target]

    def launch_framework(self) -> None:
        fw = self.config.framework
        if fw == 'napcat':
            path = (self.config.napcat.launcherPath or '').strip()
        else:
            path = (self.config.snowluma.launcherPath or '').strip()
            if not path or not os.path.exists(path):
                path = self._detect_running_dir('index.mjs') or os.path.join(BASE_DIR, 'SnowLuma')
        if not path or not os.path.exists(path):
            self._log('error', f'未找到启动路径（{fw}）。请在「连接」页填写它的目录。')
            return
        argv, cwd = self._resolve_launcher(path)
        if not argv:
            self._log('error', f'在 {path} 里找不到启动文件（launcher.bat/.exe）。')
            return
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(argv, cwd=cwd, **kwargs)
            self._log('info', f'已启动 {fw}：{argv[-1]}')
        except Exception as e:  # noqa: BLE001
            self._log('error', f'启动 {fw} 失败: {e}')

    def start_qq(self) -> None:
        if self._engine.running:
            # push live settings
            try:
                self._engine.set_groups(self.config.groups or [])
                self._engine.set_ignore_groups(self.config.ignoreGroups or [])
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            self._engine.start(self._build_runtime_config())
        except Exception as e:  # noqa: BLE001
            self._log('error', '启动 QQ 引擎失败: ' + str(e))
            return
        self._running = True
        self.ai.load(self.config.ai)
        self.ai.start()
        self.ui_queue.put({'kind': 'status', 'state': 'connecting'})
        self._log('info', 'QQ 引擎已启动。')

    def restart_qq(self) -> None:
        self.stop_qq()
        self.start_qq()

    def stop_qq(self) -> None:
        self._engine.stop()
        self._running = False
        self._connected = False
        self.ui_queue.put({'kind': 'status', 'state': 'disconnected'})

    # ------------------------------------------------------------------
    # Events from the engine
    # ------------------------------------------------------------------
    def _on_event(self, ev: Dict[str, Any]) -> None:
        self.ui_queue.put(ev)
        if ev.get('event') != 'groupMessage':
            return
        # Ignore our own messages so the bot never reacts to itself.
        sender_id = str(ev.get('senderId') or '')
        self_id = str(getattr(self.ai, 'self_id', '') or '')
        if self_id and sender_id and sender_id == self_id:
            return
        # 点歌 / 好感度 等命令先处理；命中就不再交给聊天 AI。
        try:
            if self.interactions.handle(ev):
                return
        except Exception as e:  # noqa: BLE001
            self._log('error', '互动功能出错: ' + str(e))
        self.ai.feed(ev)

    def set_ai_enabled(self, enabled: bool) -> None:
        self.config.ai.enabled = bool(enabled)
        self.ai.load(self.config.ai)
        self.config.save()
        self._log('info', 'AI 群友已' + ('启用' if enabled else '禁用') + '。')

    def reload_ai(self) -> None:
        self.config.ai.validate()
        self.config.song.validate()
        self.config.affinity.validate()
        self.ai.load(self.config.ai)
        self.interactions.load(self.config)
        self._log('info', 'AI / 互动配置已重载。')

    def clear_affinity(self) -> None:
        self.interactions.affinity.clear()
        self._log('info', '好感度已清空。')

    def clear_context(self) -> None:
        self.ai.clear_context()
        self._log('info', '上下文已清空。')

    def set_self_id(self, self_id: str) -> None:
        self.ai.self_id = str(self_id or '')

    def shutdown(self) -> None:
        self.stop_qq()
