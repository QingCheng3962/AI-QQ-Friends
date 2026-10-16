"""点歌: search a song (QQ 音乐 / 网易云) and turn it into an OneBot music card.

The native search endpoints are tried first; when both are unreachable the
module falls back to a public meting API which yields a **directly playable**
audio URL (a ``custom`` card). Nothing here needs an API key.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

import httpx

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

PLATFORMS = ('auto', 'qq', '163')
PLATFORM_LABELS = {'auto': '自动（QQ音乐 → 网易云）', 'qq': 'QQ 音乐', '163': '网易云音乐'}

_NETEASE_SEARCH = 'https://music.163.com/api/search/get/web'
_QQ_SEARCH = 'https://c.y.qq.com/soso/fcgi-bin/client_search_cp'
_METING = 'https://api.i-meto.com/meting/api'


@dataclass
class SongHit:
    """One search result, ready to be posted as a music card."""
    platform: str                 # 'qq' | '163' | 'custom'
    song_id: str = ''
    title: str = ''
    artist: str = ''
    audio_url: str = ''           # 仅 custom 卡片使用（可直接播放的音频）
    page_url: str = ''
    image_url: str = ''

    def label(self) -> str:
        return self.title + (f' - {self.artist}' if self.artist else '')

    def card(self) -> dict:
        """Keyword arguments for ``QqEngine.send_group_music``."""
        return {
            'platform': self.platform, 'songId': self.song_id, 'title': self.title,
            'artist': self.artist, 'audio': self.audio_url,
            'url': self.page_url, 'image': self.image_url,
        }


def _search_netease(keyword: str, client: httpx.Client) -> Optional[SongHit]:
    resp = client.get(_NETEASE_SEARCH,
                      params={'s': keyword, 'type': 1, 'offset': 0, 'limit': 1},
                      headers={'Referer': 'https://music.163.com/',
                               'Cookie': 'appver=2.0.2'})
    resp.raise_for_status()
    result = (resp.json() or {}).get('result') or {}
    songs = result.get('songs') or []
    if not songs:
        return None
    song = songs[0] or {}
    song_id = song.get('id')
    if song_id is None:
        return None
    artist = '/'.join(a.get('name', '') for a in (song.get('artists') or [])
                      if a.get('name'))
    return SongHit('163', song_id=str(song_id), title=song.get('name') or keyword,
                   artist=artist,
                   page_url=f'https://music.163.com/#/song?id={song_id}')


def _search_qq(keyword: str, client: httpx.Client) -> Optional[SongHit]:
    resp = client.get(_QQ_SEARCH,
                      params={'w': keyword, 'p': 1, 'n': 1, 'format': 'json',
                              'cr': 1, 'new_json': 1},
                      headers={'Referer': 'https://y.qq.com/'})
    resp.raise_for_status()
    data = (resp.json() or {}).get('data') or {}
    songs = (data.get('song') or {}).get('list') or []
    if not songs:
        return None
    song = songs[0] or {}
    mid = song.get('songmid') or song.get('mid')
    if not mid:
        return None
    artist = '/'.join(s.get('name', '') for s in (song.get('singer') or [])
                      if s.get('name'))
    return SongHit('qq', song_id=str(mid),
                   title=song.get('songname') or song.get('title') or keyword,
                   artist=artist,
                   page_url=f'https://y.qq.com/n/ryqq/songDetail/{mid}')


def _search_meting(keyword: str, client: httpx.Client) -> Optional[SongHit]:
    """Fallback: public meting API -> a directly playable audio URL."""
    resp = client.get(_METING,
                      params={'server': 'netease', 'type': 'search', 'id': keyword},
                      headers={'Referer': 'https://api.i-meto.com/'})
    resp.raise_for_status()
    items = resp.json() or []
    if not isinstance(items, list) or not items:
        return None
    item = items[0] or {}
    audio = item.get('url') or ''
    if not audio:
        return None
    return SongHit('custom', title=item.get('name') or keyword,
                   artist=item.get('artist') or '', audio_url=audio,
                   page_url=item.get('url') or '', image_url=item.get('pic') or '')


def search(keyword: str, platform: str = 'auto', timeout: float = 8.0,
           log: Optional[Callable[[str], None]] = None) -> Optional[SongHit]:
    """Find the first matching song. Returns None when nothing usable is found.

    ``platform`` is one of ``auto`` / ``qq`` / ``163``; ``auto`` tries QQ 音乐
    then 网易云 (matching the config docstring). A meting lookup is the last
    resort so that a request still succeeds when the official APIs refuse.
    """
    kw = (keyword or '').strip()
    if not kw:
        return None
    order: List[str] = {'auto': ['qq', '163'], 'qq': ['qq'], '163': ['163']}.get(
        platform, ['qq', '163'])
    problems: List[str] = []

    def note(msg: str) -> None:
        problems.append(msg)
        if log:
            log(msg)

    try:
        with httpx.Client(timeout=timeout, headers={'User-Agent': _UA},
                          follow_redirects=True) as client:
            for name in order:
                try:
                    hit = _search_qq(kw, client) if name == 'qq' else _search_netease(kw, client)
                except Exception as e:  # noqa: BLE001
                    note(f'{PLATFORM_LABELS.get(name, name)} 搜索失败: {e}')
                    continue
                if hit:
                    return hit
                note(f'{PLATFORM_LABELS.get(name, name)} 没有找到「{kw}」。')
            try:
                hit = _search_meting(kw, client)
            except Exception as e:  # noqa: BLE001
                note(f'备用音源搜索失败: {e}')
                hit = None
            if hit:
                return hit
    except Exception as e:  # noqa: BLE001
        note(f'点歌网络错误: {e}')
    return None
