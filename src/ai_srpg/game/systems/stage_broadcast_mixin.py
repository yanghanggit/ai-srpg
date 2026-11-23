"""位置广播：地点内只到当前区域，大地图只到同一格。

广播只负责「谁听见」——投递事件消息，不发布领域事件。事件由发起这件事的 system
发布一次，广播可以有多个方向。

地点内部的事件不沿区域树扩散，在哪个区域发生就只告诉那个区域。大地图是坐标系，
不是整张图共享的场所：站在同一格才算同一处，格上的事件也不会传给旁边的地点。
"""

from typing import Optional, Set

from ...entitas import Entity
from ...models import AnyAgentEvent
from ..entities import (
    get_actors_in_map_cell,
    get_actors_in_stage,
    is_map_stage,
    resolve_stage_entity,
)
from ..events.publish import deliver_entities
from .domain_event_mixin import DomainEventMixin


class StageBroadcastMixin(DomainEventMixin):
    """按位置广播事件：地点内按区域，大地图上按格。"""

    ############################################################################################################
    def broadcast_in_region(
        self,
        region: Entity,
        agent_event: AnyAgentEvent,
        *,
        exclude_entities: Optional[Set[Entity]] = None,
    ) -> None:
        """向地点内的当前区域投递：区域实体与直接在该区域的角色。

        不向父区域、子区域或大地图扩散。
        """
        region_entity = resolve_stage_entity(self._game, region)
        assert region_entity is not None, f"{region.name} 无所在舞台，无法广播"
        assert not is_map_stage(
            region_entity
        ), f"{region_entity.name} 是大地图，不能作为区域广播"
        targets = get_actors_in_stage(self._game, region_entity) | {region_entity}
        self._deliver(targets, agent_event, region_entity.name, exclude_entities)

    ############################################################################################################
    def broadcast_in_map_cell(
        self,
        entity: Entity,
        agent_event: AnyAgentEvent,
        *,
        exclude_entities: Optional[Set[Entity]] = None,
    ) -> None:
        """向大地图上与 ``entity`` 同一格的 actor 投递。

        大地图实体本身不接收；不向相邻格、相邻地点或地点内部扩散。
        """
        map_stage = resolve_stage_entity(self._game, entity)
        assert map_stage is not None, f"{entity.name} 无所在舞台，无法广播"
        assert is_map_stage(map_stage), f"{entity.name} 不在大地图上，不能按格广播"
        targets = get_actors_in_map_cell(self._game, entity)
        self._deliver(targets, agent_event, map_stage.name, exclude_entities)

    ############################################################################################################
    def _deliver(
        self,
        targets: Set[Entity],
        agent_event: AnyAgentEvent,
        broadcast_stage: str,
        exclude_entities: Optional[Set[Entity]],
    ) -> None:
        """投递到目标集合；空集合不产生任何消息。"""
        excluded = exclude_entities or set()
        targets = targets - excluded
        if not targets:
            return
        deliver_entities(
            self._game, targets, agent_event, broadcast_stage=broadcast_stage
        )


###############################################################################
__all__ = ["StageBroadcastMixin"]
