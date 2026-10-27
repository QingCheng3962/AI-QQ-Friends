"""tkinter GUI for AI QQ Friends: 连接 / AI 配置 / 日志."""
from __future__ import annotations

import threading
import time
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

from .config import AppConfig, DEFAULT_BASE_URLS
from .controller import Controller

_PROVIDERS = ['openai', 'deepseek', 'moonshot', 'anthropic', 'ollama']


class ScrollFrame(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        vsb = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>', lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(
            self._win, width=e.width))
        self.canvas.bind('<Enter>', lambda e: self.canvas.bind_all('<MouseWheel>', self._wheel))
        self.canvas.bind('<Leave>', lambda e: self.canvas.unbind_all('<MouseWheel>'))

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')


class App:
    # 视频推荐来源：顺序必须和 config.VIDEO_SOURCES 一致
    _VIDEO_SOURCE_LABELS = ['番剧追番榜（追番）', 'B 站首页推荐（主页）', 'B 站首页热门',
                            'B 站全站排行', '我的收藏夹（要登录 B 站）']
    _VIDEO_SOURCE_KEYS = ['anime', 'home', 'hot', 'rank', 'fav']
    # 联网搜索来源 / 时机：顺序必须和 config.SEARCH_PROVIDERS / SEARCH_MODES 一致
    _SEARCH_PROVIDER_LABELS = ['DuckDuckGo（免费，无需 Key）', 'Bing（免费，无需 Key）',
                               '自定义 JSON 接口（Tavily / SearXNG…）']
    _SEARCH_PROVIDER_KEYS = ['duckduckgo', 'bing', 'custom']
    _SEARCH_MODE_LABELS = ['只在关键词命中时搜（省钱）', '每次回复都搜（最准、最慢）']
    _SEARCH_MODE_KEYS = ['keywords', 'always']

    def __init__(self, root: tk.Tk):
        self.root = root
        self.controller = Controller()
        root.title('AI QQ Friends - QQ 群友')
        root.geometry('900x680')
        root.minsize(780, 560)

        self._build_toolbar()
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self._build_connect_tab()
        self._build_ai_tab()
        self._build_interact_tab()
        self._build_misc_tab()
        self._build_log_tab()
        self._load_config()
        root.protocol('WM_DELETE_WINDOW', self._on_close)
        root.after(100, self._poll)

    # ------------------------------------------------------------------
    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(side='top', fill='x')
        self.status = ttk.Label(bar, text='未连接', font=('Segoe UI', 10, 'bold'),
                                foreground='#999999')
        self.status.pack(side='left')
        ttk.Button(bar, text='连接', command=self._on_connect).pack(side='left', padx=(14, 4))
        ttk.Button(bar, text='断开', command=self._on_disconnect).pack(side='left', padx=4)
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=10)
        self.ai_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='AI 群友开关', variable=self.ai_on,
                        command=self._on_ai_toggle).pack(side='left', padx=4)
        ttk.Button(bar, text='重开上下文', command=self._on_clear_ctx).pack(side='left', padx=4)
        ttk.Button(bar, text='保存设置', command=self._on_save).pack(side='left', padx=4)

    def _build_connect_tab(self):
        host = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(host, text=' 连接 ')
        sc = ScrollFrame(host)
        sc.pack(fill='both', expand=True)
        frm = ttk.LabelFrame(sc.inner, text='OneBot 11 网关（SnowLuma / NapCat）', padding=8)
        frm.pack(fill='x', pady=(6, 0))

        self.var_fw = tk.StringVar(value='SnowLuma')
        self.var_launcher = tk.StringVar()
        self.var_mode = tk.StringVar(value='forward')
        self.var_url = tk.StringVar()
        self.var_token = tk.StringVar()
        self.var_lhost = tk.StringVar()
        self.var_lport = tk.StringVar()
        self.var_groups = tk.StringVar()
        self.var_ignore = tk.StringVar()
        self.var_autoreconnect = tk.BooleanVar(value=True)
        self.var_health = tk.StringVar()

        r = ttk.Frame(frm)
        r.grid(row=0, column=0, columnspan=4, sticky='we', pady=2)
        ttk.Label(r, text='启动框架').pack(side='left')
        fwbox = ttk.Combobox(r, textvariable=self.var_fw, state='readonly',
                             values=['SnowLuma', 'NapCat'], width=10)
        fwbox.pack(side='left', padx=(4, 12))
        fwbox.bind('<<ComboboxSelected>>', lambda e: self._on_fw_changed())
        ttk.Label(r, text='启动路径').pack(side='left')
        ttk.Entry(r, textvariable=self.var_launcher).pack(side='left', fill='x', expand=True, padx=(4, 0))

        self._row(frm, 1, '连接模式', self.var_mode, hint='forward=连接网关 / reverse=监听网关连入')
        self._row(frm, 2, '正向地址', self.var_url, width=44)
        self._row(frm, 3, 'Access Token', self.var_token, width=44)
        r = ttk.Frame(frm)
        r.grid(row=4, column=0, columnspan=4, sticky='we', pady=2)
        ttk.Label(r, text='反向监听').pack(side='left')
        ttk.Entry(r, textvariable=self.var_lhost, width=16).pack(side='left', padx=(4, 4))
        ttk.Entry(r, textvariable=self.var_lport, width=8).pack(side='left')

        self._row(frm, 5, '群白名单', self.var_groups, width=44,
                  hint='多个用逗号/空格分隔；留空=全部群')
        self._row(frm, 6, '忽略群', self.var_ignore, width=44, hint='这些群不处理')
        r = ttk.Frame(frm)
        r.grid(row=7, column=0, columnspan=4, sticky='w', pady=2)
        ttk.Checkbutton(r, text='自动重连', variable=self.var_autoreconnect).pack(side='left')
        ttk.Label(r, text='在线检测秒').pack(side='left', padx=(12, 4))
        ttk.Entry(r, textvariable=self.var_health, width=6).pack(side='left')
        r = ttk.Frame(frm)
        r.grid(row=8, column=0, columnspan=4, sticky='w', pady=(6, 0))
        ttk.Button(r, text='启动', command=self._on_launch).pack(side='left', padx=2)
        ttk.Button(r, text='连接', command=self._on_connect).pack(side='left', padx=2)
        ttk.Button(r, text='重连', command=self._on_reconnect).pack(side='left', padx=2)
        ttk.Button(r, text='断开', command=self._on_disconnect).pack(side='left', padx=2)
        ttk.Label(frm, text='SnowLuma/NapCat 会自动发现正在运行的目录并验证 token；'
                            '留空启动路径也能连接，只要它们已在运行。',
                  foreground='#888888', wraplength=760, justify='left').grid(
            row=9, column=0, columnspan=4, sticky='w', pady=(6, 0))
        frm.columnconfigure(1, weight=1)

    def _build_ai_tab(self):
        host = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(host, text=' AI 配置 ')
        sc = ScrollFrame(host)
        sc.pack(fill='both', expand=True)

        llm = ttk.LabelFrame(sc.inner, text='大模型（OpenAI 兼容 / Anthropic）', padding=8)
        llm.pack(fill='x', pady=(6, 0))
        self.var_provider = tk.StringVar()
        self.var_base = tk.StringVar()
        self.var_key = tk.StringVar()
        self.var_model = tk.StringVar()
        self.var_temp = tk.StringVar()
        self.var_maxtok = tk.StringVar()
        self.var_timeout = tk.StringVar()
        self.var_retry = tk.StringVar()
        p = ttk.Combobox(llm, textvariable=self.var_provider, state='readonly',
                         values=_PROVIDERS, width=12)
        ttk.Label(llm, text='提供方').grid(row=0, column=0, sticky='w', padx=4, pady=2)
        p.grid(row=0, column=1, sticky='w', padx=4, pady=2)
        p.bind('<<ComboboxSelected>>', lambda e: self._on_provider())
        self._row(llm, 1, 'API 地址', self.var_base, width=44)
        self._row(llm, 2, 'API 密钥', self.var_key, width=44, show='*')
        self._row(llm, 3, '模型', self.var_model, width=24)
        self._row(llm, 4, '温度', self.var_temp, width=8)
        self._row(llm, 5, '最大 tokens', self.var_maxtok, width=8)
        self._row(llm, 6, '超时秒/重试', self.var_timeout, width=8)
        ttk.Entry(llm, textvariable=self.var_retry, width=8).grid(row=6, column=2, sticky='w', padx=4)
        llm.columnconfigure(1, weight=1)

        pr = ttk.LabelFrame(sc.inner, text='人设 / 提示词', padding=8)
        pr.pack(fill='x', pady=(8, 0))
        self.prompt = tk.Text(pr, height=7, wrap='word', font=('Consolas', 9))
        self.prompt.pack(fill='both', expand=True, padx=2, pady=2)

        rule = ttk.LabelFrame(sc.inner, text='回复规则', padding=8)
        rule.pack(fill='x', pady=(8, 0))
        self.var_mention = tk.BooleanVar(value=False)
        self.var_trig_enabled = tk.BooleanVar(value=True)
        self.var_trigger_word = tk.StringVar()
        self.var_trigger = tk.StringVar()
        self.var_auto = tk.BooleanVar(value=False)
        self.var_chance = tk.StringVar()
        self.var_at = tk.BooleanVar(value=True)
        self.var_quote = tk.BooleanVar(value=True)
        ttk.Checkbutton(rule, text='被 @ 时回复', variable=self.var_mention).grid(
            row=0, column=0, sticky='w', padx=4, pady=2)
        ttk.Checkbutton(rule, text='触发词回复', variable=self.var_trig_enabled).grid(
            row=0, column=1, sticky='w', padx=4)
        ttk.Checkbutton(rule, text='每条都回复', variable=self.var_auto).grid(
            row=0, column=2, sticky='w', padx=4)
        self._row(rule, 1, '触发词（必须开头）', self.var_trigger_word, width=24,
                  hint='用户自定义字符串；消息以此开头才回复（"[AI]你好"触发，"你好[AI]"不触发）；逗号分隔多个')
        self._row(rule, 2, '触发正则（可选）', self.var_trigger, width=24,
                  hint='高级：额外正则，匹配即回复；可留空')
        r = ttk.Frame(rule)
        r.grid(row=3, column=0, columnspan=4, sticky='w', pady=2)
        ttk.Label(r, text='每条都回复概率 %').pack(side='left')
        ttk.Entry(r, textvariable=self.var_chance, width=6).pack(side='left', padx=(4, 12))
        ttk.Checkbutton(r, text='回复时 @ 对方', variable=self.var_at).pack(side='left')
        ttk.Checkbutton(r, text='引用触发消息（针对性回复）',
                        variable=self.var_quote).pack(side='left', padx=(12, 0))
        rule.columnconfigure(1, weight=1)

        ctx = ttk.LabelFrame(sc.inner, text='上下文与限制', padding=8)
        ctx.pack(fill='x', pady=(8, 0))
        self.var_ctx_enabled = tk.BooleanVar(value=True)
        self.var_ctx_len = tk.StringVar()
        self.var_ctx_budget = tk.StringVar()
        self.var_max_msgs = tk.StringVar()
        self.var_max_chars = tk.StringVar()
        self.var_cooldown = tk.StringVar()
        ttk.Checkbutton(ctx, text='启用上下文', variable=self.var_ctx_enabled).grid(
            row=0, column=0, sticky='w', padx=4, pady=2)
        self._row(ctx, 0, '上下文长度', self.var_ctx_len, col=2, width=6)
        self._row(ctx, 1, '上下文 Token 预算', self.var_ctx_budget, width=8,
                  hint='0 = 只按条数；超预算时从最早的一句开始、按句子裁剪')
        self._row(ctx, 2, '最大回复条数', self.var_max_msgs, width=6)
        self._row(ctx, 3, '单条最大字数', self.var_max_chars, width=6)
        self._row(ctx, 4, '冷却秒', self.var_cooldown, width=6)
        ctx.columnconfigure(1, weight=1)

        srch = ttk.LabelFrame(
            sc.inner, text='联网搜索（免费源 / 自定义源；只有真要回复、且命中时才搜）',
            padding=8)
        srch.pack(fill='x', pady=(8, 0))
        self.var_search_enabled = tk.BooleanVar(value=False)
        self.var_search_provider = tk.StringVar(value=self._SEARCH_PROVIDER_LABELS[0])
        self.var_search_mode = tk.StringVar(value=self._SEARCH_MODE_LABELS[0])
        self.var_search_kw = tk.StringVar()
        self.var_search_max = tk.StringVar(value='5')
        self.var_search_timeout = tk.StringVar(value='12')
        self.var_search_url = tk.StringVar()
        self.var_search_key = tk.StringVar()
        ttk.Checkbutton(srch, text='启用联网搜索', variable=self.var_search_enabled).grid(
            row=0, column=0, columnspan=2, sticky='w', padx=4, pady=2)
        ttk.Label(srch, text='搜索来源').grid(row=1, column=0, sticky='w', padx=4, pady=2)
        ttk.Combobox(srch, textvariable=self.var_search_provider, state='readonly',
                     values=self._SEARCH_PROVIDER_LABELS, width=34).grid(
            row=1, column=1, sticky='w', padx=4, pady=2)
        ttk.Label(srch, text='什么时候搜').grid(row=2, column=0, sticky='w', padx=4, pady=2)
        ttk.Combobox(srch, textvariable=self.var_search_mode, state='readonly',
                     values=self._SEARCH_MODE_LABELS, width=30).grid(
            row=2, column=1, sticky='w', padx=4, pady=2)
        r = ttk.Frame(srch)
        r.grid(row=3, column=0, columnspan=4, sticky='w', pady=2)
        ttk.Label(r, text='结果条数').pack(side='left')
        ttk.Entry(r, textvariable=self.var_search_max, width=6).pack(side='left', padx=(4, 16))
        ttk.Label(r, text='超时秒').pack(side='left')
        ttk.Entry(r, textvariable=self.var_search_timeout, width=6).pack(side='left', padx=4)
        self._row(srch, 4, '自动搜索关键词', self.var_search_kw, width=52,
                  hint='逗号分隔；消息里含任意一个才去搜（模式选「每次」则忽略）')
        self._row(srch, 5, '自定义接口地址', self.var_search_url, width=52,
                  hint='带 {query} 走 GET（SearXNG）；不带则 POST JSON（Tavily/Serper）')
        self._row(srch, 6, '自定义接口 Key', self.var_search_key, width=52, show='*',
                  hint='只有自定义接口需要，可留空')
        ttk.Label(srch, foreground='#888888', wraplength=760, justify='left',
                  text='搜索只在机器人**本来就要回复**时触发，搜到的结果会作为参考塞进提示词。'
                       'DuckDuckGo / Bing 都是免费网页抓取，可能被限流；要稳定可填一个自定义 JSON 接口'
                       '（SearXNG：http://127.0.0.1:8080/search?q={query}&format=json）。').grid(
            row=7, column=0, columnspan=4, sticky='w', padx=4, pady=(4, 0))
        srch.columnconfigure(1, weight=1)

        bl = ttk.LabelFrame(sc.inner, text='黑名单（每行一个 QQ 号）', padding=8)
        bl.pack(fill='x', pady=(8, 4))
        self.blacklist = tk.Text(bl, height=4, wrap='word', font=('Consolas', 9))
        self.blacklist.pack(fill='both', expand=True, padx=2, pady=2)

        flt = ttk.LabelFrame(sc.inner, text='输出过滤（防注入 / 语言检测）', padding=8)
        flt.pack(fill='x', pady=(8, 4))
        self.var_strip = tk.BooleanVar(value=True)
        ttk.Checkbutton(flt, text='回复中移除触发词（如 [AI]，防止群友注入提示词自触发）',
                        variable=self.var_strip).pack(anchor='w', padx=2, pady=2)
        ttk.Label(flt, text='违禁词（每行一个；回复含其中任意一个则整条丢弃）',
                  foreground='#888888').pack(anchor='w', padx=2)
        self.blocked = tk.Text(flt, height=4, wrap='word', font=('Consolas', 9))
        self.blocked.pack(fill='both', expand=True, padx=2, pady=2)

    def _build_interact_tab(self):
        host = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(host, text=' 互动 ')
        sc = ScrollFrame(host)
        sc.pack(fill='both', expand=True)
        host = sc.inner

        sd = ttk.LabelFrame(host, text='点歌（群内发「触发词 + 歌名」即发音乐卡片）', padding=8)
        sd.pack(fill='x', pady=(6, 0))
        self.var_song_enabled = tk.BooleanVar(value=True)
        self.var_song_trigger = tk.StringVar()
        self.var_song_platform = tk.StringVar(value='auto')
        self.var_song_cooldown = tk.StringVar()
        self.var_song_timeout = tk.StringVar()
        ttk.Checkbutton(sd, text='启用点歌', variable=self.var_song_enabled).grid(
            row=0, column=0, sticky='w', padx=4, pady=2)
        self._row(sd, 1, '触发词（必须开头）', self.var_song_trigger, width=18,
                  hint='例如 [点歌] 起风了；命中后不再交给 AI 聊天')
        ttk.Label(sd, text='平台').grid(row=2, column=0, sticky='w', padx=4, pady=2)
        ttk.Combobox(sd, textvariable=self.var_song_platform, state='readonly',
                     values=['auto', 'qq', '163'], width=8).grid(
            row=2, column=1, sticky='w', padx=4, pady=2)
        r = ttk.Frame(sd)
        r.grid(row=3, column=0, columnspan=3, sticky='w', pady=2)
        ttk.Label(r, text='冷却秒').pack(side='left')
        ttk.Entry(r, textvariable=self.var_song_cooldown, width=6).pack(side='left', padx=(4, 14))
        ttk.Label(r, text='搜索超时秒').pack(side='left')
        ttk.Entry(r, textvariable=self.var_song_timeout, width=6).pack(side='left', padx=4)
        ttk.Label(sd, text='auto=先 QQ 音乐再网易云；登录网易云会员后，VIP 歌也能解析出完整可播放直链。',
                  foreground='#888888', wraplength=760, justify='left').grid(
            row=4, column=0, columnspan=3, sticky='w', pady=(4, 0))

        # --- 网易云会员登录（替群友解析 VIP 歌的可播放直链）---
        self.var_song_netease_cookie = tk.StringVar()
        ttk.Label(sd, text='网易云登录（会员）').grid(row=5, column=0, sticky='w', padx=4, pady=2)
        ttk.Entry(sd, textvariable=self.var_song_netease_cookie, width=40).grid(
            row=5, column=1, sticky='we', padx=4, pady=2)
        netease_btns = ttk.Frame(sd)
        netease_btns.grid(row=5, column=2, sticky='w', padx=4)
        ttk.Button(netease_btns, text='扫码登录', command=self._on_netease_login).pack(side='left')
        ttk.Button(netease_btns, text='验证登录', command=self._on_netease_verify).pack(
            side='left', padx=(4, 0))

        qrrow = ttk.Frame(sd)
        qrrow.grid(row=6, column=0, columnspan=3, sticky='w', padx=4, pady=4)
        self._netease_qr_label = ttk.Label(qrrow)
        self._netease_qr_label.pack(side='left')
        self._netease_qr_photo = None
        self._netease_url = ''
        qrbtns = ttk.Frame(qrrow)
        qrbtns.pack(side='left', anchor='n', padx=8)
        ttk.Button(qrbtns, text='在浏览器打开登录链接',
                   command=self._on_netease_open).pack(anchor='w', pady=2)
        ttk.Button(qrbtns, text='复制登录链接',
                   command=self._on_netease_copy).pack(anchor='w', pady=2)
        self._netease_status = tk.StringVar(value='未登录（VIP 歌只能放试听）')
        ttk.Label(sd, textvariable=self._netease_status, foreground='#888888',
                  wraplength=760, justify='left').grid(
            row=7, column=0, columnspan=3, sticky='w', padx=4, pady=(0, 4))
        ttk.Label(sd, foreground='#888888', wraplength=760, justify='left',
                  text='点「扫码登录」→ 上面直接出现二维码（也可用浏览器打开链接）→ '
                       '用【网易云音乐 App】扫一扫并在手机上点确认；成功后 Cookie 会自动填入并保存。\n'
                       '自己粘贴 Cookie 的话：把浏览器 music.163.com 的 Cookie（含 MUSIC_U=…）粘到上面，'
                       '点「验证登录」——会显示账号昵称，并实测一首会员歌能不能拿到完整直链。').grid(
            row=8, column=0, columnspan=3, sticky='w', padx=4)
        sd.columnconfigure(1, weight=1)

        af = ttk.LabelFrame(host, text='好感度（随聊天增长，会影响 AI 语气）', padding=8)
        af.pack(fill='x', pady=(8, 4))
        self.var_aff_enabled = tk.BooleanVar(value=True)
        self.var_aff_start = tk.StringVar()
        self.var_aff_max = tk.StringVar()
        self.var_aff_gain = tk.StringVar()
        self.var_aff_cap = tk.StringVar()
        self.var_aff_trigger = tk.StringVar()
        self.var_aff_hint = tk.BooleanVar(value=True)
        self.var_aff_persist = tk.BooleanVar(value=True)
        self.var_aff_checkin = tk.BooleanVar(value=True)
        self.var_aff_checkin_trigger = tk.StringVar()
        self.var_aff_checkin_gain = tk.StringVar()
        ttk.Checkbutton(af, text='启用好感度', variable=self.var_aff_enabled).pack(
            anchor='w', padx=4, pady=2)
        r = ttk.Frame(af)
        r.pack(fill='x', pady=2)
        ttk.Label(r, text='查询触发词').pack(side='left')
        ttk.Entry(r, textvariable=self.var_aff_trigger, width=14).pack(side='left', padx=(4, 16))
        ttk.Label(r, text='初始').pack(side='left')
        ttk.Entry(r, textvariable=self.var_aff_start, width=6).pack(side='left', padx=(4, 16))
        ttk.Label(r, text='上限').pack(side='left')
        ttk.Entry(r, textvariable=self.var_aff_max, width=6).pack(side='left', padx=(4, 16))
        ttk.Label(r, text='每次被搭话 +').pack(side='left')
        ttk.Entry(r, textvariable=self.var_aff_gain, width=6).pack(side='left', padx=(4, 16))
        ttk.Label(r, text='每人每天上限').pack(side='left')
        ttk.Entry(r, textvariable=self.var_aff_cap, width=6).pack(side='left', padx=4)
        r2 = ttk.Frame(af)
        r2.pack(fill='x', pady=(4, 0))
        ttk.Checkbutton(r2, text='影响人设提示词（好感度高时更亲近）',
                        variable=self.var_aff_hint).pack(side='left', padx=(4, 12))
        ttk.Checkbutton(r2, text='保存到 affinity.json',
                        variable=self.var_aff_persist).pack(side='left', padx=(0, 12))
        ttk.Button(r2, text='清空好感度', command=self._on_clear_affinity).pack(side='left')

        r3 = ttk.Frame(af)
        r3.pack(fill='x', pady=(4, 0))
        ttk.Checkbutton(r3, text='启用每日签到', variable=self.var_aff_checkin).pack(
            side='left', padx=(4, 12))
        ttk.Label(r3, text='签到触发词').pack(side='left')
        ttk.Entry(r3, textvariable=self.var_aff_checkin_trigger, width=12).pack(
            side='left', padx=(4, 14))
        ttk.Label(r3, text='签到好感度 +').pack(side='left')
        ttk.Entry(r3, textvariable=self.var_aff_checkin_gain, width=6).pack(side='left', padx=4)
        ttk.Label(r3, text='（每天一次，不受每日上限限制）', foreground='#888888').pack(
            side='left', padx=(4, 0))

        # --- 拍一拍（调 send_poke；完全不让大模型决定）---
        pk = ttk.LabelFrame(host, text='拍一拍（调 OneBot send_poke；不让大模型决定）', padding=8)
        pk.pack(fill='x', pady=(8, 4))
        self.var_poke_enabled = tk.BooleanVar(value=True)
        self.var_poke_back = tk.BooleanVar(value=True)
        self.var_poke_back_chance = tk.StringVar(value='100')
        self.var_poke_proactive = tk.BooleanVar(value=True)
        self.var_poke_threshold = tk.StringVar(value='60')
        self.var_poke_chance = tk.StringVar(value='15')
        self.var_poke_cooldown = tk.StringVar(value='120')
        ttk.Checkbutton(pk, text='启用拍一拍', variable=self.var_poke_enabled).pack(
            anchor='w', padx=4, pady=2)
        rp = ttk.Frame(pk)
        rp.pack(fill='x', pady=2)
        ttk.Checkbutton(rp, text='被拍了就拍回去', variable=self.var_poke_back).pack(
            side='left', padx=(4, 8))
        ttk.Label(rp, text='回拍概率 %').pack(side='left')
        ttk.Entry(rp, textvariable=self.var_poke_back_chance, width=6).pack(
            side='left', padx=(4, 16))
        ttk.Label(rp, text='同群冷却秒').pack(side='left')
        ttk.Entry(rp, textvariable=self.var_poke_cooldown, width=7).pack(side='left', padx=4)
        rq = ttk.Frame(pk)
        rq.pack(fill='x', pady=(4, 0))
        ttk.Checkbutton(rq, text='好感度高的群友说话时主动拍', variable=self.var_poke_proactive).pack(
            side='left', padx=(4, 8))
        ttk.Label(rq, text='好感度 ≥').pack(side='left')
        ttk.Entry(rq, textvariable=self.var_poke_threshold, width=6).pack(
            side='left', padx=(4, 12))
        ttk.Label(rq, text='每次说话有').pack(side='left')
        ttk.Entry(rq, textvariable=self.var_poke_chance, width=6).pack(
            side='left', padx=(4, 4))
        ttk.Label(rq, text='% 概率拍一下').pack(side='left')
        ttk.Label(pk, foreground='#888888', wraplength=760, justify='left',
                  text='拍一拍有风控：冷却别调太小（默认 120 秒），概率别拉满；'
                       '真的被限了就先把「主动拍」关掉，只留「被拍回拍」。').pack(
            anchor='w', padx=4, pady=(4, 0))

    def _build_misc_tab(self):
        host = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(host, text=' 杂项 ')
        sc = ScrollFrame(host)
        sc.pack(fill='both', expand=True)

        video = ttk.LabelFrame(
            sc.inner,
            text='视频推荐（群友发「触发词 + 视频推荐」→ 群里推一批 B 站视频）', padding=8)
        video.pack(fill='x', pady=(6, 4))
        self.var_misc_video_enabled = tk.BooleanVar(value=True)
        self.var_misc_video_trigger = tk.StringVar()
        self.var_misc_video_source = tk.StringVar(value=self._VIDEO_SOURCE_LABELS[0])
        self.var_misc_video_count = tk.StringVar(value='5')
        self.var_misc_video_cooldown = tk.StringVar(value='30')
        self.var_misc_video_title = tk.StringVar()
        self.var_misc_video_item = tk.StringVar()
        self.var_misc_video_cool = tk.StringVar()
        self.var_misc_video_fail = tk.StringVar()
        ttk.Checkbutton(video, text='启用视频推荐', variable=self.var_misc_video_enabled).grid(
            row=0, column=0, columnspan=2, sticky='w', padx=4, pady=2)
        self._row(video, 1, '触发词（必须开头）', self.var_misc_video_trigger, width=18,
                  hint='例如 [视频推荐]；命中后不再交给 AI 聊天')
        ttk.Label(video, text='推荐来源').grid(row=2, column=0, sticky='w', padx=4, pady=2)
        ttk.Combobox(video, textvariable=self.var_misc_video_source, state='readonly',
                     values=self._VIDEO_SOURCE_LABELS, width=24).grid(
            row=2, column=1, sticky='w', padx=4, pady=2)
        r = ttk.Frame(video)
        r.grid(row=3, column=0, columnspan=3, sticky='w', pady=2)
        ttk.Label(r, text='每次推几条').pack(side='left')
        ttk.Entry(r, textvariable=self.var_misc_video_count, width=6).pack(side='left', padx=(4, 16))
        ttk.Label(r, text='全服冷却秒').pack(side='left')
        ttk.Entry(r, textvariable=self.var_misc_video_cooldown, width=8).pack(side='left', padx=(4, 8))
        ttk.Label(r, text='谁的请求都算；冷却过后再发 = 换一批新的（越点越多）',
                  foreground='#888888').pack(side='left')
        self._row(video, 4, '抬头文案', self.var_misc_video_title, width=52,
                  hint='可用 {player} 谁点的、{count} 条数、{source} 来源名')
        self._row(video, 5, '每条文案', self.var_misc_video_item, width=52,
                  hint='可用 {index} 序号、{title} 标题、{owner} 备注、{link} 链接')
        self._row(video, 6, '冷却中提示', self.var_misc_video_cool, width=52,
                  hint='可用 {wait} 还要等几秒、{player} 谁点的')
        self._row(video, 7, '抓取失败提示', self.var_misc_video_fail, width=52)

        bili = ttk.LabelFrame(video, text='B 站账号（只有来源选「我的收藏夹」才需要）', padding=6)
        bili.grid(row=8, column=0, columnspan=4, sticky='we', padx=4, pady=(8, 4))
        self.var_misc_bili_cookie = tk.StringVar()
        self.var_misc_bili_fav = tk.StringVar()
        self.var_misc_bili_status = tk.StringVar(value='（还没读取）')
        self._bili_fav_map = {}
        self._bili_fav_cur = {'media_id': 0, 'name': ''}
        ttk.Label(bili, text='SESSDATA').grid(row=0, column=0, sticky='w', padx=4, pady=3)
        ttk.Entry(bili, textvariable=self.var_misc_bili_cookie, width=44, show='*').grid(
            row=0, column=1, sticky='we', padx=4, pady=3)
        ttk.Button(bili, text='读取收藏夹', command=self._on_bili_folders).grid(
            row=0, column=2, sticky='w', padx=4, pady=3)
        ttk.Label(bili, textvariable=self.var_misc_bili_status,
                  foreground='#888888').grid(row=0, column=3, sticky='w', padx=4)
        ttk.Label(bili, text='收藏夹').grid(row=1, column=0, sticky='w', padx=4, pady=3)
        self.cmb_bili_fav = ttk.Combobox(bili, textvariable=self.var_misc_bili_fav,
                                         width=36, values=[])
        self.cmb_bili_fav.grid(row=1, column=1, sticky='w', padx=4, pady=3)
        ttk.Label(bili, text='点上面按钮读出来再选；也可以直接填收藏夹 id（纯数字）',
                  foreground='#888888').grid(row=1, column=2, columnspan=2, sticky='w', padx=4)
        ttk.Label(bili, text='拿法：浏览器登录 bilibili.com → F12 → Application → Cookies，'
                             '把整条 Cookie 粘进来（或只填 SESSDATA 的值），再点「读取收藏夹」选一个。',
                  foreground='#888888', wraplength=760, justify='left').grid(
            row=2, column=1, columnspan=3, sticky='w', padx=4, pady=(2, 0))
        bili.columnconfigure(1, weight=1)
        video.columnconfigure(1, weight=1)

    def _build_log_tab(self):
        tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab, text=' 日志 ')
        self.log = tk.Text(tab, height=24, wrap='word', state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True)
        # 日志着色：收到 / 回复 / 警告 / 错误
        for tag, color in (('in', '#1565c0'), ('out', '#2e7d32'),
                           ('warn', '#ef6c00'), ('error', '#c62828'),
                           ('ai', '#6a1b9a')):
            self.log.tag_configure(tag, foreground=color)
        sb = ttk.Scrollbar(tab, orient='vertical', command=self.log.yview)
        sb.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=sb.set)
        bottom = ttk.Frame(tab)
        bottom.pack(fill='x', pady=(6, 0))
        self.send_group_id = tk.StringVar()
        self.send_text = tk.StringVar()
        ttk.Entry(bottom, textvariable=self.send_group_id, width=14).pack(side='left')
        ttk.Entry(bottom, textvariable=self.send_text).pack(side='left', fill='x', expand=True, padx=6)
        ttk.Button(bottom, text='手动发送', command=self._on_manual_send).pack(side='right')

    def _row(self, parent, row, label, var, width=30, hint='', col=0, show=''):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky='w', padx=4, pady=2)
        e = ttk.Entry(parent, textvariable=var, width=width, show=show)
        e.grid(row=row, column=col + 1, sticky='we', padx=4, pady=2)
        if hint:
            ttk.Label(parent, text=hint, foreground='#888888').grid(
                row=row, column=col + 2, columnspan=2, sticky='w', padx=4)
        return e

    # ------------------------------------------------------------------
    def _on_fw_changed(self):
        self._save_endpoint(getattr(self, '_editing_fw', 'snowluma'))
        fw = 'napcat' if self.var_fw.get().strip().lower().startswith('nap') else 'snowluma'
        self._editing_fw = fw
        self.controller.config.framework = fw
        self._load_endpoint(fw)

    def _load_endpoint(self, fw):
        self._editing_fw = fw
        ep = self.controller.config.napcat if fw == 'napcat' else self.controller.config.snowluma
        self.var_mode.set(ep.mode if ep.mode in ('forward', 'reverse') else 'forward')
        url, token = ep.url or '', ep.accessToken or ''
        if fw == 'snowluma':
            det = self.controller.snowluma_ws_auth()
            if det:
                if det[2] and not token:
                    token = det[2]
                if not url:
                    url = f'ws://{det[0]}:{det[1]}'
        self.var_url.set(url)
        self.var_token.set(token)
        self.var_lhost.set(ep.listenHost or '0.0.0.0')
        self.var_lport.set(str(ep.listenPort))
        self.var_launcher.set(ep.launcherPath or '')

    def _save_endpoint(self, fw):
        ep = self.controller.config.napcat if fw == 'napcat' else self.controller.config.snowluma
        ep.mode = self.var_mode.get().strip() or 'forward'
        ep.url = self.var_url.get().strip()
        ep.accessToken = self.var_token.get().strip()
        ep.listenHost = self.var_lhost.get().strip() or '0.0.0.0'
        ep.listenPort = self._int(self.var_lport.get(), 3002)
        ep.launcherPath = self.var_launcher.get().strip()
        ep.validate()

    # ------------------------------------------------------------------
    def _load_config(self):
        cfg = self.controller.config
        self._editing_fw = cfg.framework
        self.var_fw.set('NapCat' if cfg.framework == 'napcat' else 'SnowLuma')
        self._load_endpoint(cfg.framework)
        self.var_groups.set(', '.join(cfg.groups or []))
        self.var_ignore.set(', '.join(cfg.ignoreGroups or []))
        self.var_autoreconnect.set(bool(cfg.autoReconnect))
        self.var_health.set(str(cfg.healthCheckSeconds))

        ai = cfg.ai
        self.ai_on.set(bool(ai.enabled))
        self.var_provider.set(ai.provider or 'openai')
        self.var_base.set(ai.baseUrl or '')
        self.var_key.set(ai.apiKey or '')
        self.var_model.set(ai.model)
        self.var_temp.set(str(ai.temperature))
        self.var_maxtok.set(str(ai.maxTokens))
        self.var_timeout.set(str(ai.timeoutSeconds))
        self.var_retry.set(str(ai.retryCount))
        self.prompt.delete('1.0', 'end')
        self.prompt.insert('1.0', ai.systemPrompt)
        self.var_mention.set(bool(ai.mentionReply))
        self.var_trig_enabled.set(bool(ai.triggerEnabled))
        self.var_trigger_word.set(ai.triggerWord or '')
        self.var_trigger.set(ai.triggerRegex or '')
        self.var_auto.set(bool(ai.autoReply))
        self.var_chance.set(str(ai.autoReplyChance))
        self.var_at.set(bool(ai.atReply))
        self.var_quote.set(bool(ai.quoteReply))
        self.var_ctx_enabled.set(bool(ai.contextEnabled))
        self.var_ctx_len.set(str(ai.contextLength))
        self.var_ctx_budget.set(str(ai.contextTokenBudget))
        self.var_max_msgs.set(str(ai.maxReplyMessages))
        self.var_max_chars.set(str(ai.maxCharsPerMessage))
        self.var_cooldown.set(str(ai.cooldownSeconds))
        self.var_search_enabled.set(bool(ai.searchEnabled))
        self.var_search_provider.set(
            dict(zip(self._SEARCH_PROVIDER_KEYS, self._SEARCH_PROVIDER_LABELS)).get(
                ai.searchProvider, self._SEARCH_PROVIDER_LABELS[0]))
        self.var_search_mode.set(
            dict(zip(self._SEARCH_MODE_KEYS, self._SEARCH_MODE_LABELS)).get(
                ai.searchMode, self._SEARCH_MODE_LABELS[0]))
        self.var_search_kw.set(ai.searchKeywords or '')
        self.var_search_max.set(str(ai.searchMaxResults))
        self.var_search_timeout.set(str(ai.searchTimeoutSeconds))
        self.var_search_url.set(ai.searchApiUrl or '')
        self.var_search_key.set(ai.searchApiKey or '')
        self.blacklist.delete('1.0', 'end')
        self.blacklist.insert('1.0', '\n'.join(b.get('id', '') for b in ai.blacklist))
        self.var_strip.set(bool(ai.stripTrigger))
        self.blocked.delete('1.0', 'end')
        self.blocked.insert('1.0', '\n'.join(str(w) for w in (ai.blockedWords or [])))

        song = cfg.song
        self.var_song_enabled.set(bool(song.enabled))
        self.var_song_trigger.set(song.trigger or '')
        self.var_song_platform.set(song.platform or 'auto')
        self.var_song_cooldown.set(str(song.cooldownSeconds))
        self.var_song_timeout.set(str(song.timeoutSeconds))
        self.var_song_netease_cookie.set(song.neteaseCookie or '')
        if hasattr(self, '_netease_status'):
            self._netease_status.set('已登录（会员 Cookie 已保存）'
                                     if (song.neteaseCookie or '').strip()
                                     else '未登录（VIP 歌只能放试听）')

        aff = cfg.affinity
        self.var_aff_enabled.set(bool(aff.enabled))
        self.var_aff_trigger.set(aff.queryTrigger or '')
        self.var_aff_start.set(str(aff.start))
        self.var_aff_max.set(str(aff.maximum))
        self.var_aff_gain.set(str(aff.gainPerChat))
        self.var_aff_cap.set(str(aff.dailyCap))
        self.var_aff_hint.set(bool(aff.promptHint))
        self.var_aff_persist.set(bool(aff.persist))
        self.var_aff_checkin.set(bool(aff.checkinEnabled))
        self.var_aff_checkin_trigger.set(aff.checkinTrigger or '')
        self.var_aff_checkin_gain.set(str(aff.checkinGain))

        pk = cfg.poke
        self.var_poke_enabled.set(bool(pk.enabled))
        self.var_poke_back.set(bool(pk.pokeBack))
        self.var_poke_back_chance.set(str(pk.pokeBackChance))
        self.var_poke_proactive.set(bool(pk.proactive))
        self.var_poke_threshold.set(str(pk.affinityThreshold))
        self.var_poke_chance.set(str(pk.proactiveChance))
        self.var_poke_cooldown.set(str(pk.cooldownSeconds))

        misc = cfg.misc
        self.var_misc_video_enabled.set(bool(misc.videoEnabled))
        self.var_misc_video_trigger.set(misc.videoTrigger or '')
        self.var_misc_video_source.set(dict(zip(self._VIDEO_SOURCE_KEYS,
                                                self._VIDEO_SOURCE_LABELS)).get(
            misc.videoSource, self._VIDEO_SOURCE_LABELS[0]))
        self.var_misc_video_count.set(str(misc.videoCount))
        self.var_misc_video_cooldown.set(str(misc.videoCooldownSeconds))
        self.var_misc_video_title.set(misc.videoTitle)
        self.var_misc_video_item.set(misc.videoItemText)
        self.var_misc_video_cool.set(misc.videoCoolText)
        self.var_misc_video_fail.set(misc.videoFailText)
        self.var_misc_bili_cookie.set(misc.biliCookie or '')
        self._bili_fav_cur = {'media_id': int(misc.biliFavMediaId or 0),
                              'name': str(misc.biliFavName or '')}
        self.var_misc_bili_fav.set(str(misc.biliFavName or ''))
        self.var_misc_bili_status.set(
            '已配置：%s' % misc.biliFavName if misc.biliFavName else '（还没读取）')

    def _gather(self):
        cfg = self.controller.config
        cfg.framework = ('napcat' if self.var_fw.get().strip().lower().startswith('nap')
                         else 'snowluma')
        self._save_endpoint(getattr(self, '_editing_fw', cfg.framework))
        cfg.groups = [x for x in re_split(self.var_groups.get())]
        cfg.ignoreGroups = [x for x in re_split(self.var_ignore.get())]
        cfg.autoReconnect = self.var_autoreconnect.get()
        cfg.healthCheckSeconds = self._int(self.var_health.get(), 30)

        ai = cfg.ai
        ai.enabled = self.ai_on.get()
        ai.provider = self.var_provider.get().strip() or 'openai'
        ai.baseUrl = self.var_base.get().strip()
        ai.apiKey = self.var_key.get()
        ai.model = self.var_model.get().strip() or 'gpt-4o-mini'
        ai.temperature = self._float(self.var_temp.get(), 0.8)
        ai.maxTokens = self._int(self.var_maxtok.get(), 512)
        ai.timeoutSeconds = self._int(self.var_timeout.get(), 30)
        ai.retryCount = self._int(self.var_retry.get(), 1)
        ai.systemPrompt = self.prompt.get('1.0', 'end').strip()
        ai.mentionReply = self.var_mention.get()
        ai.triggerEnabled = self.var_trig_enabled.get()
        ai.triggerWord = self.var_trigger_word.get().strip()
        ai.triggerRegex = self.var_trigger.get().strip()
        ai.autoReply = self.var_auto.get()
        ai.autoReplyChance = self._int(self.var_chance.get(), 100)
        ai.atReply = self.var_at.get()
        ai.quoteReply = self.var_quote.get()
        ai.contextEnabled = self.var_ctx_enabled.get()
        ai.contextLength = self._int(self.var_ctx_len.get(), 40)
        ai.contextTokenBudget = self._int(self.var_ctx_budget.get(), 1200)
        ai.maxReplyMessages = self._int(self.var_max_msgs.get(), 2)
        ai.maxCharsPerMessage = self._int(self.var_max_chars.get(), 120)
        ai.cooldownSeconds = self._int(self.var_cooldown.get(), 5)
        ai.searchEnabled = self.var_search_enabled.get()
        ai.searchProvider = dict(zip(
            self._SEARCH_PROVIDER_LABELS, self._SEARCH_PROVIDER_KEYS)).get(
            self.var_search_provider.get().strip(), ai.searchProvider or 'duckduckgo')
        ai.searchMode = dict(zip(
            self._SEARCH_MODE_LABELS, self._SEARCH_MODE_KEYS)).get(
            self.var_search_mode.get().strip(), ai.searchMode or 'keywords')
        ai.searchKeywords = self.var_search_kw.get().strip()
        ai.searchMaxResults = self._int(self.var_search_max.get(), 5)
        ai.searchTimeoutSeconds = self._int(self.var_search_timeout.get(), 12)
        ai.searchApiUrl = self.var_search_url.get().strip()
        ai.searchApiKey = self.var_search_key.get().strip()
        ids = [ln.strip() for ln in self.blacklist.get('1.0', 'end').splitlines() if ln.strip()]
        ai.blacklist = [{'id': i, 'name': ''} for i in ids]
        ai.stripTrigger = self.var_strip.get()
        ai.blockedWords = [ln.strip() for ln in self.blocked.get('1.0', 'end').splitlines()
                           if ln.strip()]

        song = cfg.song
        song.enabled = self.var_song_enabled.get()
        song.trigger = self.var_song_trigger.get().strip()
        song.platform = self.var_song_platform.get().strip() or 'auto'
        song.cooldownSeconds = self._int(self.var_song_cooldown.get(), 4)
        song.timeoutSeconds = self._int(self.var_song_timeout.get(), 8)
        song.neteaseCookie = self.var_song_netease_cookie.get().strip()

        aff = cfg.affinity
        aff.enabled = self.var_aff_enabled.get()
        aff.queryTrigger = self.var_aff_trigger.get().strip()
        aff.start = self._int(self.var_aff_start.get(), 20)
        aff.maximum = self._int(self.var_aff_max.get(), 100)
        aff.gainPerChat = self._int(self.var_aff_gain.get(), 2)
        aff.dailyCap = self._int(self.var_aff_cap.get(), 20)
        aff.promptHint = self.var_aff_hint.get()
        aff.persist = self.var_aff_persist.get()
        aff.checkinEnabled = self.var_aff_checkin.get()
        aff.checkinTrigger = self.var_aff_checkin_trigger.get().strip()
        aff.checkinGain = self._int(self.var_aff_checkin_gain.get(), 5)

        pk = cfg.poke
        pk.enabled = self.var_poke_enabled.get()
        pk.pokeBack = self.var_poke_back.get()
        pk.pokeBackChance = self._int(self.var_poke_back_chance.get(), 100)
        pk.proactive = self.var_poke_proactive.get()
        pk.affinityThreshold = self._int(self.var_poke_threshold.get(), 60)
        pk.proactiveChance = self._int(self.var_poke_chance.get(), 15)
        pk.cooldownSeconds = self._int(self.var_poke_cooldown.get(), 120)

        misc = cfg.misc
        misc.videoEnabled = self.var_misc_video_enabled.get()
        misc.videoTrigger = self.var_misc_video_trigger.get().strip()
        label = self.var_misc_video_source.get().strip()
        misc.videoSource = dict(zip(self._VIDEO_SOURCE_LABELS,
                                    self._VIDEO_SOURCE_KEYS)).get(
            label, misc.videoSource or 'anime')
        misc.videoCount = self._int(self.var_misc_video_count.get(), 5)
        misc.videoCooldownSeconds = self._int(self.var_misc_video_cooldown.get(), 30)
        misc.videoTitle = self.var_misc_video_title.get().strip()
        misc.videoItemText = self.var_misc_video_item.get().strip()
        misc.videoCoolText = self.var_misc_video_cool.get().strip()
        misc.videoFailText = self.var_misc_video_fail.get().strip()
        misc.biliCookie = self.var_misc_bili_cookie.get().strip()
        sel = (self.var_misc_bili_fav.get() or '').strip()
        folder = self._bili_fav_map.get(sel) if sel else None
        if folder:
            misc.biliFavMediaId = int(folder.get('media_id') or 0)
            misc.biliFavName = str(folder.get('title') or '')
        elif sel.isdigit():
            misc.biliFavMediaId = int(sel)
            misc.biliFavName = ''
        else:                                   # 没重新读收藏夹：保留原来配的那个
            misc.biliFavMediaId = int(self._bili_fav_cur.get('media_id') or 0)
            misc.biliFavName = str(self._bili_fav_cur.get('name') or '')

        cfg.validate()
        cfg.save()

    # ------------------------------------------------------------------
    def _on_provider(self):
        prov = self.var_provider.get()
        if prov in DEFAULT_BASE_URLS and not self.var_base.get().strip():
            self.var_base.set(DEFAULT_BASE_URLS[prov])

    def _on_save(self):
        self._gather()
        self.controller.reload_ai()
        self._append('设置已保存。')

    def _on_connect(self):
        self._gather()
        self.controller.start_qq()
        self._append('正在连接 QQ 网关…')

    def _on_reconnect(self):
        self._gather()
        self.controller.restart_qq()
        self._append('正在重连 QQ 网关…')

    def _on_disconnect(self):
        self.controller.stop_qq()
        self._append('已断开。')

    def _on_launch(self):
        self._gather()
        self.controller.launch_framework()

    def _on_ai_toggle(self):
        self._gather()
        self.controller.set_ai_enabled(self.ai_on.get())

    def _on_clear_ctx(self):
        self.controller.clear_context()
        self._append('上下文已清空。')

    def _on_clear_affinity(self):
        self.controller.clear_affinity()
        self._append('好感度已清空。')

    # ------------------------------------------------------------------
    # B 站（视频推荐「我的收藏夹」来源用）
    # ------------------------------------------------------------------
    def _on_bili_folders(self):
        """读 B 站收藏夹：验证 Cookie + 把收藏夹填进下拉框。"""
        cookie = (self.var_misc_bili_cookie.get() or '').strip()
        if not cookie:
            messagebox.showinfo('AI QQ Friends',
                                '先在左边填 SESSDATA（或整条 Cookie），再点「读取收藏夹」。')
            return
        self.var_misc_bili_status.set('正在读取…')

        def work():
            from . import bilibili
            info = bilibili.login_info(cookie)
            if not info.get('ok'):
                msg = '❌ ' + str(info.get('message') or 'Cookie 无效')
                self._ui(lambda: self.var_misc_bili_status.set(msg))
                return
            res = bilibili.fav_folders(cookie)
            name = str(info.get('name') or '')

            def apply():
                if not res.get('ok'):
                    self.var_misc_bili_status.set('❌ ' + str(res.get('message') or '没读到'))
                    return
                folders = res.get('folders') or []
                self._bili_fav_map = {}
                labels = []
                for f in folders:
                    label = '%s（%s 个）' % (str(f.get('title') or ''),
                                          int(f.get('count') or 0))
                    self._bili_fav_map[label] = f
                    labels.append(label)
                self.cmb_bili_fav.configure(values=labels)
                self.var_misc_bili_status.set('✅ %s：%s 个收藏夹' % (name or '已登录', len(labels)))
                cur = int(self._bili_fav_cur.get('media_id') or 0)
                for label, f in self._bili_fav_map.items():
                    if int(f.get('media_id') or 0) == cur:
                        self.var_misc_bili_fav.set(label)
                        self._bili_fav_cur = {'media_id': cur, 'name': str(f.get('title') or '')}
                        break
                else:
                    if not (self.var_misc_bili_fav.get() or '').strip() and labels:
                        first = self._bili_fav_map[labels[0]]
                        self.var_misc_bili_fav.set(labels[0])
                        self._bili_fav_cur = {'media_id': int(first.get('media_id') or 0),
                                              'name': str(first.get('title') or '')}
                self._append(f'已读取 B 站收藏夹：{name}，共 {len(labels)} 个', 'info')

            self._ui(apply)

        threading.Thread(target=work, daemon=True).start()

    def _on_manual_send(self):
        gid = self.send_group_id.get().strip()
        text = self.send_text.get().strip()
        if not gid or not text:
            return
        if self.controller.send_manual(gid, text):
            self._append(f'手动发送 [{gid}]: {text}')
            self.send_text.set('')
        else:
            self._append('手动发送失败：QQ 引擎未连接。', 'error')

    # ------------------------------------------------------------------
    def _poll(self):
        try:
            self.controller.log_saver.maybe_roll()
        except Exception:  # noqa: BLE001
            pass
        for ev in self.controller.drain_ui():
            self._handle(ev)
        self.root.after(100, self._poll)

    def _handle(self, ev):
        kind = ev.get('kind') or ev.get('event')
        if kind == 'log':
            self._append_raw(ev.get('line') or ev.get('message') or '',
                             ev.get('level') or 'info')
        elif kind == 'status':
            st = ev.get('state')
            if st == 'connected':
                sid = ev.get('selfId') or ''
                self.controller.set_self_id(sid)
                self.status.config(text=f'QQ 已连接 {sid}'.strip(), foreground='#4fc3f7')
            elif st == 'connecting':
                self.status.config(text='QQ 连接中…', foreground='#ffb74d')
            else:
                self.status.config(text='QQ 未连接', foreground='#999999')
        elif kind == 'restricted':
            self.status.config(text='QQ 受限/离线', foreground='#ff6b6b')

    def _append_raw(self, line, tag='info'):
        """把一行（已带时间戳与格式）写进日志页。"""
        self.log.configure(state='normal')
        self.log.insert('end', str(line) + '\n', tag)
        self.log.see('end')
        self.log.configure(state='disabled')

    def _append(self, text, tag='info'):
        """GUI 自己的提示：交给 controller 统一走日志页 + .log 落盘。"""
        self.controller.notify(str(text), tag)

    # ------------------------------------------------------------------
    # 网易云会员登录（替群友解析 VIP 歌可播放直链）
    # ------------------------------------------------------------------
    def _ui(self, fn):
        try:
            self.root.after(0, fn)
        except Exception:  # noqa: BLE001
            pass

    def _on_netease_login(self):
        if getattr(self, '_netease_login_running', False):
            self._append('网易云登录已在进行中…', 'warn')
            return
        self._netease_login_running = True
        self._netease_status.set('正在获取二维码…')
        self._append('正在获取网易云登录二维码…', 'info')
        threading.Thread(target=self._netease_login_worker, daemon=True).start()

    def _show_netease_qr(self, url):
        """把登录链接画成二维码显示在界面里。"""
        self._netease_url = url
        try:
            import qrcode
            from PIL import ImageTk
            img = qrcode.make(url).resize((200, 200))
            photo = ImageTk.PhotoImage(img)
            self._netease_qr_photo = photo   # 必须保留引用
            self._netease_qr_label.configure(image=photo, text='')
        except Exception as e:  # noqa: BLE001
            self._netease_qr_photo = None
            self._netease_qr_label.configure(
                image='', text='（生成二维码失败：' + str(e) + '，请用下面按钮打开链接）')

    def _on_netease_open(self):
        if not self._netease_url:
            self._append('还没有登录链接，先点「扫码登录」。', 'warn')
            return
        try:
            webbrowser.open(self._netease_url)
        except Exception as e:  # noqa: BLE001
            self._append('打开浏览器失败：' + str(e), 'warn')

    def _on_netease_copy(self):
        if not self._netease_url:
            self._append('还没有登录链接，先点「扫码登录」。', 'warn')
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self._netease_url)
            self._append('登录链接已复制到剪贴板。', 'info')
        except Exception as e:  # noqa: BLE001
            self._append('复制失败：' + str(e), 'warn')

    def _netease_login_worker(self):
        qr = None
        try:
            from . import netease
            qr = netease.QrLogin()
            unikey = qr.start()
            if not unikey:
                self._ui(lambda: self._netease_status.set('获取二维码失败（网易云接口无响应）'))
                return
            url = qr.login_url()
            self._ui(lambda: self._show_netease_qr(url))
            self._ui(lambda: self._netease_status.set('请用【网易云音乐 App】扫描上方二维码，并在手机上确认'))
            self._ui(lambda: self._append('网易云扫码登录：二维码已显示在界面里。', 'info'))
            scanned = False
            for _ in range(120):
                time.sleep(2)
                code, cookie = qr.poll()
                if code == 800:
                    self._ui(lambda: self._netease_status.set('二维码已过期，请重新点「扫码登录」'))
                    return
                if code == 802:
                    if not scanned:
                        scanned = True
                        self._ui(lambda: self._append('已扫码，请在手机上点「确认登录」。', 'info'))
                    self._ui(lambda: self._netease_status.set('已扫码，请在手机上点「确认登录」…'))
                elif code == 803:
                    if not cookie:
                        self._ui(lambda: self._netease_status.set('登录成功但没拿到 Cookie'))
                        self._ui(lambda: self._append('网易云 803 但没有 MUSIC_U，请反馈。', 'warn'))
                        return
                    self._ui(lambda: self._apply_netease_cookie(cookie))
                    return
            self._ui(lambda: self._netease_status.set('登录超时，请重试'))
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            self._ui(lambda: self._netease_status.set('登录出错：' + msg))
        finally:
            if qr is not None:
                qr.close()
            self._netease_login_running = False

    def _apply_netease_cookie(self, cookie):
        """把扫码拿到的 Cookie 填进输入框并立即保存到 config.json。"""
        try:
            self.var_song_netease_cookie.set(cookie)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.controller.config.song.neteaseCookie = cookie
            self.controller.config.save()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._netease_status.set('登录成功 ✅ 已保存会员 Cookie：' + (cookie[:24] + '…'))
        except Exception:  # noqa: BLE001
            pass
        self._append('网易云登录成功，已保存会员 Cookie；现在可以替群友播放 VIP 歌了。', 'info')

    def _on_netease_verify(self):
        """验证输入框里的 Cookie：显示账号昵称，并实测一首会员歌能不能播放。"""
        if getattr(self, '_netease_verify_running', False):
            self._append('正在验证中，请稍候…', 'warn')
            return
        cookie = (self.var_song_netease_cookie.get() or '').strip()
        if not cookie:
            self._append('请先把网易云 Cookie 粘进输入框（含 MUSIC_U=…），再点「验证登录」。', 'warn')
            return
        self._netease_verify_running = True
        self._netease_status.set('正在验证 Cookie…')
        self._append('正在验证网易云 Cookie…', 'info')
        threading.Thread(target=self._netease_verify_worker, args=(cookie,), daemon=True).start()

    def _netease_verify_worker(self, cookie):
        res = None
        try:
            from . import netease
            res = netease.check_login(cookie)
        except Exception as e:  # noqa: BLE001
            res = {'ok': False, 'message': '验证出错：' + str(e)}
        msg = (res or {}).get('message') or '验证失败'
        ok = bool((res or {}).get('ok'))

        def done():
            self._netease_verify_running = False
            try:
                self._netease_status.set(msg)
            except Exception:  # noqa: BLE001
                pass
            self._append(msg, 'info' if ok else 'warn')
            if ok:
                # 验证通过就顺手存进 config.json
                try:
                    self.controller.config.song.neteaseCookie = cookie
                    self.controller.config.save()
                except Exception:  # noqa: BLE001
                    pass
        self._ui(done)

    def _on_close(self):
        try:
            self._gather()
            self.controller.shutdown()
        finally:
            self.root.destroy()

    @staticmethod
    def _int(s, default):
        try:
            return int(str(s).strip())
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _float(s, default):
        try:
            return float(str(s).strip())
        except (TypeError, ValueError):
            return default


def re_split(text):
    import re
    return [x for x in re.split(r'[,，;\s]+', text or '') if x]


def run():
    root = tk.Tk()
    try:
        dpi = root.winfo_fpixels('1i')
        if dpi and dpi > 0:
            root.tk.call('tk', 'scaling', dpi / 72.0)
    except Exception:  # noqa: BLE001
        pass
    App(root)
    root.mainloop()
