import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

MAX_FAVORABILITY = 200
MIN_FAVORABILITY = 0
HISTORY_LIMIT = 12
STATE_VERSION = 1


@dataclass
class PlayerState:
    favorability: int = 50
    in_gal_mode: bool = False
    intimacy_unlocked: bool = False
    intimacy_sessions: int = 0
    last_action: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "favorability": self.favorability,
            "in_gal_mode": self.in_gal_mode,
            "intimacy_unlocked": self.intimacy_unlocked,
            "intimacy_sessions": self.intimacy_sessions,
            "last_action": self.last_action,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerState":
        return cls(
            favorability=int(data.get("favorability", 50)),
            in_gal_mode=bool(data.get("in_gal_mode", False)),
            intimacy_unlocked=bool(data.get("intimacy_unlocked", False)),
            intimacy_sessions=int(data.get("intimacy_sessions", 0)),
            last_action=data.get("last_action"),
            history=list(data.get("history", [])),
        )

    def copy(self) -> "PlayerState":
        return PlayerState.from_dict(self.to_dict())


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


@register(
    "moremorelove",
    "LumineStory",
    "基于 AI 的 Galgame 互动体验",
    "0.1.0",
    "https://github.com/oyxning/astrabot-plugin-moremorelove",
)
class MoreMoreLovePlugin(Star):
    def __init__(self, context: Context, config: Optional[Dict[str, Any]] = None):
        super().__init__(context, config)
        self._config = config or {}
        self._state_lock = asyncio.Lock()
        self._data_dir: Path = Path(StarTools.get_data_dir("moremorelove"))
        self._state_file = self._data_dir / "state.json"
        self._player_states: Dict[str, PlayerState] = {}

    async def initialize(self):
        await self._load_state()

    async def terminate(self):
        await self._persist_state()

    def _player_display_name(self, event: AstrMessageEvent) -> str:
        configured = (self._config.get("player_name") or "").strip()
        if configured:
            return configured
        return event.get_sender_name() or "玩家"

    def _heroine_name(self) -> str:
        name = (self._config.get("heroine_name") or "恋恋").strip()
        return name or "恋恋"

    def _custom_persona_prompt(self) -> str:
        return (self._config.get("custom_character_prompt") or "").strip()

    def _explicit_enabled(self) -> bool:
        return bool(self._config.get("enable_explicit_mode", False))

    def _status_card_use_t2i(self) -> bool:
        return bool(self._config.get("status_card_use_t2i", True))

    async def _load_state(self):
        if not self._state_file.exists():
            return

        try:
            payload = await asyncio.to_thread(self._read_state_payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MoreMoreLove 载入存档失败：%s", exc)
            return

        players = payload.get("players", {})
        async with self._state_lock:
            self._player_states = {
                user_id: PlayerState.from_dict(state) for user_id, state in players.items()
            }

    async def _persist_state(self):
        async with self._state_lock:
            await self._persist_state_locked()

    async def _persist_state_locked(self):
        snapshot = {
            "version": STATE_VERSION,
            "players": {
                user_id: state.to_dict() for user_id, state in self._player_states.items()
            },
        }
        await asyncio.to_thread(self._write_state_payload, snapshot)

    def _read_state_payload(self) -> Dict[str, Any]:
        with self._state_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_state_payload(self, payload: Dict[str, Any]) -> None:
        temp_path = self._state_file.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_path.replace(self._state_file)

    async def _get_state_snapshot(self, user_id: str) -> PlayerState:
        async with self._state_lock:
            state = self._player_states.get(user_id)
            created = False
            if state is None:
                state = PlayerState()
                self._player_states[user_id] = state
                created = True
            if created:
                await self._persist_state_locked()
            return state.copy()

    async def _mutate_state(
        self, user_id: str, mutator: Callable[[PlayerState], Any]
    ) -> Tuple[PlayerState, Any]:
        async with self._state_lock:
            state = self._player_states.setdefault(user_id, PlayerState())
            result = mutator(state)
            snapshot = state.copy()
            await self._persist_state_locked()
        return snapshot, result

    def _history_excerpt(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return "（暂无历史互动）"
        recent = history[-3:]
        segments = []
        for item in recent:
            action = item.get("action", "未知行动")
            narration = item.get("narration", "").strip()
            delta = int(item.get("delta", 0))
            segments.append(
                f"玩家行动：{action}\n女主回应：{narration}\n好感变化：{delta:+d}"
            )
        return "\n\n".join(segments)

    def _build_action_prompt(
        self, event: AstrMessageEvent, state: PlayerState, action_text: str
    ) -> str:
        player_name = self._player_display_name(event)
        heroine_name = self._heroine_name()
        history_block = self._history_excerpt(state.history)
        return (
            f"你是一款互动式 Galgame 中的成年女主角“{heroine_name}”，需要以恋爱游戏的口吻与玩家互动。\n"
            f"玩家“{player_name}”当前的好感度为 {state.favorability}/{MAX_FAVORABILITY}。\n"
            f"以下是最近的互动历史：\n{history_block}\n"
            "请根据玩家提出的行动生成一次新的剧情互动，保持语气自然、具有画面感，避免直接使用系统描述。\n"
            "请严格以 JSON 对象格式输出结果，且不要附加任何额外文本。JSON 字段说明：\n"
            '- "narration": string，描述你与玩家的互动过程，使用简体中文的第二人称视角，避免直白的色情描写。\n'
            '- "favorability_delta": int，范围 -20 到 20，代表这次行动对好感度的影响。\n'
            '- "mood": string，只能是 "positive"、"neutral" 或 "negative"。\n'
            '- "player_feedback": string，给玩家的简短建议或情绪反馈。\n'
            '- "intimacy_signal": bool，当剧情暗示可以迈入更亲密阶段时为 true，否则为 false。\n'
            f'玩家此次行动请求为：“{action_text}”。合理评估其正向或负向效果。'
        )

    async def _call_llm(
        self,
        event: AstrMessageEvent,
        prompt: str,
        contexts: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        provider = self.context.get_using_provider(event.unified_msg_origin)
        if provider is None:
            return None, "未找到可用的 LLM 提供商，请先在 AstrBot 中完成模型配置。"

        try:
            response = await provider.text_chat(
                prompt=prompt,
                session_id=event.unified_msg_origin,
                contexts=contexts or [],
                system_prompt=system_prompt or None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MoreMoreLove 调用 LLM 失败：%s", exc)
            return None, f"哎呀，恋恋没有获得 AI 的回应：{exc}"

        text = response.completion_text.strip()
        if not text:
            return None, "AI 沉默不语，恋恋暂时没有回应。"
        return text, None

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        while start != -1:
            brace = 0
            for idx in range(start, len(text)):
                char = text[idx]
                if char == "{":
                    brace += 1
                elif char == "}":
                    brace -= 1
                    if brace == 0:
                        candidate = text[start : idx + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
            start = text.find("{", start + 1)
        return None

    async def _invoke_action_ai(
        self, event: AstrMessageEvent, state: PlayerState, action_text: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        contexts: List[Dict[str, str]] = []
        if state.history:
            player_name = self._player_display_name(event)
            for item in state.history[-3:]:
                contexts.append(
                    {"role": "user", "content": f"{player_name} 的行动：{item.get('action', '')}"}
                )
                contexts.append(
                    {
                        "role": "assistant",
                        "content": item.get("narration", ""),
                    }
                )

        prompt = self._build_action_prompt(event, state, action_text)
        system_prompt = self._custom_persona_prompt()
        raw_text, error = await self._call_llm(
            event,
            prompt,
            contexts=contexts,
            system_prompt=system_prompt if system_prompt else None,
        )
        if error:
            return None, error

        if raw_text is None:
            return None, "AI 没有给出任何内容。"

        payload = self._extract_json(raw_text)
        if payload is None:
            logger.warning("MoreMoreLove 未能解析 JSON，原始内容：%s", raw_text)
            return {
                "narration": raw_text,
                "favorability_delta": 0,
                "mood": "neutral",
                "player_feedback": "系统未能判定效果，本次好感度保持不变。",
                "intimacy_signal": False,
            }, None

        payload.setdefault("narration", "")
        payload["favorability_delta"] = int(payload.get("favorability_delta", 0))
        payload["mood"] = str(payload.get("mood", "neutral")) or "neutral"
        payload["player_feedback"] = str(payload.get("player_feedback", "")).strip()
        payload["intimacy_signal"] = bool(payload.get("intimacy_signal", False))
        return payload, None

    async def _apply_action_outcome(
        self, user_id: str, action_text: str, outcome: Dict[str, Any]
    ) -> Tuple[PlayerState, int]:
        def mutate(state: PlayerState):
            delta = clamp(int(outcome.get("favorability_delta", 0)), -20, 20)
            new_value = clamp(state.favorability + delta, MIN_FAVORABILITY, MAX_FAVORABILITY)
            record = {
                "timestamp": datetime.utcnow().isoformat(),
                "action": action_text,
                "narration": outcome.get("narration", ""),
                "delta": delta,
                "mood": outcome.get("mood", "neutral"),
                "feedback": outcome.get("player_feedback", ""),
            }
            state.favorability = new_value
            state.last_action = action_text
            state.history.append(record)
            if len(state.history) > HISTORY_LIMIT:
                state.history = state.history[-HISTORY_LIMIT:]
            if new_value >= MAX_FAVORABILITY:
                state.intimacy_unlocked = True
            return delta

        new_state, delta = await self._mutate_state(user_id, mutate)
        return new_state, delta

    async def _record_intimacy_session(self, user_id: str, narration: str):
        def mutate(state: PlayerState):
            state.intimacy_unlocked = True
            state.intimacy_sessions += 1
            state.last_action = "情趣系统互动"
            state.history.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "action": "[情趣系统互动]",
                    "narration": narration,
                    "delta": 0,
                    "mood": "intimacy",
                    "feedback": "恋恋与你共同沉浸在亲密时光中。",
                }
            )
            if len(state.history) > HISTORY_LIMIT:
                state.history = state.history[-HISTORY_LIMIT:]

        await self._mutate_state(user_id, mutate)

    def _translate_mood(self, mood: str) -> str:
        mapping = {
            "positive": "心情愉悦",
            "neutral": "情绪平稳",
            "negative": "略显失落",
            "intimacy": "沉溺于亲密",
        }
        return mapping.get(mood, "难以捉摸")

    def _build_status_text(self, event: AstrMessageEvent, state: PlayerState) -> str:
        hero = self._heroine_name()
        player = self._player_display_name(event)
        lines = [
            f"MoreMoreLove 状态面板",
            f"当前对象：{hero}",
            f"玩家：{player}",
            f"恋爱模式：{'开启' if state.in_gal_mode else '关闭'}",
            f"好感度：{state.favorability}/{MAX_FAVORABILITY}",
        ]
        if state.intimacy_unlocked:
            lines.append(f"情趣系统：已解锁（互动次数 {state.intimacy_sessions}）")
        else:
            lines.append("情趣系统：未解锁")
        if state.last_action:
            lines.append(f"最近行动：{state.last_action}")
        if state.history:
            lines.append(f"她的心情：{self._translate_mood(state.history[-1].get('mood', 'neutral'))}")
        lines.append(f"色情互动开关：{'开启' if self._explicit_enabled() else '关闭'}")
        return "\n".join(lines)

    async def _render_status_card(
        self, event: AstrMessageEvent, state: PlayerState
    ) -> List:
        summary = self._build_status_text(event, state)
        if not self._status_card_use_t2i():
            result = event.plain_result(summary)
            result.use_t2i(False)
            return [result]

        try:
            url = await self.text_to_image(summary, return_url=True)
            result = event.image_result(url)
            result.use_t2i(False)
            return [result]
        except Exception as exc:  # noqa: BLE001
            logger.warning("MoreMoreLove t2i 生成失败，退回文本：%s", exc)
            fallback = event.plain_result(summary)
            fallback.use_t2i(False)
            return [fallback]

    async def _perform_intimacy_scene(
        self, event: AstrMessageEvent, state: PlayerState, trigger_reason: str
    ) -> Tuple[Optional[str], Optional[str]]:
        if not self._explicit_enabled():
            return None, "色情互动开关当前关闭，可在插件配置中开启。"

        hero = self._heroine_name()
        player = self._player_display_name(event)
        history_excerpt = self._history_excerpt(state.history)
        prompt = (
            f"你是一款成人向 Galgame 中的女主角“{hero}”，已与玩家“{player}”建立最高好感度的亲密关系。\n"
            f"触发原因：{trigger_reason}。\n"
            "请创作 3-4 段富有画面感的亲密描写，确保双方为成年且完全自愿，重点刻画动作、触感与情绪。\n"
            "内容需采用简体中文第一人称（代表你）与第二人称（代表玩家）的混合叙述，允许出现肢体描写与语言色情。\n"
            "请保持优雅与情感丰富，避免粗俗语言。不得输出任何 JSON，仅输出正文。\n"
            "可参考的最近互动：\n"
            f"{history_excerpt}"
        )
        system_prompt = self._custom_persona_prompt()
        raw_text, error = await self._call_llm(
            event,
            prompt,
            contexts=None,
            system_prompt=system_prompt if system_prompt else None,
        )
        if error:
            return None, error
        return raw_text, None

    async def _handle_action(
        self, event: AstrMessageEvent, action_text: str
    ) -> List:
        user_id = event.get_sender_id()
        state = await self._get_state_snapshot(user_id)
        if not state.in_gal_mode:
            result = event.plain_result("恋恋仍在日常模式，请先使用 galstart 进入 Gal 模式。")
            result.use_t2i(False)
            return [result]

        outcome, error = await self._invoke_action_ai(event, state, action_text)
        if error:
            result = event.plain_result(error)
            result.use_t2i(False)
            return [result]
        assert outcome is not None

        new_state, real_delta = await self._apply_action_outcome(
            user_id, action_text, outcome
        )

        narrative_lines = [
            outcome.get("narration", "").strip(),
            f"好感度变动：{real_delta:+d} → {new_state.favorability}/{MAX_FAVORABILITY}",
        ]
        feedback = outcome.get("player_feedback", "").strip()
        if feedback:
            narrative_lines.append(f"恋恋的提示：{feedback}")

        if (
            new_state.intimacy_unlocked
            and new_state.intimacy_sessions == 0
            and self._explicit_enabled()
        ):
            narrative_lines.append("好感度已满，恋恋的心意更加炽热，情趣系统即将开启。")

        result = event.plain_result("\n".join(narrative_lines))
        result.use_t2i(False)
        replies: List = [result]

        should_trigger_intimacy = (
            outcome.get("intimacy_signal", False)
            and new_state.intimacy_unlocked
            and self._explicit_enabled()
        )
        auto_unlock = (
            new_state.intimacy_unlocked
            and new_state.intimacy_sessions == 0
            and self._explicit_enabled()
        )

        if should_trigger_intimacy or auto_unlock:
            trigger_reason = (
                "互相确认心意后顺势靠近"
                if should_trigger_intimacy
                else "好感度抵达 200，恋恋渴望更进一步"
            )
            intimacy_text, intimacy_error = await self._perform_intimacy_scene(
                event, new_state, trigger_reason
            )
            if intimacy_text:
                intimacy_result = event.plain_result(intimacy_text)
                intimacy_result.use_t2i(False)
                replies.append(intimacy_result)
                await self._record_intimacy_session(user_id, intimacy_text)
            elif intimacy_error:
                warn = event.plain_result(intimacy_error)
                warn.use_t2i(False)
                replies.append(warn)

        return replies

    @filter.command("galmenu")
    async def gal_menu(self, event: AstrMessageEvent):
        hero = self._heroine_name()
        menu = (
            f"MoreMoreLove · {hero}\n"
            "【基础操作】\n"
            "galstart：进入 Gal 模式\n"
            "galexit：退出 Gal 模式\n"
            "galstatus：查看当前状态\n"
            "galreset：重置本会话进度\n"
            "【AI 行动】\n"
            "galpark：和恋恋去公园散步\n"
            "galcinema：邀恋恋去看电影\n"
            "galact <行动>：自定义行动，如“galact 准备烛光晚餐”\n"
            "galintimacy：在满足条件时主动触发情趣系统\n"
            "（正确或错误的行动都会影响好感度，请谨慎选择！）"
        )
        result = event.plain_result(menu)
        result.use_t2i(False)
        yield result

    @filter.command("galstart")
    async def gal_start(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()

        def mutate(state: PlayerState):
            if state.in_gal_mode:
                return False
            state.in_gal_mode = True
            state.last_action = "开启恋恋的 Gal 模式"
            return True

        new_state, changed = await self._mutate_state(user_id, mutate)
        if changed:
            message = (
                f"恋恋轻轻握住你的手：从现在起，我们的故事正式开始。当前好感度为 "
                f"{new_state.favorability}/{MAX_FAVORABILITY}。"
            )
        else:
            message = "恋恋早已全神贯注地看着你，我们已经在 Gal 模式中啦。"
        result = event.plain_result(message)
        result.use_t2i(False)
        yield result

    @filter.command("galexit")
    async def gal_exit(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()

        def mutate(state: PlayerState):
            if not state.in_gal_mode:
                return False
            state.in_gal_mode = False
            return True

        _, changed = await self._mutate_state(user_id, mutate)
        if changed:
            message = "恋恋点了点头：那就暂时回到日常状态吧，随时呼唤我回来。"
        else:
            message = "恋恋一直在日常模式，如果想恋爱请先 galstart 哟。"
        result = event.plain_result(message)
        result.use_t2i(False)
        yield result

    @filter.command("galstatus")
    async def gal_status(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        state = await self._get_state_snapshot(user_id)
        for result in await self._render_status_card(event, state):
            yield result

    @filter.command("galreset")
    async def gal_reset(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()

        async with self._state_lock:
            self._player_states[user_id] = PlayerState()
            await self._persist_state_locked()

        result = event.plain_result("恋恋重新整理了记忆，一切从零开始。")
        result.use_t2i(False)
        yield result

    @filter.command("galpark")
    async def gal_park(self, event: AstrMessageEvent):
        for reply in await self._handle_action(event, "与恋恋在公园并肩散步，分享彼此心事"):
            yield reply

    @filter.command("galcinema")
    async def gal_cinema(self, event: AstrMessageEvent):
        for reply in await self._handle_action(event, "邀请恋恋去电影院看浪漫影片"):
            yield reply

    @filter.command("galact")
    async def gal_act(self, event: AstrMessageEvent):
        tokens = self.parse_commands(event.message_str)
        if tokens.len < 2:
            result = event.plain_result("用法：galact <行动>，例如“galact 亲手准备晚餐”。")
            result.use_t2i(False)
            yield result
            return
        action_text = " ".join(tokens.tokens[1:]).strip()
        if not action_text:
            result = event.plain_result("请在 galact 后描述你的行动。")
            result.use_t2i(False)
            yield result
            return

        for reply in await self._handle_action(event, action_text):
            yield reply

    @filter.command("galintimacy")
    async def gal_intimacy(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        state = await self._get_state_snapshot(user_id)
        if not state.in_gal_mode:
            result = event.plain_result("恋恋尚未进入 Gal 模式，先使用 galstart 吧。")
            result.use_t2i(False)
            yield result
            return
        if state.favorability < MAX_FAVORABILITY:
            result = event.plain_result("恋恋还需要更多的心动时刻，至少达到 200 好感度后再试。")
            result.use_t2i(False)
            yield result
            return

        intimacy_text, intimacy_error = await self._perform_intimacy_scene(
            event, state, "玩家主动请求更亲密的时刻"
        )
        if intimacy_text:
            result = event.plain_result(intimacy_text)
            result.use_t2i(False)
            yield result
            await self._record_intimacy_session(user_id, intimacy_text)
        elif intimacy_error:
            result = event.plain_result(intimacy_error)
            result.use_t2i(False)
            yield result
