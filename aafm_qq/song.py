"""点歌: 搜索歌曲（QQ 音乐 / 网易云）并转成 OneBot 音乐卡片。

- QQ 音乐：直接发 ``qq`` 卡片（用歌曲 mid）。
- 网易云：登录会员 Cookie 后优先解析**可播放直链**，发 ``custom`` 卡片
  （VIP 歌也能完整播放）；没登录 / 取不到直链时回退到 ``163`` 卡片。
搜索本身匿名，不需要任何 API key。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

import httpx

from . import netease

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

PLATFORMS = ('auto', 'qq', '163')
PLATFORM_LABELS = {'auto': '自动（QQ音乐 → 网易云）', 'qq': 'QQ 音乐', '163': '网易云音乐'}

_QQ_SEARCH = 'https://c.y.qq.com/soso/fcgi-bin/client_search_cp'


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


def _netease_hit(keyword: str, cookie: str,
                 log: Optional[Callable[[str], None]] = None) -> Optional[SongHit]:
    """网易云：匿名搜索 → 有会员 Cookie 时解析可播放直链。

    取到直链就发 ``custom`` 卡片（VIP 也能完整播放）；否则回退 ``163`` 卡片。
    """
    try:
        info = netease.resolve(keyword, cookie)
    except netease.SearchUnavailable as e:
        if log:
            log(f'网易云接口不可用: {e}')
        return None
    if not info:
        return None
    artist = '/'.join(info.get('artists') or [])
    page = f'https://music.163.com/#/song?id={info["id"]}'
    if info.get('url'):
        return SongHit('custom', title=info['title'], artist=artist,
                       audio_url=info['url'], page_url=page)
    if info.get('note') and log:
        log(info['note'])
    return SongHit('163', song_id=info['id'], title=info['title'],
                   artist=artist, page_url=page)


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


def search(keyword: str, platform: str = 'auto', timeout: float = 8.0,
           log: Optional[Callable[[str], None]] = None,
           cookie: str = '') -> Optional[SongHit]:
    """Find the first matching song. Returns None when nothing usable is found.

    ``platform`` is one of ``auto`` / ``qq`` / ``163``; ``auto`` tries QQ 音乐
    then 网易云. ``cookie`` is the NetEase member cookie used to resolve a
    directly playable URL for 网易云 songs (VIP included).
    """
    kw = (keyword or '').strip()
    if not kw:
        return None
    order: List[str] = {'auto': ['qq', '163'], 'qq': ['qq'], '163': ['163']}.get(
        platform, ['qq', '163'])

    def note(msg: str) -> None:
        if log:
            log(msg)

    try:
        with httpx.Client(timeout=timeout, headers={'User-Agent': _UA},
                          follow_redirects=True) as client:
            for name in order:
                try:
                    if name == 'qq':
                        hit = _search_qq(kw, client)
                    else:
                        hit = _netease_hit(kw, cookie, note)
                except Exception as e:  # noqa: BLE001
                    note(f'{PLATFORM_LABELS.get(name, name)} 搜索失败: {e}')
                    continue
                if hit:
                    return hit
                note(f'{PLATFORM_LABELS.get(name, name)} 没有找到「{kw}」。')
    except Exception as e:  # noqa: BLE001
        note(f'点歌网络错误: {e}')
    return None
