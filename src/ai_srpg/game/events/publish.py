"""事件投递与发布：投递决定「谁听见」，发布决定「记下发生过什么」。

向哪个范围投递属于系统层，由 ``game/systems`` 里的 mixin 解析；这里只管投递本身，
不认识舞台、角色与广播范围。

两者分开是因为它们不是一回事：一次位置变化要说给旧处、新处和自己三处听，但那只是
一次搬运的事实。投递可以有很多份，事件只发布一次。
"""

from typing import Any, Dict, Iterable, Mapping, Optional, Set

from ...entitas import Entity
from ...models import AnyAgentEvent, HumanMessage
from ..context import SRPGGame
from ..memory.access import add_human_message


#################################################################################################################################################
def publish_event(srpg_game: SRPGGame, agent_event: AnyAgentEvent) -> None:
    """把一个领域事件交给游戏的事件出口（默认实现直接丢弃）。"""
    srpg_game.events.publish(agent_event)


#################################################################################################################################################
def deliver_entities(
    srpg_game: SRPGGame,
    entities: Set[Entity],
    agent_event: AnyAgentEvent,
    *,
    broadcast_stage: Optional[str] = None,
) -> None:
    """向指定实体投递事件消息（不发布事件）。

    ``broadcast_stage`` 只由全舞台广播传入，用于在记忆里标记广播范围；私发不传，
    消息上就不会出现这个标记。
    """
    _append_messages(srpg_game, entities, agent_event, broadcast_stage=broadcast_stage)


#################################################################################################################################################
def deliver_entities_by_stage(
    srpg_game: SRPGGame,
    entities_by_stage: Mapping[str, Set[Entity]],
    agent_event: AnyAgentEvent,
) -> None:
    """按舞台分组投递：每条消息带自己所在舞台的标记。

    跨舞台的广播（例如按距离波及若干地点）不该变成多条领域事件——范围只是它被谁听见。
    """
    for stage_name, entities in entities_by_stage.items():
        _append_messages(srpg_game, entities, agent_event, broadcast_stage=stage_name)


#################################################################################################################################################
def _append_messages(
    srpg_game: SRPGGame,
    entities: Iterable[Entity],
    agent_event: AnyAgentEvent,
    *,
    broadcast_stage: Optional[str] = None,
) -> None:
    """把事件写进每个实体的记忆，按实体创建顺序写入以保持可重放。"""
    for entity in sorted(entities, key=lambda item: item.index):
        # 只在广播时带上标记：``extra="allow"`` 会把它留在消息的额外属性里，
        # 传 None 会写进词表之外的「存在但为空」状态，因此按需展开
        extra: Dict[str, Any] = (
            {"broadcast_stage": broadcast_stage} if broadcast_stage is not None else {}
        )
        add_human_message(
            srpg_game,
            entity,
            HumanMessage(
                content=agent_event.message,
                agent_event=agent_event.type,
                **extra,
            ),
        )


###############################################################################
__all__ = [
    "deliver_entities",
    "deliver_entities_by_stage",
    "publish_event",
]
