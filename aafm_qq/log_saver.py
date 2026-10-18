"""聊天 / 系统日志落盘。

所有显示在「日志」页的行都会被缓冲到内存，**程序关闭时写盘**（跨天运行时也会
自动切一次）。每个群一个文件，文件名形如：
``[2026-10-18][123456][群名][1].log``；连接 / 系统类日志落在
``[2026-10-18][000000][系统][1].log``。

文件名里的「保存次数」= 当天第几次保存（关闭程序 / 跨天），由已存在的文件推算，
所以一天内多次开关程序会得到 ``[1] [2] [3] …``，历史文件不会被覆盖。

纯标准库，无 UI 依赖；Controller 持有一个 :class:`LogSaver`。
"""
from __future__ import annotations

import datetime
import os
import re
import threading
from typing import Dict, List, Tuple

DEFAULT_LOG_DIR = 'logs'
SYSTEM_GID = '000000'
SYSTEM_GNAME = '系统'
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(text: str, limit: int = 40) -> str:
    """把群名里的非法文件名字符换掉，并限制长度。"""
    s = _ILLEGAL.sub('_', str(text or '').strip()) or SYSTEM_GNAME
    return s[:limit]


class LogSaver:
    def __init__(self, base_dir: str, log_dir: str = DEFAULT_LOG_DIR,
                 enabled: bool = True):
        self.base_dir = base_dir
        self.enabled = bool(enabled)
        self.dir = log_dir if os.path.isabs(log_dir) else os.path.join(base_dir, log_dir)
        self._lock = threading.Lock()
        # (group_id, group_name) -> [已格式化好的日志行]
        self._groups: Dict[Tuple[str, str], List[str]] = {}
        self._date: datetime.date | None = None   # 当前缓冲属于哪一天

    # ------------------------------------------------------------------
    def record(self, line, group_id: str = '', group_name: str = '') -> None:
        """缓冲一行（行已带时间戳与格式）。"""
        if not self.enabled:
            return
        text = str(line or '').rstrip('\n')
        if not text:
            return
        gid = str(group_id or SYSTEM_GID).strip() or SYSTEM_GID
        gname = str(group_name or '').strip() or SYSTEM_GNAME
        key = (gid, gname)
        with self._lock:
            if self._date is None:
                self._date = datetime.date.today()
            self._groups.setdefault(key, []).append(text)

    # ------------------------------------------------------------------
    def maybe_roll(self) -> List[str]:
        """跨天时把缓冲写盘。返回写出的文件路径列表。"""
        if not self.enabled:
            return []
        today = datetime.date.today()
        with self._lock:
            if self._date is None or self._date == today:
                return []
            date = self._date
        return self._save(date)

    def flush(self) -> List[str]:
        """把当前缓冲写盘（程序关闭时调用）。"""
        if not self.enabled:
            return []
        with self._lock:
            date = self._date
        if date is None:
            return []
        return self._save(date)

    # ------------------------------------------------------------------
    def _save(self, date: datetime.date) -> List[str]:
        with self._lock:
            groups = self._groups
            self._groups = {}
            self._date = None
        if not groups:
            return []
        try:
            os.makedirs(self.dir, exist_ok=True)
        except OSError:
            with self._lock:                    # 写不了就放回去，别丢
                for key, lines in groups.items():
                    self._groups.setdefault(key, []).extend(lines)
                if self._date is None:
                    self._date = date
            return []
        day = date.strftime('%Y-%m-%d')
        index = self._next_index(day)
        paths: List[str] = []
        for (gid, gname), lines in groups.items():
            name = f'[{day}][{safe_name(gid, 20)}][{safe_name(gname)}][{index}].log'
            path = os.path.join(self.dir, name)
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines) + '\n')
                paths.append(path)
            except OSError:
                pass
        return paths

    def _next_index(self, day: str) -> int:
        """当天已存在的最大编号 + 1。"""
        prefix = f'[{day}]'
        pattern = re.compile(r'^\[' + re.escape(day) + r'\]\[[^\]]*\]\[[^\]]*\]\[(\d+)\]\.log$')
        highest = 0
        try:
            for name in os.listdir(self.dir):
                if not name.startswith(prefix):
                    continue
                m = pattern.match(name)
                if m:
                    highest = max(highest, int(m.group(1)))
        except OSError:
            pass
        return highest + 1
