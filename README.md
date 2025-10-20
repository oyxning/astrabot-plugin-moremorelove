# MoreMoreLove

⚠️ 本插件包含 R18 取向的恋爱与情趣内容，请在遵守所在地法律法规及平台规范的前提下酌情安装与使用。

## 插件简介

MoreMoreLove 是一款面向 AstrBot 的 AI Galgame 插件。它提供恋恋（可自定义名字）作为核心角色，支持手动开启/关闭的 Gal 模式、动态好感度系统、可配置的情趣系统，以及利用官方 t2i 服务生成的状态卡片，帮助你在工作与娱乐之间自由切换。

## 核心特性

- `galmenu`：展示基础操作与 AI 行动菜单。
- `galstart` / `galexit`：在工作模式与 Gal 模式之间无缝切换。
- 好感度系统：正确/错误的行为都会影响女主对你的好感，达到 200 后可（自愿）解锁情趣系统。
- `galact`：自定义行动，由 AI 即时生成剧情、调整好感度。
- `galintimacy`：在好感满值且配置允许时触发语言色情互动。
- `galstatus`：使用官方 t2i 输出角色状态卡片（失败时自动降级为文本）。
- 完整的配置项与数据持久化，支持多次会话间延续剧情。

## 指令一览

| 指令 | 说明 |
| --- | --- |
| `galmenu` | 查看菜单和玩法提示 |
| `galstart` / `galexit` | 开启或退出 Gal 模式 |
| `galstatus` | 查看当前状态（优先尝试 t2i 卡片） |
| `galreset` | 重置当前会话的恋爱进度 |
| `galpark` / `galcinema` | 预设的恋爱行动示例 |
| `galact <行动>` | 自定义行动（如 `galact 准备烛光晚餐`） |
| `galintimacy` | 在条件满足且显式开启后执行情趣互动 |

所有互动默认使用简体中文输出，必要时可通过 `_conf_schema.json` 配置自定义人设。

## 可配置项

| 配置键 | 说明 |
| --- | --- |
| `player_name` | 玩家称呼，留空则自动沿用消息平台昵称 |
| `heroine_name` | 女主角显示名称 |
| `custom_character_prompt` | 追加的人设/背景设定（可选） |
| `enable_explicit_mode` | 是否允许在好感满值后触发语言色情篇章，默认关闭 |
| `status_card_use_t2i` | 是否使用 t2i 服务生成状态卡片，默认开启 |

修改配置后请通过 AstrBot 后台重载插件或重启 AstrBot 以确保生效。

## 情趣系统说明

- 好感度达到 200 且 `enable_explicit_mode` 为 true 时，系统会自动或手动触发语言色情互动。
- 情趣剧情同样基于 AI 生成，仅涉及成年、双向自愿的描写。
- 若未开启开关，将只提示好感度已满，不会进入色情剧情。

## 开发信息

- 作者：LumineStory
- 仓库：https://github.com/oyxning/astrabot-plugin-moremorelove
- 依赖：仅使用 AstrBot 官方插件 API，默认无需额外安装第三方库。
- 许可协议：MIT License（见仓库根目录 `LICENSE`）

如遇异常，请查看 AstrBot 日志或提交 issue 反馈。祝你和恋恋拥有更多甜蜜瞬间！
