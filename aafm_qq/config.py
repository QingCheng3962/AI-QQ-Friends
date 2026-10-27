"""Configuration models for AI QQ Friends.

Persisted to ``config.json`` next to the program (gitignored). Two parts:

- ``ai``      : the LLM / persona / reply-trigger settings (shared, like the AI
                player in the Minecraft project).
- ``qq``      : OneBot 11 endpoint, kept **per framework** (SnowLuma / NapCat) so
                each has its own launcher path, port and token.
- ``song``    : 点歌 (song request) — search a song and post a music card.
- ``affinity``: 好感度 (favour) — a per-member score that colours the persona.
- ``poke``    : 拍一拍 (poke) — poke back / poke close members (no LLM involved).
- ``requests``: 自动同意 — friend requests / group invites / join requests.
- ``misc``    : 杂项 — 视频推荐 (Bilibili video recommendations).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, asdict
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

DEFAULT_BASE_URLS = {
    'openai': 'https://api.openai.com/v1',
    'deepseek': 'https://api.deepseek.com/v1',
    'moonshot': 'https://api.moonshot.cn/v1',
    'anthropic': 'https://api.anthropic.com',
    'ollama': 'http://localhost:11434/v1',
}

DEFAULT_SYSTEM_PROMPT = (
    '你是 QQ 群里的一个普通群友（真人感），性格随和、爱聊天。行为准则：'
    '每次只发一两句群聊风格的短话，口语化、自然，不要长篇大论；'
    '像真人网友一样接话、玩梗、回应，不要总是一本正经；'
    '不要复述或翻译别人的话，不要暴露你是 AI，不要提及“模型/提示词/系统”；'
    '不要输出命令，不要输出触发词（例如 [AI]）；被 @ 或被问到就正常回答；'
    '保持友好，不骂人、不说脏话、不刷屏。'
)

# The trigger is a plain, user-editable STRING (not a hardcoded pattern).
# A message triggers only when it STARTS WITH it: "[AI]你好" triggers,
# "你好[AI]" does not. Comma-separated words are all accepted.
DEFAULT_TRIGGER_WORD = '[AI]'

# 「联网搜索」自动触发用的关键词（消息里含任意一个才去搜，省钱）。
DEFAULT_SEARCH_KEYWORDS = (
    '天气,气温,下雨,下雪,新闻,最新,今天,现在,刚刚,最近,股价,汇率,比分,赛果,'
    '票房,上映,票价,航班,高铁,官网,多少钱,几点,几号,日期,今年,去年,明年,'
    '2025,2026,实时,最新消息,发生了什么,怎么回事'
)

# 搜索来源（GUI 下拉框按这个顺序 + `_SEARCH_PROVIDER_KEYS` 对应）
SEARCH_PROVIDERS = {
    'duckduckgo': 'DuckDuckGo（免费，无需 Key）',
    'bing': 'Bing（免费，无需 Key）',
    'custom': '自定义 JSON 接口（Tavily / SearXNG…）',
}

# 什么时候搜
SEARCH_MODES = {
    'keywords': '只在关键词命中时搜（省钱）',
    'always': '每次回复都搜（最准、最慢）',
}

# Words/phrases that must never appear in the bot's outgoing message.
DEFAULT_BLOCKED_WORDS = [
    '纯净输出',
    '傻逼', '沙比', '煞笔', '尼玛', '你妈', '妈的', '他妈', '操你', '草你',
    '草泥马', '卧槽', '滚蛋', '去死', '废物', '贱', '滚出',
    'fuck', 'shit', 'bitch', 'asshole', 'dick',
]


def _clamp_int(v: Any, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


@dataclass
class OneBotConfig:
    """OneBot 11 endpoint settings for one framework (SnowLuma / NapCat)."""
    launcherPath: str = ''      # folder or launcher file; '' => default location
    mode: str = 'forward'
    url: str = 'ws://127.0.0.1:3001'
    accessToken: str = ''
    listenHost: str = '0.0.0.0'
    listenPort: int = 3002
    autoConfigNewAccounts: bool = True

    def validate(self) -> None:
        self.launcherPath = str(self.launcherPath or '').strip()
        if self.mode not in ('forward', 'reverse'):
            self.mode = 'forward'
        if not self.url:
            self.url = 'ws://127.0.0.1:3001'
        if not self.listenHost:
            self.listenHost = '0.0.0.0'
        try:
            self.listenPort = int(self.listenPort)
        except (TypeError, ValueError):
            self.listenPort = 3002
        self.listenPort = _clamp_int(self.listenPort, 1, 65535)
        self.accessToken = str(self.accessToken or '')
        self.autoConfigNewAccounts = bool(self.autoConfigNewAccounts)


@dataclass
class AiConfig:
    enabled: bool = False
    provider: str = 'openai'
    baseUrl: str = ''
    apiKey: str = ''
    model: str = 'gpt-4o-mini'
    temperature: float = 0.8
    maxTokens: int = 512
    timeoutSeconds: int = 30
    retryCount: int = 1

    systemPrompt: str = DEFAULT_SYSTEM_PROMPT

    # Reply rules
    mentionReply: bool = False                # reply when the bot is @-mentioned
    triggerEnabled: bool = True
    triggerWord: str = DEFAULT_TRIGGER_WORD    # user string; message must START with it
    triggerRegex: str = ''                     # optional extra regex (advanced, may be empty)
    autoReply: bool = False                   # reply to every group message
    autoReplyChance: int = 100                # 0-100 (used with autoReply)
    atReply: bool = True                      # prefix the reply with @sender
    quoteReply: bool = True                   # 引用触发它的那条消息（[CQ:reply]）
    # 私聊（好友/临时会话的「聊天页面」）：默认也自动回复，且不用触发词。
    privateReplyEnabled: bool = True
    privateAlwaysReply: bool = True

    # Output filter: the bot must never echo the trigger (prevents group members
    # from injecting prompts) and must not say rude words / leak "纯净输出".
    stripTrigger: bool = True
    blockedWords: List[str] = field(default_factory=lambda: list(DEFAULT_BLOCKED_WORDS))

    # Context / limits
    contextEnabled: bool = True
    contextLength: int = 40                   # 最多保留多少条（硬上限）
    contextTokenBudget: int = 1200            # 送进模型的 token 预算（0=只按条数）
    maxReplyMessages: int = 2
    maxCharsPerMessage: int = 120
    cooldownSeconds: int = 5

    # 联网搜索（免费源 / 自定义源）。只有真要回复时才搜，且默认只在关键词命中时搜。
    searchEnabled: bool = False
    searchProvider: str = 'duckduckgo'
    searchMode: str = 'keywords'              # keywords / always
    searchKeywords: str = DEFAULT_SEARCH_KEYWORDS
    searchMaxResults: int = 5
    searchApiUrl: str = ''                    # custom：GET 模板带 {query}，否则 POST JSON
    searchApiKey: str = ''
    searchTimeoutSeconds: int = 12

    # Blacklist: [{"id": "123456", "name": "昵称"}] (by QQ id)
    blacklist: List[Dict[str, str]] = field(default_factory=list)

    def validate(self) -> None:
        if self.provider not in DEFAULT_BASE_URLS:
            self.provider = 'openai'
        self.baseUrl = str(self.baseUrl or '').strip()
        self.apiKey = str(self.apiKey or '')
        self.model = str(self.model or 'gpt-4o-mini')
        try:
            self.temperature = max(0.0, min(2.0, float(self.temperature)))
        except (TypeError, ValueError):
            self.temperature = 0.8
        self.maxTokens = _clamp_int(self.maxTokens, 16, 8192)
        self.timeoutSeconds = _clamp_int(self.timeoutSeconds, 5, 600)
        self.retryCount = _clamp_int(self.retryCount, 0, 5)
        self.systemPrompt = str(self.systemPrompt or '').strip() or DEFAULT_SYSTEM_PROMPT
        self.triggerWord = str(self.triggerWord or '').strip()
        self.triggerRegex = str(self.triggerRegex or '').strip()
        self.mentionReply = bool(self.mentionReply)
        self.triggerEnabled = bool(self.triggerEnabled)
        self.autoReply = bool(self.autoReply)
        self.atReply = bool(self.atReply)
        self.quoteReply = bool(self.quoteReply)
        self.privateReplyEnabled = bool(self.privateReplyEnabled)
        self.privateAlwaysReply = bool(self.privateAlwaysReply)
        self.stripTrigger = bool(self.stripTrigger)
        if self.blockedWords is None:
            self.blockedWords = list(DEFAULT_BLOCKED_WORDS)
        norm_bw = []
        for w in self.blockedWords or []:
            s = str(w).strip()
            if s and s not in norm_bw:
                norm_bw.append(s)
        self.blockedWords = norm_bw
        self.autoReplyChance = _clamp_int(self.autoReplyChance, 0, 100)
        self.contextLength = _clamp_int(self.contextLength, 0, 200)
        self.contextTokenBudget = _clamp_int(self.contextTokenBudget, 0, 32000)
        self.maxReplyMessages = _clamp_int(self.maxReplyMessages, 1, 20)
        self.maxCharsPerMessage = _clamp_int(self.maxCharsPerMessage, 1, 2000)
        self.cooldownSeconds = _clamp_int(self.cooldownSeconds, 0, 3600)
        self.searchEnabled = bool(self.searchEnabled)
        if self.searchProvider not in SEARCH_PROVIDERS:
            self.searchProvider = 'duckduckgo'
        if self.searchMode not in SEARCH_MODES:
            self.searchMode = 'keywords'
        self.searchKeywords = (str(self.searchKeywords or '').strip()
                               or DEFAULT_SEARCH_KEYWORDS)
        self.searchMaxResults = _clamp_int(self.searchMaxResults, 1, 10)
        self.searchApiUrl = str(self.searchApiUrl or '').strip()
        self.searchApiKey = str(self.searchApiKey or '').strip()
        self.searchTimeoutSeconds = _clamp_int(self.searchTimeoutSeconds, 3, 60)
        if self.blacklist is None:
            self.blacklist = []
        norm = []
        for b in self.blacklist:
            if isinstance(b, dict):
                bid = str(b.get('id') or '').strip()
                name = str(b.get('name') or '')
            else:  # tolerate a hand-edited list of plain QQ numbers
                bid, name = str(b or '').strip(), ''
            if bid and not any(x['id'] == bid for x in norm):
                norm.append({'id': bid, 'name': name})
        self.blacklist = norm


@dataclass
class SongConfig:
    """点歌: a group message starting with ``trigger`` (default ``[点歌]``) makes
    the bot search a song and post a music card. ``platform`` is one of
    ``auto`` (try QQ then NetEase), ``qq`` (QQ 音乐) or ``163`` (网易云).

    Matched messages are consumed here and never reach the chat AI, so a song
    request is not "answered" by the large model as well.
    """
    enabled: bool = True
    trigger: str = '[点歌]'
    platform: str = 'auto'
    cooldownSeconds: int = 4            # 同一群两次点歌的最小间隔
    timeoutSeconds: int = 8             # 搜索接口超时
    # 网易云会员登录 Cookie（含 MUSIC_U）。在「互动」页扫码 / 粘贴后自动写入，
    # 用于替群友解析 VIP 歌的可播放直链（搜索本身匿名，不带它会返回空结果）。
    neteaseCookie: str = ''

    def validate(self) -> None:
        self.enabled = bool(self.enabled)
        self.trigger = str(self.trigger or '').strip() or '[点歌]'
        if self.platform not in ('auto', 'qq', '163'):
            self.platform = 'auto'
        self.cooldownSeconds = _clamp_int(self.cooldownSeconds, 0, 3600)
        self.timeoutSeconds = _clamp_int(self.timeoutSeconds, 2, 60)
        self.neteaseCookie = str(self.neteaseCookie or '').strip()


@dataclass
class AffinityConfig:
    """好感度: a per-(group, member) score 0-100 that grows as the member chats
    with the bot, is written into the persona prompt (so the bot gets warmer to
    people it "knows") and can be queried in-group with ``queryTrigger``."""
    enabled: bool = True
    start: int = 20            # 新成员的初始好感度
    maximum: int = 100         # 上限
    gainPerChat: int = 2       # 每次被搭话 +N
    dailyCap: int = 20         # 每人每天最多 +N（0=不限制）
    queryTrigger: str = '[好感度]'
    promptHint: bool = True    # 把好感度写进人设提示词，影响语气
    persist: bool = True       # 落盘到 affinity.json
    # 每日签到：[签到] 每天一次，额外加好感度（不受「每人每天上限」限制）。
    checkinEnabled: bool = True
    checkinTrigger: str = '[签到]'
    checkinGain: int = 5       # 每次签到加多少好感度

    def validate(self) -> None:
        self.enabled = bool(self.enabled)
        self.maximum = _clamp_int(self.maximum, 1, 1000)
        self.start = _clamp_int(self.start, 0, self.maximum)
        self.gainPerChat = _clamp_int(self.gainPerChat, 0, 100)
        self.dailyCap = _clamp_int(self.dailyCap, 0, 100000)
        self.queryTrigger = str(self.queryTrigger or '').strip() or '[好感度]'
        self.promptHint = bool(self.promptHint)
        self.persist = bool(self.persist)
        self.checkinEnabled = bool(self.checkinEnabled)
        self.checkinTrigger = str(self.checkinTrigger or '').strip() or '[签到]'
        self.checkinGain = _clamp_int(self.checkinGain, 0, 100)


@dataclass
class PokeConfig:
    """拍一拍：调 OneBot 的 ``send_poke``（**绝不让 LLM 决定**）。

    两条路径，都带冷却与概率：

    - **被拍回拍**：有人拍了拍机器人 → 拍回去（``pokeBack``）。
    - **主动拍**：好感度 ≥ ``affinityThreshold`` 的群友说话时，小概率拍一下
      （``proactive``）。人越熟越容易触发，但不会刷屏。

    QQ 对拍一拍有风控，冷却默认给到 120 秒，别调太小。
    """
    enabled: bool = True
    pokeBack: bool = True               # 被拍了就拍回去
    pokeBackChance: int = 100           # 回拍概率 %
    proactive: bool = True              # 好感度高的群友说话时主动拍
    affinityThreshold: int = 60         # 好感度 >= 这个值才会被主动拍
    proactiveChance: int = 15           # 每次他说话时主动拍的概率 %
    cooldownSeconds: int = 120          # 同一群两次拍的最小间隔（风控）

    def validate(self) -> None:
        self.enabled = bool(self.enabled)
        self.pokeBack = bool(self.pokeBack)
        self.pokeBackChance = _clamp_int(self.pokeBackChance, 0, 100)
        self.proactive = bool(self.proactive)
        self.affinityThreshold = _clamp_int(self.affinityThreshold, 0, 1000)
        self.proactiveChance = _clamp_int(self.proactiveChance, 0, 100)
        self.cooldownSeconds = _clamp_int(self.cooldownSeconds, 0, 3600)


@dataclass
class RequestConfig:
    """自动同意：好友申请 / 被邀请入群 / 申请加群。

    走 OneBot 11 的 ``set_friend_add_request`` / ``set_group_add_request``。
    默认全开；不想自动处理某类就关掉对应开关（关掉后只记日志、留给你手动同意）。
    """
    enabled: bool = True            # 总开关
    friend: bool = True             # 自动同意好友申请
    groupInvite: bool = True        # 自动同意「邀请机器人入群」
    groupJoin: bool = True          # 自动同意「申请加入机器人所在的群」
    # 「邀请入群」也遵守「群白名单 / 忽略群」：白名单非空时，不在名单里的群不自动进
    respectGroupFilter: bool = True

    def validate(self) -> None:
        self.enabled = bool(self.enabled)
        self.friend = bool(self.friend)
        self.groupInvite = bool(self.groupInvite)
        self.groupJoin = bool(self.groupJoin)
        self.respectGroupFilter = bool(self.respectGroupFilter)


# Titles shown when a member checks their 好感度 (high → low).
AFFINITY_TITLES = [
    (95, '心动'),
    (80, '挚友'),
    (60, '好朋友'),
    (40, '朋友'),
    (20, '眼熟'),
    (0, '陌生'),
]


def affinity_title(score: int) -> str:
    for floor, name in AFFINITY_TITLES:
        if score >= floor:
            return name
    return AFFINITY_TITLES[-1][1]


# 视频推荐来源（GUI「杂项」页的下拉框按这个顺序 + `_VIDEO_SOURCE_KEYS` 对应）
VIDEO_SOURCES = {
    'anime': '番剧追番榜',        # pgc/web/rank/list?season_type=1
    'home': 'B 站首页推荐',       # x/web-interface/index/top/rcmd（首页那排，需先拿 buvid3）
    'hot': 'B 站首页热门',        # x/web-interface/popular
    'rank': 'B 站全站排行',       # x/web-interface/ranking/v2
    'fav': '我的收藏夹（登录）',   # x/v3/fav/resource/list（需 SESSDATA）
}


@dataclass
class MiscConfig:
    """杂项：视频推荐。

    群友发「触发词 + 视频推荐」（默认 ``[视频推荐]``）即在群里推一批 B 站视频；
    冷却**全服共用**（谁的请求都算），冷却过后再点会**重新抓一批新的**
    （按来源各自记住最近推过的 id，越点越多、不重复）。
    """
    videoEnabled: bool = True
    videoTrigger: str = '[视频推荐]'
    # anime=番剧追番榜（默认）/ home=B 站首页推荐 / hot=B 站首页热门 /
    # rank=B 站全站排行 / fav=我的收藏夹（要 Cookie）
    videoSource: str = 'anime'
    videoCount: int = 5                 # 一次推几条
    videoCooldownSeconds: int = 30      # 全服共用冷却（秒）
    # 抬头文案：{player} 谁点的、{count} 条数、{source} 来源名
    videoTitle: str = '【视频推荐】{player} 点的{source}前 {count} 条：'
    # 每条文案：{index} 序号、{title} 标题、{owner} 备注（UP主/更新进度）、{link} 链接
    videoItemText: str = '{index}. {title} {owner} {link}'
    videoCoolText: str = '【视频推荐】刚推过啦，{wait} 秒后再来（会换一批新的）'
    videoFailText: str = '【视频推荐】B 站接口暂时抽风了，稍等一下再试~'
    # 来源选「我的收藏夹」时才需要：B 站登录 Cookie（整条或只填 SESSDATA 值都行）
    biliCookie: str = ''
    biliFavMediaId: int = 0             # 收藏夹 id（GUI 可点「读取收藏夹」自动填）
    biliFavName: str = ''               # 收藏夹名字（显示用）

    def validate(self) -> None:
        self.videoEnabled = bool(self.videoEnabled)
        self.videoTrigger = str(self.videoTrigger or '').strip() or '[视频推荐]'
        src = str(self.videoSource or 'anime').strip().lower()
        self.videoSource = src if src in VIDEO_SOURCES else 'anime'
        self.videoCount = _clamp_int(self.videoCount, 1, 10)
        self.videoCooldownSeconds = _clamp_int(self.videoCooldownSeconds, 0, 3600)
        self.videoTitle = (str(self.videoTitle or '').strip()
                           or '【视频推荐】{player} 点的{source}前 {count} 条：')
        self.videoItemText = (str(self.videoItemText or '').strip()
                              or '{index}. {title} {owner} {link}')
        self.videoCoolText = (str(self.videoCoolText or '').strip()
                              or '【视频推荐】刚推过啦，{wait} 秒后再来（会换一批新的）')
        self.videoFailText = (str(self.videoFailText or '').strip()
                              or '【视频推荐】B 站接口暂时抽风了，稍等一下再试~')
        self.biliCookie = str(self.biliCookie or '').strip()
        self.biliFavMediaId = _clamp_int(self.biliFavMediaId, 0, 999_999_999)
        self.biliFavName = str(self.biliFavName or '').strip()

    def source_name(self) -> str:
        """来源的中文名（给文案里的 {source} 用）。"""
        if (self.videoSource or '') == 'fav' and (self.biliFavName or '').strip():
            return '收藏夹「%s」' % str(self.biliFavName).strip()[:20]
        return VIDEO_SOURCES.get(self.videoSource or 'anime', VIDEO_SOURCES['anime'])


# Sub-dataclasses nested inside AppConfig (JSON object -> validated instance).
_NESTED_CONFIGS = {
    'ai': AiConfig,
    'song': SongConfig,
    'affinity': AffinityConfig,
    'poke': PokeConfig,
    'requests': RequestConfig,
    'misc': MiscConfig,
}


@dataclass
class AppConfig:
    framework: str = 'snowluma'   # 'snowluma' | 'napcat'
    snowluma: OneBotConfig = field(default_factory=OneBotConfig)
    napcat: OneBotConfig = field(default_factory=OneBotConfig)
    # Group whitelist (empty = every group) and ignore list.
    groups: List[str] = field(default_factory=list)
    ignoreGroups: List[str] = field(default_factory=list)
    autoReconnect: bool = True
    healthCheckSeconds: int = 30
    lastLoginUin: str = ''
    ai: AiConfig = field(default_factory=AiConfig)
    song: SongConfig = field(default_factory=SongConfig)
    affinity: AffinityConfig = field(default_factory=AffinityConfig)
    poke: PokeConfig = field(default_factory=PokeConfig)
    requests: RequestConfig = field(default_factory=RequestConfig)
    misc: MiscConfig = field(default_factory=MiscConfig)

    def active(self) -> OneBotConfig:
        return self.napcat if self.framework == 'napcat' else self.snowluma

    def validate(self) -> None:
        if self.framework not in ('snowluma', 'napcat'):
            self.framework = 'snowluma'
        for name in ('snowluma', 'napcat'):
            sub = getattr(self, name)
            if isinstance(sub, dict):
                sub = OneBotConfig(**{k: v for k, v in sub.items()
                                      if k in OneBotConfig.__dataclass_fields__})
                setattr(self, name, sub)
            if not isinstance(sub, OneBotConfig):
                setattr(self, name, OneBotConfig())
            getattr(self, name).validate()
        for attr in ('groups', 'ignoreGroups'):
            vals = getattr(self, attr) or []
            norm = []
            for g in vals:
                s = str(g).strip()
                if s and s not in norm:
                    norm.append(s)
            setattr(self, attr, norm)
        self.autoReconnect = bool(self.autoReconnect)
        self.healthCheckSeconds = _clamp_int(self.healthCheckSeconds, 0, 3600)
        self.lastLoginUin = str(self.lastLoginUin or '').strip()
        for name, cls in _NESTED_CONFIGS.items():
            self._coerce(name, cls)

    def _coerce(self, name: str, cls) -> None:
        """Make ``self.<name>`` a validated instance of ``cls`` (from dict/None)."""
        val = getattr(self, name, None)
        if isinstance(val, dict):
            val = cls(**{k: v for k, v in val.items()
                         if k in cls.__dataclass_fields__})
        if not isinstance(val, cls):
            val = cls()
        val.validate()
        setattr(self, name, val)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def load(cls, path: Optional[str] = None) -> 'AppConfig':
        path = path or APP_CONFIG_FILE
        cfg = cls()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    top_fields = {f.name for f in fields(cls)}
                    for k, v in data.items():
                        if k in _NESTED_CONFIGS and isinstance(v, dict):
                            obj = getattr(cfg, k)
                            sub_fields = {f.name for f in fields(type(obj))}
                            for k2, v2 in v.items():
                                if k2 in sub_fields:
                                    setattr(obj, k2, v2)
                        elif k in top_fields:  # only real config fields, never methods
                            setattr(cfg, k, v)
            except Exception as e:  # noqa: BLE001
                print(f'[aiqq] Failed to read {path}, using defaults: {e}')
        cfg.validate()
        return cfg

    def save(self, path: Optional[str] = None) -> None:
        path = path or APP_CONFIG_FILE
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001
            print(f'[aiqq] Failed to save {path}: {e}')
