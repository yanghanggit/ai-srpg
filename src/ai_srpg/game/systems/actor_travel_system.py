"""大地图移动：在大地图上走到相邻一格，只改坐标，不改变所在层。

走到地点所在的格子不算进入地点——那只是站在地点上，进入地点要靠 ``enter``。
"""

from typing import Dict, List, final, override

from loguru import logger

from ...entitas import Entity, GroupEvent, Matcher, ReactiveProcessor
from ...models import (
    ActorComponent,
    ActorTravelAction,
    ActorTraveled,
    MapPositionComponent,
)
from ..context import SRPGGame
from ..entities.action_rules import action_blocker
from ..entities.queries import get_map_position
from .location_change_mixin import LocationChangeMixin


@final
class ActorTravelSystem(ReactiveProcessor, LocationChangeMixin):
    """消费 ``ActorTravelAction``：校验相邻、改坐标、说给三处听。"""

    ##########################################################################################
    def __init__(self, game: SRPGGame) -> None:
        ReactiveProcessor.__init__(self, game)
        LocationChangeMixin.__init__(self, game)

    ##########################################################################################
    @override
    def get_trigger(self) -> Dict[Matcher, GroupEvent]:
        return {Matcher(all_of=[ActorTravelAction, ActorComponent]): GroupEvent.ADDED}

    ##########################################################################################
    @override
    def filter(self, entity: Entity) -> bool:
        """只处理仍挂着动作的角色：动作在处理的同一刻被消费。"""
        return entity.has(ActorComponent, ActorTravelAction)

    ##########################################################################################
    @override
    async def react(self, entities: List[Entity]) -> None:
        for entity in sorted(entities, key=lambda item: item.index):
            self._travel(entity)

    ##########################################################################################
    def _travel(self, entity: Entity) -> None:
        action = entity.get(ActorTravelAction)
        entity.remove(ActorTravelAction)
        blocker = action_blocker(self._game, entity, action)
        if blocker is not None:
            logger.warning(f"{entity.name} 的大地图移动被拒绝: {blocker}")
            return

        target = (action.x, action.y)
        from_label = self.map_label(entity)
        map_stage = get_map_position(self._game, entity)[0]
        event = ActorTraveled(
            message=f"你从{from_label}走到{map_stage.name}({target[0]},{target[1]})。",
            actor=entity.name,
            stage=map_stage.name,
            x=target[0],
            y=target[1],
        )
        self.announce_departure(
            entity, stage=map_stage, from_label=from_label, agent_event=event
        )

        entity.replace(MapPositionComponent, target[0], target[1])

        to_label = self.map_label(entity)
        self.announce_arrival(
            entity, stage=map_stage, to_label=to_label, agent_event=event
        )
        self.record_journey(
            entity, from_label=from_label, to_label=to_label, agent_event=event
        )
        self.publish(event)


###############################################################################
__all__ = ["ActorTravelSystem"]
