"""游戏领域事件：发生了什么。

事件是「发生了一件事」的最小描述，同时也是它在别人记忆里的那句话（``message``）。
结构化字段供审计、回放与会话历史使用，``message`` 供 agent 记忆使用——两者出自同一
个对象，所以记忆里说的话与事件里记的字段不会走散。

动作与事件一一对应：一个行为动作在同一次 pass 里产生一个事件。位置变化会被三处听见，
但事件只发布一次：投递范围是「谁听见」，事件是「谁做了什么」。

空间字段只有两个口径：``stage`` 是事件发生所在的舞台（结果位置），``site`` 是事件所属的
地点；大地图上的事件没有 ``site``。
"""

from typing import Annotated, Literal, Optional, Tuple, Union, final

from pydantic import BaseModel, ConfigDict, Field


class AgentEvent(BaseModel):
    """事件基类（抽象）：只声明公共字段，不直接实例化；具体事件继承它并把 type 收窄为 Literal。"""

    model_config = ConfigDict(extra="forbid")

    type: str
    message: str


@final
class NoneEvent(AgentEvent):
    """未分类事件：兜底形态（type = "none"）"""

    type: Literal["none"] = "none"


@final
class StagePulse(AgentEvent):
    """舞台脉动：此刻某个区域里有哪些角色。"""

    type: Literal["stage_pulse"] = "stage_pulse"
    stage: str
    actors: Tuple[str, ...]


@final
class ActorSpoke(AgentEvent):
    """角色在所在区域里说了一句话。"""

    type: Literal["actor_spoke"] = "actor_spoke"
    actor: str
    stage: str
    site: str
    content: str


@final
class ActorWaited(AgentEvent):
    """角色这一轮没有动。``stage`` 是它当时所在的舞台；``site`` 为所在地点。"""

    type: Literal["actor_waited"] = "actor_waited"
    actor: str
    stage: str
    site: Optional[str] = None


@final
class ActorTraveled(AgentEvent):
    """角色在大地图上走到某一格。"""

    type: Literal["actor_traveled"] = "actor_traveled"
    actor: str
    stage: str
    x: int
    y: int


@final
class ActorEnteredSite(AgentEvent):
    """角色走进脚下这个地点，落到地点入口。"""

    type: Literal["actor_entered_site"] = "actor_entered_site"
    actor: str
    stage: str
    site: str


@final
class ActorExitedSite(AgentEvent):
    """角色离开地点，回到大地图上地点所在的那一格。"""

    type: Literal["actor_exited_site"] = "actor_exited_site"
    actor: str
    stage: str
    site: str


@final
class ActorMovedWithinSite(AgentEvent):
    """角色在地点内部从一处区域走到另一处。"""

    type: Literal["actor_moved_within_site"] = "actor_moved_within_site"
    actor: str
    stage: str
    site: str


AnyAgentEvent = Annotated[
    Union[
        NoneEvent,
        StagePulse,
        ActorSpoke,
        ActorWaited,
        ActorTraveled,
        ActorEnteredSite,
        ActorExitedSite,
        ActorMovedWithinSite,
    ],
    Field(discriminator="type"),
]

###############################################################################
__all__ = [
    "ActorEnteredSite",
    "ActorExitedSite",
    "ActorMovedWithinSite",
    "ActorSpoke",
    "ActorTraveled",
    "ActorWaited",
    "AgentEvent",
    "AnyAgentEvent",
    "NoneEvent",
    "StagePulse",
]
