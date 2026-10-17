"""tkinter GUI for AI QQ Friends: 连接 / AI 配置 / 日志."""
from __future__ import annotations

import time
import tkinter as tk
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
        rule.columnconfigure(1, weight=1)

        ctx = ttk.LabelFrame(sc.inner, text='上下文与限制', padding=8)
        ctx.pack(fill='x', pady=(8, 0))
        self.var_ctx_enabled = tk.BooleanVar(value=True)
        self.var_ctx_len = tk.StringVar()
        self.var_max_msgs = tk.StringVar()
        self.var_max_chars = tk.StringVar()
        self.var_cooldown = tk.StringVar()
        ttk.Checkbutton(ctx, text='启用上下文', variable=self.var_ctx_enabled).grid(
            row=0, column=0, sticky='w', padx=4, pady=2)
        self._row(ctx, 0, '上下文长度', self.var_ctx_len, col=2, width=6)
        self._row(ctx, 1, '最大回复条数', self.var_max_msgs, width=6)
        self._row(ctx, 2, '单条最大字数', self.var_max_chars, width=6)
        self._row(ctx, 3, '冷却秒', self.var_cooldown, width=6)
        ctx.columnconfigure(1, weight=1)

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
        ttk.Label(sd, text='auto=先 QQ 音乐再网易云；两者都不可用时回退到可直链播放的备用音源。',
                  foreground='#888888', wraplength=760, justify='left').grid(
            row=4, column=0, columnspan=3, sticky='w', pady=(4, 0))
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

    def _build_log_tab(self):
        tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab, text=' 日志 ')
        self.log = tk.Text(tab, height=24, wrap='word', state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True)
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
        self.var_ctx_enabled.set(bool(ai.contextEnabled))
        self.var_ctx_len.set(str(ai.contextLength))
        self.var_max_msgs.set(str(ai.maxReplyMessages))
        self.var_max_chars.set(str(ai.maxCharsPerMessage))
        self.var_cooldown.set(str(ai.cooldownSeconds))
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

        aff = cfg.affinity
        self.var_aff_enabled.set(bool(aff.enabled))
        self.var_aff_trigger.set(aff.queryTrigger or '')
        self.var_aff_start.set(str(aff.start))
        self.var_aff_max.set(str(aff.maximum))
        self.var_aff_gain.set(str(aff.gainPerChat))
        self.var_aff_cap.set(str(aff.dailyCap))
        self.var_aff_hint.set(bool(aff.promptHint))
        self.var_aff_persist.set(bool(aff.persist))

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
        ai.contextEnabled = self.var_ctx_enabled.get()
        ai.contextLength = self._int(self.var_ctx_len.get(), 20)
        ai.maxReplyMessages = self._int(self.var_max_msgs.get(), 2)
        ai.maxCharsPerMessage = self._int(self.var_max_chars.get(), 120)
        ai.cooldownSeconds = self._int(self.var_cooldown.get(), 5)
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

        aff = cfg.affinity
        aff.enabled = self.var_aff_enabled.get()
        aff.queryTrigger = self.var_aff_trigger.get().strip()
        aff.start = self._int(self.var_aff_start.get(), 20)
        aff.maximum = self._int(self.var_aff_max.get(), 100)
        aff.gainPerChat = self._int(self.var_aff_gain.get(), 2)
        aff.dailyCap = self._int(self.var_aff_cap.get(), 20)
        aff.promptHint = self.var_aff_hint.get()
        aff.persist = self.var_aff_persist.get()

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
        for ev in self.controller.drain_ui():
            self._handle(ev)
        self.root.after(100, self._poll)

    def _handle(self, ev):
        t = ev.get('event') or ev.get('kind')
        if t in ('log',):
            self._append(ev.get('message', ''), ev.get('level', 'info'))
        elif t == 'error':
            self._append(ev.get('message', ''), 'error')
        elif t == 'status':
            st = ev.get('state')
            if st == 'connected':
                sid = ev.get('selfId') or ''
                self.controller.set_self_id(sid)
                self.status.config(text=f'QQ 已连接 {sid}'.strip(), foreground='#4fc3f7')
            elif st == 'connecting':
                self.status.config(text='QQ 连接中…', foreground='#ffb74d')
            else:
                self.status.config(text='QQ 未连接', foreground='#999999')
        elif t == 'groups':
            names = ev.get('groups') or []
            if names:
                self._append('群列表: ' + ', '.join(f"{g['name']}({g['id']})" for g in names), 'info')
        elif t == 'restricted':
            self.status.config(text='QQ 受限/离线', foreground='#ff6b6b')
        elif t == 'pong':
            pass

    def _append(self, text, tag='info'):
        stamp = time.strftime('[%H:%M:%S] ')
        self.log.configure(state='normal')
        self.log.insert('end', stamp + str(text) + '\n', tag)
        self.log.see('end')
        self.log.configure(state='disabled')

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
