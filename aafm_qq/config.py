"""Configuration models for AI QQ Friends.

Persisted to ``config.json`` next to the program (gitignored). Two parts:

- ``ai``   : the LLM / persona / reply-trigger settings (shared, like the AI
             player in the Minecraft project).
- ``qq``   : OneBot 11 endpoint, kept **per framework** (SnowLuma / NapCat) so
             each has its own launcher path, port and token.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
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

    # Output filter: the bot must never echo the trigger (prevents group members
    # from injecting prompts) and must not say rude words / leak "纯净输出".
    stripTrigger: bool = True
    blockedWords: List[str] = field(default_factory=lambda: list(DEFAULT_BLOCKED_WORDS))

    # Context / limits
    contextEnabled: bool = True
    contextLength: int = 20
    maxReplyMessages: int = 2
    maxCharsPerMessage: int = 120
    cooldownSeconds: int = 5

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
        self.maxReplyMessages = _clamp_int(self.maxReplyMessages, 1, 20)
        self.maxCharsPerMessage = _clamp_int(self.maxCharsPerMessage, 1, 2000)
        self.cooldownSeconds = _clamp_int(self.cooldownSeconds, 0, 3600)
        if self.blacklist is None:
            self.blacklist = []
        norm = []
        for b in self.blacklist:
            if isinstance(b, dict) and str(b.get('id') or '').strip():
                norm.append({'id': str(b['id']).strip(), 'name': str(b.get('name') or '')})
        self.blacklist = norm


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
        if isinstance(self.ai, dict):
            self.ai = AiConfig(**{k: v for k, v in self.ai.items()
                                  if k in AiConfig.__dataclass_fields__})
        if not isinstance(self.ai, AiConfig):
            self.ai = AiConfig()
        self.ai.validate()

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
                    for k, v in data.items():
                        if k == 'ai' and isinstance(v, dict):
                            for k2, v2 in v.items():
                                if hasattr(cfg.ai, k2):
                                    setattr(cfg.ai, k2, v2)
                        elif hasattr(cfg, k):
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
