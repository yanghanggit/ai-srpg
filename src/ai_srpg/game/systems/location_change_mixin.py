"""位置变化的告知：旧处看见他走、新处看见他来、他自己记得这条路线。

调用顺序即语义：离开按「此刻所在处」投递，必须在改组件之前发；到达按「新的所在处」，
之后发。大地图与地点的投递对象不同——大地图只投给同格的其他角色。

三处听到的说法不同，但它们是同一件事：所以传进来的是那条领域事件，这里只把它的
说法换成该听众该听到的那一版。事件本身由调用方发布一次。
"""

from typing import Set

from ...entitas import Entity
from ...models import AnyAgentEvent, HumanMessage
from ..entities.queries import get_map_position, is_map_stage, resolve_stage_entity
from ..memory import add_human_message
from .stage_broadcast_mixin import StageBroadcastMixin


class LocationChangeMixin(StageBroadcastMixin):
    """把一次位置变化说给三处听：旧处、新处、他自己。"""

    ############################################################################################################
    def announce_departure(
        self,
        entity: Entity,
        *,
        stage: Entity,
        from_label: str,
        agent_event: AnyAgentEvent,
    ) -> None:
        """旧处的在场者看见他离开；调用时角色还在原地。

        地点内按当前区域广播；大地图上按旧格广播。
        """
        self._broadcast_location(
            entity,
            stage=stage,
            agent_event=_saying(agent_event, f"{entity.name}离开了{from_label}。"),
            exclude_entities={entity},
        )

    ############################################################################################################
    def announce_arrival(
        self,
        entity: Entity,
        *,
        stage: Entity,
        to_label: str,
        agent_event: AnyAgentEvent,
    ) -> None:
        """新处的在场者看见他到来；调用时组件已经改好。

        地点内按新区域广播；大地图上按新格广播。
        """
        self._broadcast_location(
            entity,
            stage=stage,
            agent_event=_saying(agent_event, f"{entity.name}来到了{to_label}。"),
            exclude_entities={entity},
        )

    ############################################################################################################
    def _broadcast_location(
        self,
        entity: Entity,
        *,
        stage: Entity,
        agent_event: AnyAgentEvent,
        exclude_entities: Set[Entity],
    ) -> None:
        """按位置类型选择广播范围：地点内按区域，大地图上按格。"""
        if is_map_stage(stage):
            self.broadcast_in_map_cell(
                entity, agent_event, exclude_entities=exclude_entities
            )
        else:
            self.broadcast_in_region(
                stage, agent_event, exclude_entities=exclude_entities
            )

    ############################################################################################################
    def record_journey(
        self,
        entity: Entity,
        *,
        from_label: str,
        to_label: str,
        agent_event: AnyAgentEvent,
    ) -> None:
        """他自己记住从哪儿走到哪儿：别人的「他来了」不能替他回答这件事。"""
        add_human_message(
            self._game,
            entity,
            HumanMessage(
                content=f"你从{from_label}走到{to_label}。",
                agent_event=agent_event.type,
            ),
        )

    ############################################################################################################
    def map_label(self, entity: Entity) -> str:
        """大地图上的位置说法：「大地图(x,y)」；地点内部用区域名。"""
        stage_entity = resolve_stage_entity(self._game, entity)
        assert stage_entity is not None, f"{entity.name} 无所在舞台"
        if not is_map_stage(stage_entity):
            return stage_entity.name
        map_stage, position = get_map_position(self._game, entity)
        return f"{map_stage.name}({position.x},{position.y})"


###############################################################################
def _saying(agent_event: AnyAgentEvent, text: str) -> AnyAgentEvent:
    """同一件事的另一版说法：类型与字段不变，只换这句话。"""
    return agent_event.model_copy(update={"message": text})


###############################################################################
__all__ = ["LocationChangeMixin"]
