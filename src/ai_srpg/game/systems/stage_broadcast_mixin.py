"""舞台广播：地点只影响自己，大地图按格距波及一片。

广播只负责「谁听见」——投递事件消息，不发布领域事件。事件由发起这件事的 system
发布一次，广播可以有多个方向。

只有地点内部能收到「在场者」这类区域广播。大地图是坐标系，没有「在场者」这回事，
向它广播等于把一条区域事件当成整张地图的事实。需要按格距影响多个地点时走
``broadcast_over_map``：以锚点的大地图坐标为中心，选中若干地点（连同其整棵子树），
事件仍然只发布一次。
"""

from typing import Dict, List, Optional, Set, Tuple

from ...entitas import Entity
from ...models import AnyAgentEvent, MapPosition, MapPositionComponent
from ..entities import (
    get_actors_in_stage,
    get_child_stages,
    get_map_position,
    is_map_stage,
    resolve_stage_entity,
)
from ..events.publish import deliver_entities, deliver_entities_by_stage
from .domain_event_mixin import DomainEventMixin


class StageBroadcastMixin(DomainEventMixin):
    """向舞台广播事件的 mixin：地点一份，大地图一片。"""

    ############################################################################################################
    def broadcast_at_stage(
        self,
        stage: Entity,
        agent_event: AnyAgentEvent,
        *,
        exclude_entities: Optional[Set[Entity]] = None,
    ) -> None:
        """向一个舞台投递：地点/区域发给在场者与舞台本身，大地图只发给大地图自己。

        大地图不是场所：站在同一张图上不等于站在同一处，所以格上的其他角色不在此列。
        ``exclude_entities`` 用于「说话者自己不必收到自己的话」这类场景。
        """
        stage_entity = resolve_stage_entity(self._game, stage)
        assert stage_entity is not None, f"{stage.name} 无所在舞台，无法广播"
        excluded = exclude_entities or set()
        if is_map_stage(stage_entity):
            targets = {stage_entity} - excluded
        else:
            targets = (
                get_actors_in_stage(self._game, stage_entity) | {stage_entity}
            ) - excluded
        deliver_entities(
            self._game, targets, agent_event, broadcast_stage=stage_entity.name
        )

    ############################################################################################################
    def broadcast_over_map(
        self,
        entity: Entity,
        agent_event: AnyAgentEvent,
        *,
        radius: Optional[int] = 1,
        exclude_entities: Optional[Set[Entity]] = None,
    ) -> None:
        """以 ``entity`` 的大地图坐标为原点，波及 ``radius`` 格以内的地点及其子树。

        距离取切比雪夫距离（八方向 ``max(|dx|, |dy|)``）：大地图上「几格以内」的直觉即
        此，斜向相邻也算一格；``radius=0`` 只覆盖原点所在的那一处。

        ``radius=None`` 表示全图，此时原点可以是大地图本身（它没有坐标）。无论范围
        多大，事件只发布一次，每条消息带自己所在舞台的标记。
        """
        assert radius is None or radius >= 0, f"广播半径不能为负数: {radius}"
        excluded = exclude_entities or set()
        map_stage, position = self._anchor_of(entity, radius)
        targets = self._targets_by_stage(map_stage, position, radius, excluded)
        deliver_entities_by_stage(self._game, targets, agent_event)

    ############################################################################################################
    def _anchor_of(
        self, entity: Entity, radius: Optional[int]
    ) -> Tuple[Entity, MapPosition]:
        """把实体映射到「哪张大地图的哪一格」。

        角色在大地图上用自己的坐标，在地点里用地点所在的格；大地图本身没有坐标，
        只有全图广播（``radius=None``）才以它为原点。
        """
        stage_entity = resolve_stage_entity(self._game, entity)
        assert stage_entity is not None, f"{entity.name} 无所在舞台，无法广播"
        if is_map_stage(stage_entity):
            assert radius is None, f"{stage_entity.name} 没有坐标，只能做全图广播"
            return stage_entity, MapPosition(x=0, y=0)
        map_stage, position = get_map_position(self._game, entity)
        return map_stage, position

    ############################################################################################################
    def _targets_by_stage(
        self,
        map_stage: Entity,
        position: MapPosition,
        radius: Optional[int],
        excluded: Set[Entity],
    ) -> Dict[str, Set[Entity]]:
        """按舞台分组的投递目标：命中的地点及其子树，各自带上直接在场角色。"""
        targets: Dict[str, Set[Entity]] = {}
        for stage_entity in self._stages_in_range(map_stage, position, radius):
            group = targets.setdefault(stage_entity.name, set())
            group.add(stage_entity)
            group.update(get_actors_in_stage(self._game, stage_entity))

        for entities in targets.values():
            entities.difference_update(excluded)
        return {name: entities for name, entities in targets.items() if entities}

    ############################################################################################################
    def _stages_in_range(
        self,
        map_stage: Entity,
        position: MapPosition,
        radius: Optional[int],
    ) -> List[Entity]:
        """大地图的直接子舞台（地点）里落在范围内的，连同各自的整棵子树。"""
        hit: List[Entity] = []
        for child in get_child_stages(self._game, map_stage.name):
            if radius is not None and _distance(child, position) > radius:
                continue
            hit.append(child)
            hit.extend(self._descendants_of(child))
        return hit

    ############################################################################################################
    def _descendants_of(self, stage_entity: Entity) -> List[Entity]:
        """某舞台的整棵子树（先序），不含自己。"""
        found: List[Entity] = []
        for child in get_child_stages(self._game, stage_entity.name):
            found.append(child)
            found.extend(self._descendants_of(child))
        return found


###############################################################################
def _distance(entity: Entity, position: MapPosition) -> int:
    """切比雪夫距离：斜向相邻也算一格。"""
    own = entity.get(MapPositionComponent)
    return max(abs(own.x - position.x), abs(own.y - position.y))


###############################################################################
__all__ = ["StageBroadcastMixin"]
