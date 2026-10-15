# AI QQ Friends

把大模型接进 QQ 群，让它成为一个**会聊天的群友**：被 @ 或命中触发词时，像真人网友一样接话、玩梗、回答问题。

- 一个 Python tkinter GUI（**连接 / AI 配置 / 日志** 三个标签页），双击即可运行、可视化调参。
- 通过 **OneBot 11** 接入 QQ，支持 **SnowLuma / NapCat**，可一键启动。
- 大模型：**OpenAI 兼容**（OpenAI、DeepSeek、Moonshot、Ollama…）与 **Anthropic**。

> 本项目仅供学习与个人使用。请遵守 QQ 用户协议与相关法律法规，使用后果自负（详见文末免责声明）。

## 功能特性

- **接入 QQ**
  - OneBot 11 正向 WebSocket（默认 `ws://127.0.0.1:3001`）/ 反向监听两种模式。
  - 框架可切换：**SnowLuma**（默认）/ **NapCat**，各自独立保存「启动路径 / 地址 / Token / 模式 / 端口」。
  - **自动发现正在运行的框架目录并验证 Token**：换机器、换账号都不用你手填路径或 Token（连接时用真实 WebSocket 握手逐个验证，选中真正能连上的）。
  - 可选「群白名单」（留空=全部群）与「忽略群」。
- **AI 群友**
  - 人设提示词（system prompt）自由编写。
  - 回复规则：**被 @ 回复**、**触发词回复**（`[名字]` 按字面量、其余按正则）、可选「每条都回复（按概率）」。
  - **上下文记忆**（记住群里最近若干条）、回复时 **@ 对方**、**冷却时间**、**黑名单**。
  - 单条最大字数、最大回复条数限制。
- **界面对话**：日志页实时显示连接状态、群消息、AI 回复，并可**手动发送**测试。

## 环境要求

- Python 3.9+（需 tkinter；Windows 官方 Python 自带）
- Node.js 14+（推荐 18+）
- 可联网（访问大模型 API、QQ 服务）

## 安装

```bash
pip install -r requirements.txt
npm install
```

## 快速开始

1. **准备 QQ 接入**（二选一）：
   - **SnowLuma**（推荐）：从 [SnowLuma Releases](https://github.com/SnowLuma/SnowLuma/releases) 下载解压（Windows 完整版自带 Node），运行 `launcher.bat`，在它的 **WebUI** 里登录 QQ，并开启一个 **正向 WebSocket 服务**（端口默认 `3001`）。
   - **NapCat**：运行 NapCat，在其网络配置里开正向 WebSocket（`127.0.0.1:3001`）。
2. **启动本程序**：
   ```bash
   python main.py
   ```
3. **连接页**：
   - 选「启动框架」SnowLuma / NapCat；
     - 若框架已在上一步自行启动，**「启动路径」可留空**，程序会自动发现它并读取 Token；
     - 想让它帮你拉起框架，就填框架所在目录（含 `launcher.bat` / `index.mjs`）。
   - 「正向地址」默认 `ws://127.0.0.1:3001`；「群白名单」留空=处理全部群。
   - 点「**连接**」，状态显示「QQ 已连接」（会顺便打印识别到的账号与群列表）。
4. **AI 配置页**：填「提供方 / API 地址 / API 密钥 / 模型」，写下**人设提示词**，按需设置触发规则与上下文。
5. 顶部勾选「**AI 群友开关**」。此后群里被 @ 或命中触发词，机器人就会自动回话。

## 接入说明（OneBot）

- 默认用**正向模式**：本程序作为 WS 客户端，连到 SnowLuma/NapCat 的 OneBot 正向 WebSocket（`ws://127.0.0.1:3001`）。
- **SnowLuma 的 Token 会自动读取**：程序扫描 `<框架目录>/config/onebot_*.json` 里的候选端口/Token，并**用真实 WebSocket 握手逐个验证**，选用真正能连上的那个（SnowLuma 重启后文件里的 Token 可能失效，会 401，所以不能只读文件）。
- **多账号**：优先「上次登录」，否则取最近修改的配置文件（即当前运行的账号）。
- **反向模式**：选 `reverse`，在框架侧配置「WebSocket 客户端」连到本程序（如 `ws://127.0.0.1:3002/onebot/v11/ws`）。

## AI 配置说明

| 项 | 说明 |
| --- | --- |
| 提供方 / API 地址 / 密钥 / 模型 | OpenAI 兼容端点或 Anthropic。填了「提供方」会自动补默认地址。 |
| 人设提示词 | 决定说话风格；建议写“群聊口语、简短、不要暴露是 AI”。 |
| 被 @ 时回复 | 群里 @ 机器人即回复。 |
| 触发词回复 | 逗号分隔；`[名字]` 按**字面量**匹配，其余按**正则**匹配。 |
| 每条都回复 + 概率 | 打开后按概率对普通消息也接话（水群）。 |
| 回复时 @ 对方 | 回复前带上 `@昵称`。 |
| 上下文 | 记住每个群最近 N 条消息，让回复更连贯。 |
| 最大回复条数 / 单条最大字数 | 限制每次回复的条数与长度。 |
| 冷却秒 | 同一群两次回复的最小间隔。 |
| 黑名单 | 每行一个 QQ 号，这些人的消息不回复。 |

## 目录结构

```
AI QQ Friends/
├─ main.py                # 入口（GUI）
├─ aafm_qq/
│  ├─ gui.py              # tkinter GUI：连接 / AI 配置 / 日志
│  ├─ controller.py       # 引擎 + AI + 配置；框架自动发现与 Token 握手探测
│  ├─ ai_bot.py           # “群友”大脑：判定回复、上下文、调用大模型、切分发送
│  ├─ engine.py           # 管理 Node 端 OneBot 引擎子进程
│  ├─ llm.py              # OpenAI 兼容 / Anthropic 客户端
│  ├─ procutil.py         # 进程枚举（自动发现框架目录）
│  └─ config.py           # 配置模型（config.json）
├─ bot_engine.js          # Node 端 OneBot 11 引擎
├─ package.json / requirements.txt
├─ config.example.json    # 配置示例（复制为 config.json 后填写）
└─ config.json            # 运行时配置（gitignore，本地生成，含密钥勿提交）
```

## 配置示例（config.example.json）

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
    "baseUrl": "https://api.deepseek.com/v1", "apiKey": "sk-你的密钥",
    "model": "deepseek-chat", "temperature": 0.8, "maxTokens": 512,
    "systemPrompt": "你是 QQ 群里的一个普通群友……",
    "mentionReply": true, "triggerEnabled": true, "triggerRegex": "[小助手]"
  }
}
```

> 正常情况下不必手动改 `config.json`，在界面里设置即可；`config.json` 已加入 `.gitignore`，请勿提交（含 API 密钥）。

## 常见问题

- **连不上 / 401**：确认 SnowLuma/NapCat 已启动并开了正向 WS（默认 3001）；本程序会自动发现目录并验证 Token。若框架不在运行，检测不到属正常。
- **群里没反应**：确认顶部「AI 群友开关」已勾选、「AI 配置」已填对并有密钥；再确认消息命中了规则（被 @ / 触发词）。日志页会显示收到的群消息。
- **回复被判违规/风控**：把冷却调大、减少“每条都回复”的概率，或改用人设更克制。

## 免责声明

1. 本项目仅供学习、研究与个人娱乐，作者不对任何使用后果负责。
2. 登录 QQ、接入第三方服务属于个人行为，请遵守 QQ 用户协议及相关法律法规；请勿用于任何违规或违法用途。
3. 本项目会保存登录凭据与 API 密钥到本地 `config.json`，请妥善保管；因泄露、误用导致的损失由使用者自行承担。
4. 调用大模型 API 会产生费用，由使用者的 API 账户承担。
5. 本项目按“现状”提供，不提供任何明示或暗示的担保。

## License

[MIT](LICENSE)
