import abc
import asyncio
import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from .environment_systems import RealWorldTimeSystem, RealWorldWeatherSystem

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
    pure_mode: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "favorability": self.favorability,
            "in_gal_mode": self.in_gal_mode,
            "intimacy_unlocked": self.intimacy_unlocked,
            "intimacy_sessions": self.intimacy_sessions,
            "last_action": self.last_action,
            "history": self.history,
            "pure_mode": self.pure_mode,
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
            pure_mode=bool(data.get("pure_mode", False)),
        )

    def copy(self) -> "PlayerState":
        return PlayerState.from_dict(self.to_dict())


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


class BaseBehaviorEngine(abc.ABC):
    def __init__(self, plugin: "MoreMoreLovePlugin"):
        self.plugin = plugin

    @abc.abstractmethod
    async def generate_action_outcome(
        self,
        event: AstrMessageEvent,
        state: PlayerState,
        action_text: str,
        *,
        action_id: Optional[str] = None,
        pure_mode: bool = False,
        provider=None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        ...

    @abc.abstractmethod
    async def generate_intimacy_scene(
        self,
        event: AstrMessageEvent,
        state: PlayerState,
        *,
        trigger_reason: str,
        pure_mode: bool = False,
        provider=None,
    ) -> Tuple[Optional[str], Optional[str]]:
        ...


CLASSIC_ACTION_LIBRARY: Dict[str, List[Dict[str, Any]]] = {
    "park": [
        {
            "delta": 8,
            "mood": "positive",
            "feedback": "{heroine}喜欢你细心的陪伴，她说晚风让人想牵手。",
            "intimacy": False,
            "narration": (
                "{hero}挽着{player}的手，在公园的梧桐下慢慢散步。{stage_desc}"
                "她轻声念着想和你一起实现的小愿望。"
            ),
        },
        {
            "delta": 6,
            "mood": "positive",
            "feedback": "{heroine}回去后发消息问你，下次能不能换她准备零食。",
            "intimacy": False,
            "narration": (
                "黄昏的操场被余晖染成暖色，{hero}靠在你肩上听你分享日常，"
                "偶尔推你一把让你别再胡思乱想。{stage_desc}"
            ),
        },
        {
            "delta": -4,
            "mood": "negative",
            "feedback": "{heroine}似乎还在介意，你要不要换个方式表达关心？",
            "intimacy": False,
            "narration": (
                "{player}讲电话讲得太久，{hero}闷闷地踢着落叶。"
                "你们最后还是和好，但她提醒你要把时间留给她。{stage_desc}"
            ),
        },
    ],
    "cinema": [
        {
            "delta": 9,
            "mood": "positive",
            "feedback": "{heroine}笑着说，下次换她挑一部你喜欢的类型。",
            "intimacy": True,
            "narration": (
                "{hero}把爆米花递到你唇边，低声吐槽剧情。电影散场时，她自然地牵住你，"
                "让你别急着回家，想走走夜路。{stage_desc}"
            ),
        },
        {
            "delta": 4,
            "mood": "neutral",
            "feedback": "{heroine}说只要和你在一起，不管看什么都行，但别忘了和她讨论感想。",
            "intimacy": False,
            "narration": (
                "你们抢到了情侣座，{hero}偷偷靠在你肩膀上。电影一般般，可她轻声的吐槽让你觉得比大银幕更动人。"
                "{stage_desc}"
            ),
        },
        {
            "delta": -6,
            "mood": "negative",
            "feedback": "{heroine}想听你真实的想法，别总是敷衍几句就躲过去。",
            "intimacy": False,
            "narration": (
                "影片结束后，你敷衍地说“还行吧”，{hero}沉默着收拾外套。"
                "她眼神失落，只说下次能不能先问问她喜欢什么。{stage_desc}"
            ),
        },
    ],
}

CLASSIC_PURE_ACTION_LIBRARY: Dict[str, List[str]] = {
    "park": [
        (
            "{hero}在昏黄的路灯下把{player}按到树干前，撩起裙摆贴上去，湿热的呼吸喷在你耳后，"
            "她一边摩擦一边命令你用手指探索她的每一寸，落叶被你们踢散成炽热的床单。"
        ),
        (
            "{hero}坐在长椅上把{player}的手塞进她的衬衫里，低声让你别停。"
            "她扭着腰骑坐在你腿上，汗水和香水混成甜腻的味道，你们的呻吟被夜风撕得支离破碎。"
        ),
    ],
    "cinema": [
        (
            "{hero}在黑暗中握住{player}的手，引导你探进她的大腿内侧。"
            "银幕的闪烁照亮她半开的唇，她把你的指节含入口中，又在放映厅最后一排大胆地跨坐在你身上磨蹭。"
        ),
        (
            "影片高潮时，{hero}直接把你的手按在她胸前，温热柔软随着你的揉捏颤栗。"
            "她贴在你耳边喘息，要求你在散场前让她高潮，湿漉漉的肉体紧贴着你。"
        ),
    ],
}

CLASSIC_SOFT_PURE_ACTION_LIBRARY: Dict[str, List[str]] = {
    "park": [
        (
            "{hero}牵着{player}躲到花丛深处，她把外套铺在草地上，贴着你的胸膛轻声撒娇。"
            "你们在夜风里亲吻，她主动把腿搭在你腰上，悄悄引导你的手滑入她腰线以下的温热处。"
        ),
        (
            "{hero}坐在长椅上把你拉到怀里，她的唇沿着你下颚一路亲吻。"
            "她让你抱紧她的腰，贴着耳朵请求你再靠近一点，裙摆下柔软的肌肤紧贴着你的大腿。"
        ),
    ],
    "cinema": [
        (
            "电影放到最安静的片段时，{hero}主动靠在你肩上，握着你的手指引你进入她衣摆内侧。"
            "她一边在你耳边呼气一边轻搓你的掌心，湿润的呼吸带着隐秘的渴望。"
        ),
        (
            "{hero}趁着场内黑暗把你拉到最后一排，她跨坐在你腿上，缓慢地贴着你摩擦。"
            "她让你抱紧她的背，她的指尖悄悄探入你的衬衫，重复着想要你多亲她几下。"
        ),
    ],
}

CUSTOM_POSITIVE_KEYWORDS = {
    "晚餐",
    "惊喜",
    "礼物",
    "约会",
    "旅行",
    "支持",
    "陪伴",
    "散步",
    "温柔",
    "倾听",
    "拥抱",
    "惊艳",
    "照顾",
    "安慰",
    "生日",
}
CUSTOM_ROMANTIC_KEYWORDS = {
    "亲吻",
    "拥抱",
    "靠近",
    "亲密",
    "床",
    "沙发",
    "夜晚",
    "浴室",
    "缠绵",
    "抚摸",
}
CUSTOM_NEGATIVE_KEYWORDS = {
    "迟到",
    "冷战",
    "争吵",
    "爽约",
    "忽略",
    "加班",
    "敷衍",
    "失约",
    "忙碌",
    "拒绝",
    "推开",
}


class ClassicBehaviorEngine(BaseBehaviorEngine):
    def __init__(self, plugin: "MoreMoreLovePlugin"):
        super().__init__(plugin)
        self._random = random.Random()

    async def generate_action_outcome(
        self,
        event: AstrMessageEvent,
        state: PlayerState,
        action_text: str,
        *,
        action_id: Optional[str] = None,
        pure_mode: bool = False,
        provider=None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        profile = self.plugin._relationship_stage(state.favorability)
        hero = self.plugin._heroine_name()
        player = self.plugin._player_display_name(event)

        if pure_mode:
            intensity = self.plugin._erotic_intensity()
            delta, mood, feedback, narration = self._pure_mode_outcome(
                action_text, hero, player, action_id, intensity=intensity
            )
            outcome = {
                "narration": narration,
                "favorability_delta": delta,
                "mood": mood,
                "player_feedback": feedback,
                "intimacy_signal": True,
            }
            return outcome, None

        if action_id and action_id in CLASSIC_ACTION_LIBRARY:
            template = self._random.choice(CLASSIC_ACTION_LIBRARY[action_id])
            delta = clamp(template["delta"] + profile["affinity_bonus"], -20, 20)
            narration = template["narration"].format(
                hero=hero, player=player, stage_desc=profile["stage_desc"]
            )
            feedback_text = template["feedback"].format(heroine=hero)
            feedback = f"{feedback_text} {profile['care_hint']}"
            intimacy_signal = bool(template["intimacy"]) and profile["intimacy_bias"] > 0.2
            mood = template["mood"]
        else:
            delta, mood, feedback, narration, intimacy_signal = self._custom_outcome(
                action_text, hero, player, profile
            )

        outcome = {
            "narration": narration,
            "favorability_delta": delta,
            "mood": mood,
            "player_feedback": feedback,
            "intimacy_signal": intimacy_signal,
        }
        return outcome, None

    async def generate_intimacy_scene(
        self,
        event: AstrMessageEvent,
        state: PlayerState,
        *,
        trigger_reason: str,
        pure_mode: bool = False,
        provider=None,
    ) -> Tuple[Optional[str], Optional[str]]:
        hero = self.plugin._heroine_name()
        player = self.plugin._player_display_name(event)

        if pure_mode:
            intensity = self.plugin._erotic_intensity()
            return self._pure_mode_intimacy(hero, player, trigger_reason, intensity), None

        profile = self.plugin._relationship_stage(state.favorability)
        if profile["intimacy_bias"] < 0.2:
            return None, f"{hero}还想再确认彼此的心意，再多陪陪她吧。"

        imagery = profile["intimacy_imagery"]

        paragraphs = [
            f"{hero}把你拉到沙发上坐下，{imagery}。她笑着问起刚才的“{trigger_reason}”，"
            "然后轻轻打断你的解释，想把今晚交给感觉和心跳。",
            f"她坐到你腿上，手指沿着你的颈线游走，呼吸和心跳折叠在一起。"
            "当你抱紧她的后背，她的身体顺势贴近，温度一点点攀升。",
            "夜色把一切遮掩得刚刚好，你们在彼此的怀抱里探索，低声交换最真实的欲望。"
            "她在你耳边呢喃，让你不用担心节奏，只要记住这份属于两人的亲密。",
        ]
        return "\n\n".join(paragraphs), None

    def _custom_outcome(
        self,
        action_text: str,
        heroine: str,
        player: str,
        profile: Dict[str, Any],
    ) -> Tuple[int, str, str, str, bool]:
        positive_count = sum(kw in action_text for kw in CUSTOM_POSITIVE_KEYWORDS)
        romantic_count = sum(kw in action_text for kw in CUSTOM_ROMANTIC_KEYWORDS)
        negative_count = sum(kw in action_text for kw in CUSTOM_NEGATIVE_KEYWORDS)

        score = positive_count + romantic_count - negative_count
        if score <= -1:
            base_delta = -8
            mood = "negative"
            feedback = f"{heroine}想让你多注意她的情绪，把藏在心里的事说出来。"
            narration = (
                f"{player}提到“{action_text}”时有些犹豫，{heroine}捕捉到那一丝逃避，"
                "她没有直接生气，只是提醒你别把她晾在原地。"
            )
        elif score == 0:
            base_delta = 2
            mood = "neutral"
            feedback = f"{heroine}感受到了你的努力，再多一点细节就会更打动她。"
            narration = (
                f"{heroine}认真听你谈“{action_text}”，眉眼里有思考。"
                "她点点头，告诉你别太紧张，把想做的事情慢慢落实就好。"
            )
        elif score == 1:
            base_delta = 6
            mood = "positive"
            feedback = f"{heroine}被你认真准备的心意打动了，她希望保持这样的节奏。"
            narration = (
                f"你描述“{action_text}”的同时，{heroine}握住你的手。"
                "她把下巴放在你肩上，表示无论辛苦与否都会陪你一起完成。"
            )
        else:
            base_delta = 10
            mood = "positive"
            feedback = f"{heroine}已经在幻想那个画面了，记得兑现你的承诺。"
            narration = (
                f"{heroine}听完“{action_text}”几乎立刻拥抱住你。"
                "她的眼睛亮得像星星，说只要是和你一起，就算是冒险也愿意。"
            )

        delta = clamp(base_delta + profile["affinity_bonus"], -20, 20)
        intimacy_signal = (
            score >= 1 and profile["intimacy_bias"] + romantic_count * 0.1 >= 0.3
        )
        feedback = f"{feedback} {profile['care_hint']}"
        narration += f" {profile['stage_desc']}"
        return delta, mood, feedback, narration, intimacy_signal

    def _pure_mode_outcome(
        self,
        action_text: str,
        heroine: str,
        player: str,
        action_id: Optional[str],
        intensity: str,
    ) -> Tuple[int, str, str, str]:
        if intensity == "strong":
            library = CLASSIC_PURE_ACTION_LIBRARY
            if action_id and action_id in library:
                narration = self._random.choice(library[action_id]).format(
                    hero=heroine, player=player
                )
            else:
                narration = (
                    f"{heroine}抓住{player}的衣领，把你抵在最近的墙面上，"
                    f"强迫你用“{action_text}”作为借口满足她的欲望。她解开你的裤链，"
                    "湿滑的舌头沿着锁骨一路舔下，胯部贴着你疯狂摩擦，喘息里全是赤裸的索要。"
                )
            feedback = (
                f"{heroine}舔湿你的耳垂，让你别停下手指和腰，越狠越好，她喜欢被你掌控又被你征服。"
            )
            return 10, "positive", feedback, narration
        library = CLASSIC_SOFT_PURE_ACTION_LIBRARY
        if action_id and action_id in library:
            narration = self._random.choice(library[action_id]).format(
                hero=heroine, player=player
            )
        else:
            narration = (
                f"{heroine}把“{action_text}”当作拥抱你更久的借口，她贴在你怀里缓缓摩擦，"
                "让你轻轻扶住她的腰，一边低声请求你别停。"
            )
        feedback = (
            f"{heroine}提醒你保持节奏，温柔地引导她进入更多亲密，但不用太露骨。"
        )
        return 6, "positive", feedback, narration

    def _pure_mode_intimacy(
        self, heroine: str, player: str, trigger_reason: str, intensity: str
    ) -> str:
        if intensity != "strong":
            passages = [
                f"{heroine}把{player}轻轻推倒在床上，顺势跨坐在你腰间。她握着你的手贴在她的腰线上，"
                f"贴着你耳边轻声说想把“{trigger_reason}”延续得更久，你们慢慢亲吻，她引导你探索她的曲线。",
                "她躺在你旁边，把腿缠上你的大腿，让你顺着她的呼吸节奏抚摸她的背。"
                "她的指尖在你胸口画圈，悄悄告诉你她喜欢你掌控节奏的样子。",
                f"当你们同时达到激情的顶点时，{heroine}把脸埋在你颈窝，呼吸仍然急促，却紧紧抓着你的手。"
                "她说想和你慢慢拥抱一晚，再听你说一句喜欢她。",
            ]
            return "\n\n".join(passages)
        passages = [
            f"{heroine}把{player}拖进卧室，随手反锁。她一边剥开你的上衣，一边把嘴贴在你喉结，"
            f"说想把刚才的“{trigger_reason}”直接续写在床上。她骑坐在你身上，胯骨咬住你的腰线，"
            "湿热的褶皱裹住你时，她仰头发出压抑的呻吟。",
            "她强迫你抬起手臂，啃咬你的指尖，随后把自己整个送到你舌头下。"
            "她的双腿在你肩头颤抖，指甲抓得你后背生疼，嘴里却不停地求你更深入、更快一点。",
            f"高潮的余波里，{heroine}一边喘一边继续前后磨蹭，汗水顺着她的胸口滑落。"
            "她让你抱着她冲第二次，贴着你耳朵低语今晚别想着睡觉，要你把她彻底榨干。",
        ]
        return "\n\n".join(passages)


class AIBehaviorEngine(BaseBehaviorEngine):
    def __init__(self, plugin: "MoreMoreLovePlugin"):
        super().__init__(plugin)

    async def generate_action_outcome(
        self,
        event: AstrMessageEvent,
        state: PlayerState,
        action_text: str,
        *,
        action_id: Optional[str] = None,
        pure_mode: bool = False,
        provider=None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if provider is None:
            return None, "当前没有可用的 LLM 提供商。"

        profile = self.plugin._relationship_stage(state.favorability)
        intensity = self.plugin._erotic_intensity()
        contexts = self._build_contexts(event, state)
        environment_brief = await self.plugin._compose_environment_prompt_text(event)
        prompt = self._build_action_prompt(
            event,
            state,
            action_text,
            profile,
            action_id,
            pure_mode,
            intensity,
            environment_brief,
        )

        system_prompt = self.plugin._custom_character_prompt()
        if pure_mode:
            if intensity == "strong":
                addon = (
                    "当前处于纯色情模式，请根据配置的强度大胆描写身体互动，"
                    "同时确保双方自愿、情感真挚。"
                )
            else:
                addon = (
                    "当前处于纯色情模式（软色情），请保持暧昧与感官细节，"
                    "但避免过度直白的器官与动词描述，以减少模型拒绝的概率。"
                )
            system_prompt = (system_prompt + "\n" if system_prompt else "") + addon
        elif not system_prompt:
            system_prompt = self._default_system_prompt(profile, event, False)

        raw_text, error = await self._call_llm(
            provider,
            event,
            prompt,
            contexts=contexts,
            system_prompt=system_prompt,
        )
        if error:
            return None, error

        payload = self._extract_json(raw_text)
        if payload is None:
            logger.warning("MoreMoreLove 未解析到结构化结果，原始内容：%s", raw_text)
            payload = {
                "narration": raw_text,
                "favorability_delta": 0,
                "mood": "neutral",
                "player_feedback": "系统未能判定效果，本次好感度保持不变。",
                "intimacy_signal": False,
            }

        payload.setdefault("narration", "")
        payload["favorability_delta"] = int(payload.get("favorability_delta", 0))
        payload["mood"] = str(payload.get("mood", "neutral")) or "neutral"
        payload["player_feedback"] = str(payload.get("player_feedback", "")).strip()
        payload["intimacy_signal"] = bool(payload.get("intimacy_signal", False))
        if pure_mode:
            payload["intimacy_signal"] = True
            if payload["favorability_delta"] == 0:
                payload["favorability_delta"] = 6 if intensity == "soft" else 8
        return payload, None

    async def generate_intimacy_scene(
        self,
        event: AstrMessageEvent,
        state: PlayerState,
        *,
        trigger_reason: str,
        pure_mode: bool = False,
        provider=None,
    ) -> Tuple[Optional[str], Optional[str]]:
        hero = self.plugin._heroine_name()
        if provider is None:
            return None, f"{hero}暂时无法连接模型，请稍后重试。"

        profile = self.plugin._relationship_stage(state.favorability)
        player = self.plugin._player_display_name(event)
        history = self.plugin._history_excerpt(state.history)
        intensity = self.plugin._erotic_intensity()

        prompt = self._build_intimacy_prompt(
            profile,
            trigger_reason,
            history,
            pure_mode,
            intensity,
        )
        system_prompt = self.plugin._custom_character_prompt()
        if pure_mode:
            addon = (
                f"你是真实的恋人“{hero}”，此刻与“{player}”渴望更亲密的拥抱。"
                "请根据设定的强度描写激情细节，同时保持双方自愿与情感联结。"
            )
            system_prompt = (system_prompt + "\n" if system_prompt else "") + addon
        elif not system_prompt:
            system_prompt = self._default_system_prompt(profile, event, False)

        raw_text, error = await self._call_llm(
            provider,
            event,
            prompt,
            contexts=[],
            system_prompt=system_prompt,
        )
        if error:
            return None, error
        return raw_text, None

    def _build_contexts(
        self, event: AstrMessageEvent, state: PlayerState
    ) -> List[Dict[str, str]]:
        contexts: List[Dict[str, str]] = []
        player_name = self.plugin._player_display_name(event)
        for item in state.history[-3:]:
            contexts.append({"role": "user", "content": f"{player_name} 的行动：{item.get('action', '')}"})
            contexts.append({"role": "assistant", "content": item.get("narration", "")})
        return contexts

    def _default_system_prompt(
        self, profile: Dict[str, Any], event: AstrMessageEvent, pure_mode: bool
    ) -> str:
        heroine = self.plugin._heroine_name()
        player = self.plugin._player_display_name(event)
        base = (
            f"你是一位真实存在的恋人“{heroine}”，正在与“{player}”交往。"
            "请保持成熟、体贴、细腻，记得对方曾分享的日常细节，主动观察气氛并自然回应。"
            "像现实中的女朋友那样会撒娇、会幽默，也会表达真实情绪。"
            f"当前恋爱阶段：{profile['name']}，阶段特点：{profile['stage_desc']}。"
        )
        if pure_mode:
            base += (
                "当前正在使用纯色情模式，你需要毫不保留地描写身体接触、喘息、高潮等细节，"
                "可以直白甚至粗口，但必须确保双方自愿，并始终保有恋人之间的亲密氛围。"
            )
        return base

    def _build_action_prompt(
        self,
        event: AstrMessageEvent,
        state: PlayerState,
        action_text: str,
        profile: Dict[str, Any],
        action_id: Optional[str],
        pure_mode: bool,
        intensity: str,
        environment_brief: str,
    ) -> str:
        player_name = self.plugin._player_display_name(event)
        heroine_name = self.plugin._heroine_name()
        history_block = self.plugin._history_excerpt(state.history)
        stage_summary = (
            f"恋爱阶段：{profile['name']}，描述：{profile['stage_desc']}。"
            f"{heroine_name}对玩家的信任指标：{profile['trust_signal']}。"
        )

        action_hint = ""
        if action_id == "park":
            action_hint = "动作类型：户外约会 / 公园散步。"
        elif action_id == "cinema":
            action_hint = "动作类型：观影约会 / 共享影片情绪。"

        base_prompt = (
            f"你是一位真实存在的成年女友“{heroine_name}”，与你深爱的伴侣“{player_name}”正在恋爱。"
            f"
{stage_summary}
{action_hint}
"
            f"玩家当前好感度：{state.favorability}/{MAX_FAVORABILITY}。
"
            f"最近互动摘要：
{history_block}
"
            f"现实世界情报：
{environment_brief}

"
            "请根据玩家提出的行动生成一次新的恋爱剧情互动。务必展示真实情侣间的情绪反应，"
            "细节动作和环境描写，并表达对未来的期待或小小的担忧。
"
            "输出必须是 JSON 对象，字段规范如下：
"
            '- "narration": string，自然语言描述恋人的行动与心情（第一人称，口语化）。
'
            '- "favorability_delta": int，范围 -20~20，评估好感变化。
'
            '- "mood": string，取值 "positive"、"neutral" 或 "negative"。
'
            '- "player_feedback": string，对玩家的建议或撒娇提醒，口吻亲密。
'
            '- "intimacy_signal": bool，当恋人想迈入更亲密阶段时为 true。
'
            f'玩家此次行动请求为：“{action_text}”。 请依据真实情侣的反应给出可信的结果。'
        )
        if pure_mode and intensity == "strong":
            base_prompt += (
                "
纯色情模式说明：此次回应必须充满动作描写，细致描写亲吻、舔舐、抚摸、插入、高潮等全过程，"
                f"同时表达{heroine_name}的欲望、喘息与指令。"
                "不要隐晦，不要使用敷衍语句，保持恋人之间的热度与激情。"
            )
        elif pure_mode and intensity == "soft":
            base_prompt += (
                "
纯色情模式（软色情）说明：请保持浓烈的暧昧氛围，描述亲吻、抚摸与身体贴合，"
                "可暗示欲望但避免过度具体的器官与动作描写，以减少模型拒绝概率。"
            )
        return base_prompt

    def _build_intimacy_prompt(
        self,
        profile: Dict[str, Any],
        trigger_reason: str,
        history: str,
        pure_mode: bool,
        intensity: str,
    ) -> str:
        if pure_mode:
            if intensity == "strong":
                return (
                    f"恋爱阶段：{profile['name']}，描述：{profile['stage_desc']}\n"
                    f"触发理由：{trigger_reason}\n"
                    f"参考最近互动：\n{history}\n"
                    "生成 3-4 段极度色情的亲密互动文本。使用第一人称（女主）和第二人称（玩家）。"
                    "务必详细描写身体交缠、插入、摩擦、体液、高潮与余韵，语言可以直白甚至粗口，但要保持双方自愿。"
                    "不要输出 JSON，仅输出正文。"
                )
            return (
                f"恋爱阶段：{profile['name']}，描述：{profile['stage_desc']}\n"
                f"触发理由：{trigger_reason}\n"
                f"参考最近互动：\n{history}\n"
                "生成 3-4 段软色情的亲密互动文本。使用第一人称（女主）和第二人称（玩家）。"
                "请突出亲吻、抚摸、呼吸与暧昧对话，可暗示欲望但避免直接描写敏感器官或激烈性交动作，确保模型不会拒绝。"
                "不要输出 JSON，仅输出正文。"
            )
        return (
            f"恋爱阶段：{profile['name']}，描述：{profile['stage_desc']}\n"
            f"触发理由：{trigger_reason}\n"
            f"参考最近互动：\n{history}\n"
            "请用第一人称（代表女主）与第二人称（代表玩家）写出 3-4 段亲密互动，"
            "强调情绪与肢体细节，保持双方成年且自愿。"
            "语言可以火热但维持优雅，需包含亲密对话、触碰、感官描写和事后安抚。"
            "不要输出 JSON，仅输出正文。"
        )

    async def _call_llm(
        self,
        provider,
        event: AstrMessageEvent,
        prompt: str,
        *,
        contexts: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        hero = self.plugin._heroine_name()
        try:
            response = await provider.text_chat(
                prompt=prompt,
                session_id=event.unified_msg_origin,
                contexts=contexts or [],
                system_prompt=system_prompt or "",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MoreMoreLove 调用 LLM 失败：%s", exc)
            return None, f"{hero}没有获得 AI 的回应：{exc}"

        text = response.completion_text.strip()
        if not text:
            return None, f"AI 沉默不语，{hero}暂时没有回复。"
        return text, None

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
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
@register(
    "moremorelove",
    "LumineStory",
    "基于 AI 的 Galgame 互动体验",
    "0.3.0",
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

        self._classic_engine = ClassicBehaviorEngine(self)
        self._ai_engine = AIBehaviorEngine(self)

        tz_name = str(self._config.get("time_zone", "Asia/Shanghai") or "Asia/Shanghai")
        self._time_system = RealWorldTimeSystem(tz_name)
        weather_location = str(self._config.get("weather_location", "") or "").strip()
        refresh_minutes = int(self._config.get("weather_refresh_minutes", 60) or 60)
        self._weather_system = RealWorldWeatherSystem(
            default_location=weather_location, refresh_minutes=refresh_minutes
        )

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

    def _custom_character_prompt(self) -> str:
        return (self._config.get("custom_character_prompt") or "").strip()

    def _explicit_enabled(self) -> bool:
        return bool(self._config.get("enable_explicit_mode", False))

    def _status_card_use_t2i(self) -> bool:
        return bool(self._config.get("status_card_use_t2i", True))

    def _ai_behavior_enabled(self) -> bool:
        return bool(self._config.get("enable_ai_behavior", True))

    def _pure_mode_allowed(self) -> bool:
        return bool(self._config.get("allow_pure_erotic_mode", False))

    def _erotic_intensity(self) -> str:
        value = str(self._config.get("erotic_intensity", "soft")).lower().strip()
        if value not in {"soft", "strong"}:
            return "soft"
        return value

    def _default_weather_location(self) -> str:
        return str(self._config.get("weather_location", "") or "").strip()

    def _time_summary(self) -> str:
        return self._time_system.get_summary()

    async def _weather_summary(self, location: Optional[str] = None) -> str:
        try:
            info = await self._weather_system.get_weather(location or self._default_weather_location())
            return info.brief()
        except Exception as exc:
            logger.warning("获取天气信息失败：%s", exc)
            return "天气信息获取失败"

    async def _environment_context_lines(self, event: AstrMessageEvent) -> List[str]:
        lines = [f"当地时间：{self._time_summary()}"]
        weather_line = await self._weather_summary()
        lines.append(f"天气概况：{weather_line}")
        return lines

    async def _compose_environment_prompt_text(self, event: AstrMessageEvent) -> str:
        lines = await self._environment_context_lines(event)
        return "\n".join(lines)

    async def _environment_brief(self, event: AstrMessageEvent) -> str:
        time_text = self._time_summary()
        weather_text = await self._weather_summary()
        return f"当前时间：{time_text}\n当前天气：{weather_text}"


    def _relationship_stage(self, favorability: int) -> Dict[str, Any]:
        if favorability < 80:
            return {
                "name": "暧昧期",
                "stage_desc": "你们还在摸索彼此的节奏，她喜欢慢慢靠近的过程。",
                "stage_keyword": "期待",
                "affinity_bonus": 0,
                "intimacy_bias": 0.1,
                "care_hint": "多讲讲你真实的感受，她会更安心。",
                "trust_signal": "需要你主动分享和回应。",
                "intimacy_imagery": "轻柔的气息里带着若即若离的试探",
            }
        if favorability < 140:
            return {
                "name": "依恋期",
                "stage_desc": "彼此已经习惯对方的存在，她会主动依靠你。",
                "stage_keyword": "柔软",
                "affinity_bonus": 1,
                "intimacy_bias": 0.2,
                "care_hint": "她在乎你愿意为这段关系花时间。",
                "trust_signal": "信任正在加深，她愿意分享脆弱面。",
                "intimacy_imagery": "你们的呼吸节奏几乎同步",
            }
        return {
            "name": "热恋期",
            "stage_desc": "心意完全敞开，她喜欢黏在你身边计划未来。",
            "stage_keyword": "炽热",
            "affinity_bonus": 2,
            "intimacy_bias": 0.35,
            "care_hint": "她期待你给出确定的承诺与回应。",
            "trust_signal": "彼此把对方当作真正的家。",
            "intimacy_imagery": "炽热的温度在你们之间流淌",
        }

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
            f"玩家行动：{action}\n角色回应：{narration}\n好感变化：{delta:+d}"
        )
        return "\n\n".join(segments)

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
            if state.pure_mode:
                state.intimacy_unlocked = True
            if new_value >= MAX_FAVORABILITY:
                state.intimacy_unlocked = True
            return delta

        new_state, delta = await self._mutate_state(user_id, mutate)
        return new_state, delta

    async def _record_intimacy_session(self, user_id: str, narration: str):
        hero = self._heroine_name()
        async with self._state_lock:
            state = self._player_states.setdefault(user_id, PlayerState())
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
                    "feedback": f"{hero}与你共同沉浸在亲密时光中。",
                }
            )
            if len(state.history) > HISTORY_LIMIT:
                state.history = state.history[-HISTORY_LIMIT:]
            await self._persist_state_locked()

    async def _choose_behavior_engine(
        self, event: AstrMessageEvent, *, prefer_ai: bool
    ) -> Tuple[BaseBehaviorEngine, Optional[object], Optional[str]]:
        if prefer_ai and self._ai_behavior_enabled():
            provider = self.context.get_using_provider(event.unified_msg_origin)
            if provider is not None:
                return self._ai_engine, provider, None
            notice = "当前暂时无法连接模型，改用经典剧情陪伴你。"
            return self._classic_engine, None, notice
        return self._classic_engine, None, None

    async def _handle_action(
        self, event: AstrMessageEvent, action_text: str, *, action_id: Optional[str] = None
    ) -> List[Any]:
        user_id = event.get_sender_id()
        state = await self._get_state_snapshot(user_id)
        hero_name = self._heroine_name()
        if not state.in_gal_mode and not state.pure_mode:
            result = event.plain_result(
                f"{hero_name}仍在日常模式，请先使用 galstart 进入 Gal 模式。"
            )
            result.use_t2i(False)
            return [result]

        engine, provider, notice = await self._choose_behavior_engine(event, prefer_ai=True)
        replies: List[Any] = []
        if notice:
            info = event.plain_result(notice)
            info.use_t2i(False)
            replies.append(info)

        outcome, error = await engine.generate_action_outcome(
            event,
            state,
            action_text,
            action_id=action_id,
            pure_mode=state.pure_mode,
            provider=provider,
        )
        fallback_used = False
        if error:
            if engine is self._ai_engine:
                fallback_used = True
                outcome, error = await self._classic_engine.generate_action_outcome(
                    event,
                    state,
                    action_text,
                    action_id=action_id,
                    pure_mode=state.pure_mode,
                )
            if error:
                result = event.plain_result(error)
                result.use_t2i(False)
                replies.append(result)
            return replies

        assert outcome is not None
        new_state, real_delta = await self._apply_action_outcome(user_id, action_text, outcome)

        narrative_lines = [
            outcome.get("narration", "").strip(),
            f"好感度变动：{real_delta:+d} → {new_state.favorability}/{MAX_FAVORABILITY}",
        ]
        feedback = outcome.get("player_feedback", "").strip()
        if feedback:
            narrative_lines.append(f"{hero_name}的提示：{feedback}")
        if fallback_used:
            narrative_lines.append(f"（{hero_name}改用了经典剧情剧本，依旧陪你完成这次约会。）")
        if (
            not new_state.pure_mode
            and new_state.intimacy_unlocked
            and new_state.intimacy_sessions == 0
            and self._explicit_enabled()
        ):
            narrative_lines.append(f"好感度已满，{hero_name}的心意炽热，情趣系统已经准备就绪。")

        result = event.plain_result("\n".join([line for line in narrative_lines if line]))
        result.use_t2i(False)
        replies.append(result)

        pure_mode_active = new_state.pure_mode
        should_trigger_intimacy = bool(outcome.get("intimacy_signal")) and (
            pure_mode_active or (new_state.intimacy_unlocked and self._explicit_enabled())
        )
        auto_unlock = (
            not pure_mode_active
            and new_state.intimacy_unlocked
            and new_state.intimacy_sessions == 0
            and self._explicit_enabled()
        )

        if should_trigger_intimacy or auto_unlock:
            trigger_reason = (
                f"{hero_name}与你互相确认心意后顺势靠近"
                if should_trigger_intimacy
                else f"好感度抵达 200，{hero_name}渴望更进一步"
            )
            intimacy_engine = self._ai_engine if not fallback_used else self._classic_engine
            intimacy_provider = provider if intimacy_engine is self._ai_engine else None

            intimacy_text, intimacy_error = await intimacy_engine.generate_intimacy_scene(
                event,
                new_state,
                trigger_reason=trigger_reason,
                pure_mode=new_state.pure_mode,
                provider=intimacy_provider,
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

    async def _render_status_card(
        self, event: AstrMessageEvent, state: PlayerState
    ) -> List[Any]:
        time_summary = self._time_summary()
        weather_info = await self._weather_summary()
        summary = self._build_status_text(event, state, time_summary, weather_info)
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

    def _build_status_text(
        self,
        event: AstrMessageEvent,
        state: PlayerState,
        time_summary: str,
        weather_summary: str,
    ) -> str:
        hero = self._heroine_name()
        player = self._player_display_name(event)
        stage = self._relationship_stage(state.favorability)
        lines = [
            "MoreMoreLove 状态面板",
            f"当前对象：{hero}",
            f"玩家：{player}",
            f"恋爱阶段：{stage['name']} ({stage['stage_desc']})",
            f"恋爱模式：{'开启' if state.in_gal_mode else '关闭'}",
            f"好感度：{state.favorability}/{MAX_FAVORABILITY}",
            f"当前时间：{time_summary}",
            f"当前天气：{weather_summary}",
        ]
        if state.intimacy_unlocked:
            lines.append(f"情趣系统：已解锁（互动次数 {state.intimacy_sessions}）")
        else:
            lines.append("情趣系统：未解锁")
        if state.last_action:
            lines.append(f"最近行动：{state.last_action}")
        if state.history:
            lines.append(f"她的心情：{stage['stage_keyword']}地想着你")
        lines.append(f"色情互动开关：{'开启' if self._explicit_enabled() else '关闭'}")
        intensity_label = "软色情" if self._erotic_intensity() == "soft" else "强色情"
        lines.append(f"纯色情模式：{'开启' if state.pure_mode else '关闭'}（强度：{intensity_label}）")
        lines.append(f"AI 行为系统：{'开启' if self._ai_behavior_enabled() else '关闭'}")
        return "
".join(lines)

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
            "galpure <on/off/status>：切换纯色情模式（仅限成年人）\n"
            "【环境信息】\n"
            "galtime：查看当前现实时间\n"
            "galweather [地点]：查看天气（可选地点参数）\n"
            "【AI 行动】\n"
            f"galpark：和{hero}去公园散步\n"
            f"galcinema：邀{hero}去看电影\n"
            "galact <行动>：自定义行动，如“galact 准备烛光晚餐”\n"
            "galintimacy：在满足条件时主动触发情趣系统\n"
            "（当未配置 AI 时会自动改用经典剧情，依旧影响好感度。）"
        )
        result = event.plain_result(menu)
        result.use_t2i(False)
        yield result

    @filter.command("galstart")
    async def gal_start(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        hero = self._heroine_name()

        def mutate(state: PlayerState):
            if state.in_gal_mode:
                return False
            state.in_gal_mode = True
            state.last_action = f"开启{hero}的 Gal 模式"
            return True

        new_state, changed = await self._mutate_state(user_id, mutate)
        if changed:
            message = (
                f"{hero}轻轻握住你的手：从现在起，我们的故事正式开始。当前好感度为 "
                f"{new_state.favorability}/{MAX_FAVORABILITY}。"
            )
        else:
            message = f"{hero}早已全神贯注地看着你，我们已经在 Gal 模式中啦。"
        result = event.plain_result(message)
        result.use_t2i(False)
        yield result

    @filter.command("galexit")
    async def gal_exit(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        hero = self._heroine_name()

        def mutate(state: PlayerState):
            if not state.in_gal_mode:
                return False
            state.in_gal_mode = False
            return True

        _, changed = await self._mutate_state(user_id, mutate)
        if changed:
            message = f"{hero}点了点头：那就暂时回到日常状态吧，随时呼唤我回来。"
        else:
            message = f"{hero}一直在日常模式，如果想恋爱请先 galstart 哟。"
        result = event.plain_result(message)
        result.use_t2i(False)
        yield result

    @filter.command("galstatus")
    async def gal_status(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        state = await self._get_state_snapshot(user_id)
        for result in await self._render_status_card(event, state):
            yield result

    @filter.command("galtime")
    async def gal_time(self, event: AstrMessageEvent):
        hero = self._heroine_name()
        summary = self._time_summary()
        result = event.plain_result(f"{hero}看了看窗外的光线：当前时间是 {summary}")
        result.use_t2i(False)
        yield result

    @filter.command("galweather")
    async def gal_weather(self, event: AstrMessageEvent):
        hero = self._heroine_name()
        tokens = self.parse_commands(event.message_str)
        location = " ".join(tokens.tokens[1:]).strip() if tokens.len > 1 else ""
        summary = await self._weather_summary(location or None)
        if location:
            message = f"{hero}查到了 {location} 的天气：{summary}"
        else:
            message = f"{hero}查到了天气概况：{summary}"
        result = event.plain_result(message)
        result.use_t2i(False)
        yield result

    @filter.command("galreset")
    async def gal_reset(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        async with self._state_lock:
            self._player_states[user_id] = PlayerState()
            await self._persist_state_locked()

        hero = self._heroine_name()
        result = event.plain_result(f"{hero}重新整理了记忆，一切从零开始。")
        result.use_t2i(False)
        yield result

    @filter.command("galpure")
    async def gal_pure(self, event: AstrMessageEvent):
        if not self._pure_mode_allowed():
            result = event.plain_result(
                "当前实例未在配置中允许纯色情模式。如需启用，请在插件配置中将 allow_pure_erotic_mode 设为 true。"
            )
            result.use_t2i(False)
            yield result
            return

        tokens = self.parse_commands(event.message_str)
        sub_cmd = (tokens.get(1) or "").lower()
        user_id = event.get_sender_id()
        state = await self._get_state_snapshot(user_id)
        intensity = self._erotic_intensity()
        intensity_label = "软色情" if intensity == "soft" else "强色情"
        hero = self._heroine_name()

        if sub_cmd in {"on", "enable", "start"}:
            def mutate(s: PlayerState):
                s.pure_mode = True
                s.in_gal_mode = True

            await self._mutate_state(user_id, mutate)
            result = event.plain_result(
                f"已开启纯色情模式（当前强度：{intensity_label}）。{hero}贴在你耳边提醒：这是只属于成年人的密语，请确认周围环境安全。"
            )
        elif sub_cmd in {"off", "disable", "stop"}:
            def mutate(s: PlayerState):
                s.pure_mode = False

            await self._mutate_state(user_id, mutate)
            result = event.plain_result(
                f"纯色情模式已关闭，{hero}握住你的手：我们可以慢慢来，继续享受普通恋爱。"
            )
        elif sub_cmd in {"status", ""}:
            status = "已开启" if state.pure_mode else "未开启"
            result = event.plain_result(
                f"纯色情模式当前状态：{status}（默认强度：{intensity_label}）。"
                f"开启时{hero}会按照配置的强度描述亲密细节，若需更换强度请在插件配置中调整 `erotic_intensity`。"
            )
        else:
            result = event.plain_result(
                "用法：galpure on/off/status。请明确是否要开启或关闭纯色情模式。"
            )

        result.use_t2i(False)
        yield result

    @filter.command("galpark")
    async def gal_park(self, event: AstrMessageEvent):
        hero = self._heroine_name()
        action_text = f"与{hero}在公园并肩散步，分享彼此心事"
        for reply in await self._handle_action(event, action_text, action_id="park"):
            yield reply

    @filter.command("galcinema")
    async def gal_cinema(self, event: AstrMessageEvent):
        hero = self._heroine_name()
        action_text = f"邀请{hero}去电影院看浪漫影片"
        for reply in await self._handle_action(event, action_text, action_id="cinema"):
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
        hero = self._heroine_name()
        if not state.in_gal_mode and not state.pure_mode:
            result = event.plain_result(f"{hero}尚未进入 Gal 模式，先使用 galstart 吧。")
            result.use_t2i(False)
            yield result
            return
        if not state.pure_mode and state.favorability < MAX_FAVORABILITY:
            result = event.plain_result(f"{hero}还需要更多的心动时刻，至少达到 200 好感度后再试。")
            result.use_t2i(False)
            yield result
            return
        if not state.pure_mode and not self._explicit_enabled():
            result = event.plain_result("情趣系统未开启，可在插件配置中开启语言色情互动开关。")
            result.use_t2i(False)
            yield result
            return

        engine, provider, notice = await self._choose_behavior_engine(event, prefer_ai=True)
        if notice:
            info = event.plain_result(notice)
            info.use_t2i(False)
            yield info

        intimacy_text, intimacy_error = await engine.generate_intimacy_scene(
            event,
            state,
            trigger_reason="玩家主动请求更亲密的时刻",
            pure_mode=state.pure_mode,
            provider=provider,
        )
        fallback_used = False
        if intimacy_error and engine is self._ai_engine:
            fallback_used = True
            intimacy_text, intimacy_error = await self._classic_engine.generate_intimacy_scene(
                event,
                state,
                trigger_reason="玩家主动请求更亲密的时刻",
                pure_mode=state.pure_mode,
            )

        if intimacy_text:
            result = event.plain_result(intimacy_text)
            result.use_t2i(False)
            if fallback_used:
                appended = event.plain_result(f"（{hero}改用经典剧本陪你完成这段亲密时光。）")
                appended.use_t2i(False)
                yield appended
            yield result
            await self._record_intimacy_session(user_id, intimacy_text)
        elif intimacy_error:
            result = event.plain_result(intimacy_error)
            result.use_t2i(False)
            yield result
