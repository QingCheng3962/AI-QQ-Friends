# Changelog

[简体中文](CHANGELOG.md) | **English**

This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

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
