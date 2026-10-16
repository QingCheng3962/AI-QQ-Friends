# Changelog

[简体中文](CHANGELOG.md) | **English**

This project follows [Semantic Versioning](https://semver.org/).

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
