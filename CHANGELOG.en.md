# Changelog

[简体中文](CHANGELOG.md) | **English**

This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added · NetEase member login (song direct links)

- **Interaction → Song request** gains a **NetEase login (member)** box: scan-to-login (the QR code is drawn right in the UI) or paste a cookie and hit verify; on success it is written to and saved as `song.neteaseCookie`.
- Same scheme as the parent project: **search is anonymous** (a logged-in cookie makes NetEase return empty results), and the member `MUSIC_U` cookie is only used to **resolve the playable direct link** — so VIP songs also post a fully playable `custom` card.
- Falls back to a `163` card when not logged in / no direct link is available; "verify" shows the account nickname and probes a member-only song.

### Added · Video recommendations

- The **Misc** tab adds **video recommendations**: a member sends "trigger + 视频推荐" (default `[视频推荐]`) to post a batch of Bilibili videos in the group.
- Five sources (anime ranking / Bilibili home feed / home popular / site ranking / my favorites). The cooldown is **shared across all users** and asking again after it expires fetches a **fresh batch** (recent ids are remembered per source, so repeated requests keep giving new items).
- For the "my favorites" source, **paste the whole Bilibili cookie directly** (or just the `SESSDATA` value), then click "read favorites" to verify and pick a folder; items are sampled by randomly paging the folder.
- The home-feed endpoint warms up by visiting the homepage once to obtain `buvid3` (otherwise `-412 request was banned`); its `ps` may only be 12.

### Added · Daily check-in

- A member sends the "check-in trigger" (default `[签到]`) once per day to gain extra affinity (default +5).
- The check-in bonus **ignores the per-day cap** and records a consecutive-day streak.
- Configurable: on/off, trigger word, amount per check-in.

### Added · Chat logs on disk

- The log page now uses one format: incoming `[date time][group：id][user QQ][user name]：text`, replies `[date time]Replay[group id][bot] -> text`, system `[date time][系统] text`.
- On close, every chat / reply / connection-system line is saved to `logs/[date][group id][group name][save count].log` (connection lines go to `logs/[date][000000][系统][save count].log`).
- Closing the program several times in one day bumps the save count (1, 2, 3 …) without overwriting history; a day rollover while running also saves once.

### Fixed

- **Group messages are logged**: incoming group messages now reach the log page and the saved files (previously there was no branch for them).
- **NetEase song requests**: uses the official endpoint plus the member cookie to resolve a playable direct link, dropping the now-broken third-party fallback (whose `custom` links often failed to play).
- **Engine exiting unexpectedly**: a crashed / killed child process now notifies the UI and flips it to "not connected" instead of keeping the connected state.
- **Reverse mode with multiple connections**: the OneBot reverse listener now sends commands / replies only to the **newest** connection, avoiding duplicates.
- **"@ the sender in replies"** now depends only on its own toggle; it no longer also requires "reply when @-mentioned".
- **A false "restricted" verdict no longer wedges the bot**: consecutive online-check failures are now advisory — it keeps retrying at a low frequency and resumes automatically once back online (previously it permanently stopped auto-reconnect *and* the online check).
- **Affinity display** uses the configured maximum instead of a hard-coded 100 (the query progress bar scales proportionally).
- **Failed LLM requests are no longer hammered**: the cooldown is stamped when the request starts, so an erroring endpoint is not called again for every matching message.
- **The own-account id is fetched right after connecting**, so @-mention detection no longer waits up to ~30s for the first heartbeat.
- **API URL joining** no longer duplicates a path when `baseUrl` already ends in `/v1` or is a full endpoint.
- **Blacklist**: plain QQ numbers (strings) hand-written in `config.json` are no longer silently dropped.
- **Connect tab**: a detected token no longer overwrites a token you typed; **manual send** now reports failure when the engine is not connected.
- **Song requests**: the empty-keyword hint is now also rate-limited to avoid spam.

## [0.1.1] - 2026-10-16

### Added · In-group song requests

- A member sends "trigger word + song name" (default `[点歌] 起风了`) to request a song; the bot searches and posts a **music card**.
- Search order: QQ Music → NetEase Cloud. If neither works it automatically falls back to a publicly streamable alternate source (a `custom` card).
- A message consumed by a song request is **not** handed to the chat AI, so the model does not "answer" the command as well.
- Configurable: on/off, trigger word, platform (`auto`/`qq`/`163`), cooldown seconds, search timeout seconds.

### Added · Affinity

- Every member has a 0–100 affinity score with the bot, which grows when the bot replies to them (with a configurable daily cap).
- The score is injected into the persona prompt so the bot is warmer to people it knows and more polite to strangers (can be turned off).
- Members can send the "query trigger" (default `[好感度]`) to see their score and title: Stranger / Acquainted / Friend / Good friend / Close friend / Heartfelt.
- Optionally persisted to `affinity.json` (already in `.gitignore`), with a one-click reset.

### Changed

- A new **Interactions** tab next to Connect / AI Config / Log, where song requests and affinity are configured.
- Song requests and affinity have their own switches and are **not** affected by the "AI group member switch" at the top.
- Config loading/validation in `config.py` now handles nested dataclasses generically, so an older `config.json` (without `song` / `affinity`) upgrades seamlessly.

### Engineering

- New modules: `aafm_qq/song.py`, `aafm_qq/affinity.py`, `aafm_qq/interactions.py`.
- `bot_engine.js` gains a `sendGroupMusic` command supporting the `qq` / `163` / `custom` music cards, with CQ escaping.

## [0.1.0]

- First release: AI group member (trigger-word replies, @-mention replies, probability replies, context memory, output filtering) and OneBot 11 connectivity (SnowLuma / NapCat).
