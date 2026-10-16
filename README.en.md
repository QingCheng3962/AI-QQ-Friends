# AI QQ Friends

[简体中文](README.md) | **English**

> Current version **v0.1.1** · See [CHANGELOG.en.md](CHANGELOG.en.md) for the changelog

Plug a large language model into a QQ group and let it become a **group member that actually chats**: when a message **starts with** the trigger word (default `[AI]`), it replies like a real netizen — bantering, keeping up with memes, answering questions — with **prompt-injection protection + language filtering** on the output.

- A Python tkinter GUI (**Connect / AI Config / Interactions / Log** — four tabs). Double-click to run, tune everything visually.
- Connects to QQ over **OneBot 11**, supports **SnowLuma / NapCat**, and can launch them for you with one click.
- LLMs: **OpenAI-compatible** (OpenAI, DeepSeek, Moonshot, Ollama, …) and **Anthropic**.
- In-group fun: **song requests** (`[点歌] <song>` posts a music card) and **affinity** (grows as people chat and colours the AI's tone).

> This project is for learning and personal use only. Please comply with the QQ User Agreement and applicable laws; you are responsible for the consequences (see the disclaimer at the end).

## Features

- **QQ connectivity**
  - OneBot 11 forward WebSocket (default `ws://127.0.0.1:3001`) or reverse listening — both modes supported.
  - Switchable framework: **SnowLuma** (default) / **NapCat**, each keeping its own launcher path, address, token, mode and port.
  - **Auto-discovers the running framework directory and verifies the token**: no need to hand-copy paths or tokens when you change machines or accounts (each candidate is verified with a real WebSocket handshake, and the one that truly connects wins).
  - Optional group whitelist (empty = all groups) and ignore list.
- **AI group member**
  - Freely written persona / system prompt.
  - Reply rules: **trigger-word replies** (the trigger word is **a plain string you type**, default `[AI]`; a message must **start with** it — `[AI]hello` triggers, `hello[AI]` does not; comma-separated words all count), an optional **reply when @-mentioned**, an optional **reply to everything (by probability)**, plus an optional **advanced trigger regex**.
  - **Context memory** (remembers the last N messages per group), **@-mention the sender** on reply, **cooldown**, **blacklist**.
  - Max characters per message and max number of reply messages.
  - **Output filtering**: if a reply **contains your trigger word** (e.g. `[AI]`) it is stripped out — preventing prompt injection by group members and self-triggering; a reply that hits a **blocked word** (defaults include “纯净输出” plus common profanity) is **dropped entirely**. Trigger words, blocked words and toggles live under “AI Config → Reply Rules / Output Filter”.
- **In-group interactions**
  - **Song request**: a member sends “trigger word + song name” (default `[点歌] 起风了`) and the bot searches and posts a **music card**. The order is QQ Music → NetEase Cloud; if neither works it falls back to a directly playable alternate source (a `custom` card). A message consumed by a song request is **not** handed to the chat AI.
  - **Affinity**: every member has a 0–100 score with the bot that **grows when they chat with it** (with a daily cap). It is written into the persona prompt so the tone feels more natural (the closer, the warmer); members can send the “query trigger” (default `[好感度]`) to see their score and title. Optionally persisted to `affinity.json`.
- **In-app conversation**: the Log tab shows connection status, group messages and AI replies in real time, and can **send test messages manually**.

## Requirements

- Python 3.9+ (needs tkinter; the official Windows Python ships it)
- Node.js 14+ (18+ recommended)
- Internet access (for the LLM API and QQ services)

## Install

```bash
pip install -r requirements.txt
npm install
```

## Quick Start

1. **Get QQ connectivity ready** (pick one):
   - **SnowLuma** (recommended): download and extract from [SnowLuma Releases](https://github.com/SnowLuma/SnowLuma/releases) (the Windows full package bundles Node), run `launcher.bat`, log in to QQ in its **WebUI**, and enable a **forward WebSocket service** (default port `3001`).
   - **NapCat**: run NapCat and enable forward WebSocket in its network settings (`127.0.0.1:3001`).
2. **Start this program**:
   ```bash
   python main.py
   ```
3. **Connect tab**:
   - Choose the framework (SnowLuma / NapCat);
     - If you already started the framework yourself, **the launcher path may be left empty** — the program will discover it and read the token automatically;
     - If you want it to launch the framework for you, fill in the framework directory (containing `launcher.bat` / `index.mjs`).
   - “Forward address” defaults to `ws://127.0.0.1:3001`; leave “Group whitelist” empty to handle every group.
   - Click **Connect**; the status shows “QQ connected” (and it prints the detected account and group list).
4. **AI Config tab**: fill in provider / API base URL / API key / model, write your **persona prompt**, and set the trigger rules and context as needed.
5. Tick **AI group member switch** at the top. From then on, any message in the group that **starts with** `[AI]` (e.g. `[AI]hello`) makes the bot reply.

> Song requests and affinity have their own switches on the **Interactions** tab and are **not** affected by the “AI group member switch”: even with chat AI off, `[点歌] <song>` and `[好感度]` still work.

## OneBot Integration Notes

- The default is **forward mode**: this program is the WS client connecting to SnowLuma/NapCat's OneBot forward WebSocket (`ws://127.0.0.1:3001`).
- **SnowLuma's token is read automatically**: the program scans `<framework dir>/config/onebot_*.json` for candidate ports/tokens and **verifies each with a real WebSocket handshake**, picking the one that actually connects (after a SnowLuma restart the token in the file may be stale and return 401, so reading the file alone is not enough).
- **Multiple accounts**: “last login” wins; otherwise the most recently modified config file (i.e. the currently running account).
- **Reverse mode**: choose `reverse` and configure a “WebSocket client” on the framework side pointing at this program (e.g. `ws://127.0.0.1:3002/onebot/v11/ws`).

## AI Config Reference

| Item | Description |
| --- | --- |
| Provider / API base URL / key / model | An OpenAI-compatible endpoint or Anthropic. Picking a provider auto-fills the default base URL. |
| Persona prompt | Defines the speaking style; “casual group chat, short, don't reveal you're an AI” works well. |
| Reply when @-mentioned | Reply whenever the bot is @-mentioned in the group (default **off**; only the trigger word counts, turn this on when needed). |
| Trigger-word replies | The **trigger word is a user-typed string** (default `[AI]`, comma-separated for several); a message must **start with it** (`[AI]hello` triggers, `hello[AI]` does not). |
| Trigger regex (optional) | Advanced: extra regexes; a match triggers a reply. May be left empty. |
| Reply to everything + probability | When on, it also chimes in on ordinary messages by probability (idle chatting). |
| @-mention the sender on reply | Prefix the reply with `@nickname`. |
| Context | Remember the last N messages per group for more coherent replies. |
| Max reply messages / max chars per message | Limit how many messages and how long each reply can be. |
| Cooldown seconds | Minimum interval between two replies in the same group. |
| Blacklist | One QQ number per line; their messages are ignored. |
| Output filter · strip trigger | Remove `[AI]`-style trigger words from replies so they cannot be injected as fresh prompts / re-trigger the bot. |
| Output filter · blocked words | One word per line; if a reply contains any of them (defaults include “纯净输出” and common profanity) it is **not sent at all** and is logged as “blocked”. |

### Interactions Reference (Interactions tab)

| Item | Description |
| --- | --- |
| Enable song requests | Whether to answer song requests; when off, `[点歌] …` is treated as an ordinary message and handed to the chat AI. |
| Trigger word (must be at the start) | Default `[点歌]`, following the same rule as the AI trigger: `[点歌] 起风了` triggers, `我想点歌` does not. |
| Platform | `auto` = QQ Music first, then NetEase; `qq` = QQ Music only; `163` = NetEase only. |
| Cooldown seconds | Minimum interval between two song requests in the same group, to prevent spam. |
| Search timeout (seconds) | Timeout for the search API; on failure it logs the reason and replies “not found”. |
| Enable affinity | On/off switch. |
| Query trigger | Default `[好感度]`; members send it to see their score and title (Stranger / Acquainted / Friend / Good friend / Close friend / Heartfelt). |
| Start / maximum | Initial value for a new member (default 20) and the score cap (default 100). |
| Gain per chat | How much the score grows each time the bot replies to that member (default 2). |
| Daily cap per member | Maximum gain per member per day (default 20; 0 = unlimited). |
| Affect the persona prompt | Write affinity into the system prompt so the tone follows how familiar they are; when off it is only recorded and does not affect speech. |
| Save to affinity.json | Whether to persist to disk (when off, everything resets on restart). |
| Clear affinity | Wipe all scores in one click. |

## Directory Structure

```
AI QQ Friends/
├─ main.py                # Entry point (GUI)
├─ aafm_qq/
│  ├─ gui.py              # tkinter GUI: Connect / AI Config / Interactions / Log
│  ├─ controller.py       # Engine + AI + config; framework discovery and token handshake probing
│  ├─ ai_bot.py           # The "group member" brain: decide to reply, context, call the LLM, split and send
│  ├─ interactions.py     # In-group interaction dispatch: song requests / affinity (consumed before the AI)
│  ├─ song.py             # Song requests: QQ Music / NetEase search + alternate source
│  ├─ affinity.py         # Affinity storage and prompt injection
│  ├─ engine.py           # Manages the Node-side OneBot engine subprocess
│  ├─ llm.py              # OpenAI-compatible / Anthropic client
│  ├─ procutil.py         # Process enumeration (auto-discover the framework directory)
│  └─ config.py           # Config model (config.json)
├─ bot_engine.js          # Node-side OneBot 11 engine
├─ package.json / requirements.txt
├─ config.example.json    # Example config (copy to config.json and fill in)
├─ config.json            # Runtime config (gitignored, generated locally, contains secrets — do not commit)
└─ affinity.json          # Affinity data (gitignored, created automatically at runtime)
```

## Example Config (config.example.json)

```json
{
  "framework": "snowluma",
  "snowluma": { "launcherPath": "", "mode": "forward", "url": "ws://127.0.0.1:3001",
                "accessToken": "", "listenHost": "0.0.0.0", "listenPort": 3002 },
  "napcat": { "launcherPath": "", "mode": "forward", "url": "ws://127.0.0.1:3001",
              "accessToken": "", "listenHost": "0.0.0.0", "listenPort": 3002 },
  "groups": [], "ignoreGroups": [],
  "ai": {
    "enabled": true, "provider": "openai",
    "baseUrl": "https://api.deepseek.com/v1", "apiKey": "sk-your-key",
    "model": "deepseek-chat", "temperature": 0.8, "maxTokens": 512,
    "systemPrompt": "You are an ordinary member of a QQ group …",
    "mentionReply": false, "triggerEnabled": true, "triggerWord": "[AI]", "triggerRegex": "",
    "stripTrigger": true, "blockedWords": ["纯净输出", "傻逼", "fuck"]
  },
  "song": {
    "enabled": true, "trigger": "[点歌]", "platform": "auto",
    "cooldownSeconds": 4, "timeoutSeconds": 8
  },
  "affinity": {
    "enabled": true, "start": 20, "maximum": 100, "gainPerChat": 2, "dailyCap": 20,
    "queryTrigger": "[好感度]", "promptHint": true, "persist": true
  }
}
```

> Normally you don't need to edit `config.json` by hand — set everything in the GUI. `config.json` is in `.gitignore`; do not commit it (it contains your API key).

## FAQ

- **Can't connect / 401**: make sure SnowLuma/NapCat is running with forward WS enabled (default 3001); the program discovers the directory and verifies the token automatically. If the framework isn't running, not detecting it is expected.
- **No reaction in the group**: check that the “AI group member switch” is ticked and that the AI Config is filled in with a valid key; then check the message matches a rule (**starts with `[AI]`**, or “reply when @-mentioned” is on). The Log tab shows incoming group messages.
- **The bot ignores certain messages**: they may have hit an “output filter · blocked word” and been dropped; the log shows a “blocked” entry. Adjust the word list under “AI Config → Output Filter”.
- **Replies flagged or rate-limited**: raise the cooldown, lower the “reply to everything” probability, or use a more restrained persona.
- **Song requests do nothing**: make sure “Enable song requests” is ticked on the Interactions tab and the message **starts with `[点歌]`** (e.g. `[点歌] 起风了`). The log shows “点歌: <keyword>”.
- **Song request says “not found”**: usually the search API is temporarily unavailable or the song name is too obscure; try another keyword. The log states which platform failed.
- **A card arrives but won't open / play**: it came from the alternate source (a `custom` card). QQ Music / NetEase cards depend on your framework and client; try another `platform`, or just use the link.
- **Affinity is the same for everyone / doesn't grow**: affinity only grows when the bot **actually replies** to someone and is bounded by the “daily cap per member”. If no trigger word matches, nothing grows.

## Disclaimer

1. This project is for learning, research and personal entertainment only; the author accepts no responsibility for any consequences of its use.
2. Logging in to QQ and connecting to third-party services are personal actions. Please comply with the QQ User Agreement and applicable laws, and never use this for anything illegal or against the rules.
3. This project saves login credentials and API keys to a local `config.json`; keep it safe. Any loss caused by leakage or misuse is borne by the user.
4. Calling LLM APIs costs money, billed to your own API account.
5. This project is provided “as is”, without warranty of any kind, express or implied.

## License

[MIT](LICENSE)
