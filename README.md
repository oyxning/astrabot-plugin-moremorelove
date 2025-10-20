# MoreMoreLove — AstrBot Galgame 插件

> ⚠️ **内容提醒**：本插件含成人向恋爱与情趣元素，仅供 **成年人** 在遵守所在地法律法规与平台规范的前提下使用。

---

## 简介

**MoreMoreLove** 是面向 **AstrBot** 的“恋爱互动（Galgame）”插件。  
它提供一位可自定义昵称的女主角（默认名：**恋恋**），并支持两种游玩方式：

- **AI 行为模式**：接入你的 LLM 服务，依据玩家“行动”即时生成剧情、心情与好感变化；
- **经典剧本模式**：内置多分支剧情，即使未配置 LLM 也能完整体验。

两种模式间支持**自动回退**，保证不中断的恋爱体验。

---

## 主要特性

- **一键菜单**：`galmenu` 展示可用指令与示例，开箱即玩  
- **模式切换**：`galstart / galexit` 在日常与 Gal 模式间进出  
- **好感系统**：互动会增减好感（满值默认 **200**），影响可用桥段  
- **自定义行动**：`galact <行动>` 由 AI/剧本生成“下一步会发生什么”  
- **亲密解锁（可选）**：满足条件后用 `galintimacy` 解锁更亲密互动（需显式开启）  
- **环境感知**：`galtime / galweather` 引入现实时间与天气，增强临场感  
- **状态卡片**：`galstatus` 输出状态文本；如启用 t2i，可生成“恋恋状态卡片”图片  
- **纯成人模式（可选）**：`galpure on/off/status`（需在配置中允许；仅供成年人）

---

## 安装与启动

1. 将插件目录放到：`/AstrBot/data/plugins/astrabot-plugin-moremorelove/`  
2. 重载/重启 AstrBot（或在后台“重载插件”）使其识别 `metadata.yaml` 与配置

依赖：仅使用 AstrBot 官方插件 API；天气数据默认来源 `wttr.in` 公共接口

---

## 快速上手

1. 发送 `galmenu` 查看指令与示例  
2. 发送 `galstart` 进入 Gal 模式  
3. 试试以下行动：
   - `galpark`（与恋恋去公园散步）
   - `galcinema`（邀请恋恋看电影）
   - `galact 准备一顿烛光晚餐`（完全自定义）
4. 用 `galstatus` 查看好感与近期互动摘要

提示：若已配置 LLM → 使用 **AI 行为模式**；无法连接模型时自动回落到 **经典剧本模式**。

---

## 指令一览

- **基础**
  - `galmenu`：展示指令与说明  
  - `galstart` / `galexit`：进入 / 退出 Gal 模式  
  - `galstatus`：查看当前状态（文本或 t2i 卡片）  
  - `galreset`：重置会话（清空好感、历史等）

- **环境信息**
  - `galtime`：查看现实世界时间（按配置时区）  
  - `galweather [地点]`：查询天气（留空用默认城市）

- **行动 & 剧情**
  - `galpark`：公园散步  
  - `galcinema`：一起看电影  
  - `galact <行动>`：自定义行动，由 AI/剧本生成结果  
  - `galintimacy`：满足条件时触发更亲密的桥段（需显式开启）

- **成人模式（可选）**
  - `galpure on/off/status`：开启 / 关闭 / 查看状态  
  - 仅在合规场景下使用；需先在配置中允许相关功能。

---

## 配置

下列为常用配置项（字段名与默认值以实际文件为准）：

| 键名 | 类型 | 说明 | 默认值 |
|---|---|---|---|
| `player_name` | string | 玩家称呼；留空时自动使用消息平台昵称 | `""` |
| `heroine_name` | string | 女主角名字 | `"恋恋"` |
| `custom_character_prompt` | string/text | 追加的人设提示词 | `""` |
| `enable_ai_behavior` | bool | 是否启用 AI 行为模式 | `true` |
| `allow_pure_erotic_mode` | bool | 允许 `galpure` 开关成人模式 | `false` |
| `erotic_intensity` | string | 成人模式强度：`soft` / `strong` | `"soft"` |
| `enable_explicit_mode` | bool | 满好感后是否允许亲密互动（`galintimacy`） | `false` |
| `status_card_use_t2i` | bool | `galstatus` 是否尝试用 t2i 生成图卡 | `true` |
| `time_zone` | string | 主时区（示例：`Asia/Shanghai`） | `"Asia/Shanghai"` |
| `weather_location` | string | 天气默认城市；留空使用 `Shanghai` | `""` |
| `weather_refresh_minutes` | int | 天气缓存分钟数（最小值建议 ≥ 10） | `60` |

---

## AI 行为模式的输出结构

当执行 `galact <行动>` 等需要 AI 推理的指令时，插件会要求模型以 **JSON 对象** 回复，示例：

    {
      "narration": "string — 第一人称、口语化的自然叙述，展现动作与情绪",
      "favorability_delta": -20,
      "mood": "positive | neutral | negative",
      "player_feedback": "string — 贴心建议/撒娇提醒",
      "intimacy_signal": false
    }

- 插件会据此更新好感度、渲染对话与后续分支；  
- 如果模型不可用，将自动使用经典剧本生成等效字段。

---

## 常见问题（FAQ）

- **无法连接到模型**  
  确认已正确配置 LLM 相关环境与密钥。若不可用，插件会自动回落到经典剧本模式，仍可继续游玩。

- **语法/格式相关错误**  
  若自行修改配置或提示词，请确保引号、括号配对正确；建议使用 IDE 的语法高亮与格式化功能。

---

## 声明

- 本插件仅用于合法合规、成年人自愿的娱乐场景；请自行判断与设置内容强度。  
- 请勿在未成年人可接触的环境中启用成人向功能。
