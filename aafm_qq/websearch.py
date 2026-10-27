"""联网搜索：给聊天 AI 补一条「刚发生的事」。

三个来源（``provider``）：

- ``duckduckgo`` —— 免费 HTML 抓取，**不需要 Key**（默认）。
- ``bing``       —— 免费 HTML 抓取，**不需要 Key**（DuckDuckGo 抽风时的备选）。
- ``custom``     —— 自定义 JSON 接口：Tavily / Serper / SearXNG 之类都行。

自定义接口的两种用法：

- ``searchApiUrl`` 里带 ``{query}`` → 走 **GET**，把 ``{query}`` 替换成搜索词
  （SearXNG：``http://127.0.0.1:8080/search?q={query}&format=json``）。
- 不带 ``{query}`` → 走 **POST JSON**（``{"query": ...}``，Tavily / Serper 风格），
  可选 ``Authorization: Bearer <key>``。

返回统一为 ``[{'title', 'url', 'snippet'}]``；``search_ex`` 还会带上失败原因，
方便在日志里说清楚是「没搜到」还是「接口挂了」。
"""
from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any, Dict, List, Tuple

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')

_TAG_RE = re.compile(r'<[^>]+>')


def _clean(s: str) -> str:
    return html.unescape(_TAG_RE.sub('', str(s or ''))).strip()


def _ddg_url(href: str) -> str:
    href = html.unescape(str(href or ''))
    if href.startswith('//'):
        href = 'https:' + href
    # DuckDuckGo 会把链接包成 /l/?uddg=<encoded>
    try:
        q = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(q.query)
        if 'uddg' in params and params['uddg']:
            return params['uddg'][0]
    except Exception:  # noqa: BLE001
        pass
    return href


# ----------------------------------------------------------------------
# 免费来源
# ----------------------------------------------------------------------
def search_duckduckgo(query: str, max_results: int = 5,
                      timeout: float = 12.0) -> List[Dict[str, str]]:
    try:
        import httpx
        r = httpx.get('https://html.duckduckgo.com/html/',
                      params={'q': query}, headers={'User-Agent': _UA},
                      timeout=timeout, follow_redirects=True)
    except Exception:  # noqa: BLE001
        return []
    if r.status_code != 200:
        return []
    text = r.text
    titles = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.S)
    out: List[Dict[str, str]] = []
    for i, (href, title) in enumerate(titles[:max_results]):
        t = _clean(title)
        if not t:
            continue
        out.append({
            'title': t,
            'url': _ddg_url(href),
            'snippet': _clean(snippets[i]) if i < len(snippets) else '',
        })
    return out


def search_bing(query: str, max_results: int = 5,
                timeout: float = 12.0) -> List[Dict[str, str]]:
    try:
        import httpx
        r = httpx.get('https://www.bing.com/search',
                      params={'q': query, 'setlang': 'zh-CN'},
                      headers={'User-Agent': _UA,
                               'Accept-Language': 'zh-CN,zh;q=0.9'},
                      timeout=timeout, follow_redirects=True)
    except Exception:  # noqa: BLE001
        return []
    if r.status_code != 200:
        return []
    text = r.text
    out: List[Dict[str, str]] = []
    for block in re.findall(r'<li class="b_algo".*?</li>', text, re.S):
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        t = _clean(m.group(2))
        if not t:
            continue
        p = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        out.append({
            'title': t,
            'url': html.unescape(m.group(1)),
            'snippet': _clean(p.group(1)) if p else '',
        })
        if len(out) >= max_results:
            break
    return out


# ----------------------------------------------------------------------
# 自定义 JSON 接口
# ----------------------------------------------------------------------
def search_custom(query: str, api_url: str, api_key: str = '',
                  max_results: int = 5, timeout: float = 12.0,
                  ) -> Tuple[List[Dict[str, str]], str]:
    url = (api_url or '').strip()
    if not url:
        return [], '没填搜索接口地址'
    try:
        import httpx
    except Exception as e:  # noqa: BLE001
        return [], '缺少 httpx: ' + str(e)
    headers = {'Accept': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    try:
        if '{query}' in url:
            # GET 模板（SearXNG / 自建接口）
            target = url.replace('{query}', urllib.parse.quote(query, safe=''))
            r = httpx.get(target, headers=headers, timeout=timeout,
                          follow_redirects=True)
        else:
            headers['Content-Type'] = 'application/json'
            r = httpx.post(url, json={'query': query, 'q': query,
                                      'max_results': max_results},
                           headers=headers, timeout=timeout, follow_redirects=True)
        if r.status_code >= 400:
            return [], f'HTTP {r.status_code}: {r.text[:120]}'
        data = r.json()
    except Exception as e:  # noqa: BLE001
        return [], f'{type(e).__name__}: {e}'
    if not isinstance(data, dict):
        return [], '接口返回的不是 JSON 对象'
    items: Any = (data.get('results') or data.get('organic')
                  or data.get('data') or data.get('items') or [])
    if isinstance(items, dict):
        items = items.get('results') or []
    if not isinstance(items, list):
        return [], '接口返回里没有 results 列表'
    out: List[Dict[str, str]] = []
    for it in items[:max_results]:
        if not isinstance(it, dict):
            continue
        title = str(it.get('title') or it.get('name') or '').strip()
        link = str(it.get('url') or it.get('link') or it.get('href') or '').strip()
        if not title and not link:
            continue
        out.append({
            'title': title,
            'url': link,
            'snippet': _clean(it.get('content') or it.get('snippet')
                              or it.get('description') or it.get('text') or ''),
        })
    return out, ('' if out else '接口返回 0 条结果')


# ----------------------------------------------------------------------
# 统一入口
# ----------------------------------------------------------------------
def search_ex(query: str, cfg) -> Tuple[List[Dict[str, str]], str]:
    """按配置搜索，返回 ``(结果, 失败原因)``。

    ``duckduckgo`` 没结果时会自动再试一次 ``bing``（两个都是免费源）。
    """
    query = (query or '').strip()
    if not query:
        return [], '搜索词为空'
    provider = (getattr(cfg, 'searchProvider', 'duckduckgo') or 'duckduckgo').lower()
    n = max(1, int(getattr(cfg, 'searchMaxResults', 5) or 5))
    timeout = max(3.0, float(getattr(cfg, 'searchTimeoutSeconds', 12) or 12))
    if provider == 'custom':
        return search_custom(query, getattr(cfg, 'searchApiUrl', ''),
                             getattr(cfg, 'searchApiKey', ''), n, timeout)
    if provider == 'bing':
        items = search_bing(query, n, timeout)
        return items, ('' if items else 'Bing 没返回结果（可能被限流）')
    items = search_duckduckgo(query, n, timeout)
    if not items:
        items = search_bing(query, n, timeout)      # 免费兜底
        if items:
            return items, ''
        return [], 'DuckDuckGo / Bing 都没返回结果（可能被限流，或被墙）'
    return items, ''


def search(query: str, cfg) -> List[Dict[str, str]]:
    return search_ex(query, cfg)[0]


def format_results(results: List[Dict[str, str]], max_snippet: int = 160) -> str:
    """整理成给大模型看的一段文本（标题 —— 摘要（链接））。"""
    lines = []
    for i, r in enumerate(results, 1):
        title = str(r.get('title') or '').strip()
        snippet = str(r.get('snippet') or '').strip()
        if len(snippet) > max_snippet:
            snippet = snippet[:max_snippet].rstrip() + '…'
        url = str(r.get('url') or '').strip()
        line = f'{i}. {title}'
        if snippet:
            line += f' — {snippet}'
        if url:
            line += f' ({url})'
        lines.append(line)
    return '\n'.join(lines)
