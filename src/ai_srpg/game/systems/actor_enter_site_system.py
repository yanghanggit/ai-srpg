"""进入地点：从地点所在的那一格走进去。落点永远是地点入口，与内部多深无关。

地点对外只占一格，所以进入地点只有一种结果：``current_stage`` 变成地点，
自己的坐标被摘掉。
"""

from typing import Dict, List, final, override

from loguru import logger

from ...entitas import Entity, GroupEvent, Matcher, ReactiveProcessor
from ...models import (
    ActorComponent,
    ActorEnteredSite,
    ActorEnterSiteAction,
    MapPositionComponent,
)
from ..context import SRPGGame
from ..entities.action_rules import action_blocker
from ..entities.queries import get_map_position, get_stage_entity
from .location_change_mixin import LocationChangeMixin


@final
class ActorEnterSiteSystem(ReactiveProcessor, LocationChangeMixin):
    """消费 ``ActorEnterSiteAction``：站在地点所在格才能进入。"""

    ##########################################################################################
    def __init__(self, game: SRPGGame) -> None:
        ReactiveProcessor.__init__(self, game)
        LocationChangeMixin.__init__(self, game)

    ##########################################################################################
    @override
    def get_trigger(self) -> Dict[Matcher, GroupEvent]:
        return {
            Matcher(all_of=[ActorEnterSiteAction, ActorComponent]): GroupEvent.ADDED
        }

    ##########################################################################################
    @override
    def filter(self, entity: Entity) -> bool:
        """只处理仍挂着动作的角色：动作在处理的同一刻被消费。"""
        return entity.has(ActorComponent, ActorEnterSiteAction)

    ##########################################################################################
    @override
    async def react(self, entities: List[Entity]) -> None:
        for entity in sorted(entities, key=lambda item: item.index):
            self._enter(entity)

    ##########################################################################################
    def _enter(self, entity: Entity) -> None:
        action = entity.get(ActorEnterSiteAction)
        entity.remove(ActorEnterSiteAction)
        blocker = action_blocker(self._game, entity, action)
        if blocker is not None:
            logger.warning(f"{entity.name} 的进入地点被拒绝: {blocker}")
            return

        site = get_stage_entity(self._game, action.site)
        assert site is not None
        map_stage = get_map_position(self._game, entity)[0]
        from_label = self.map_label(entity)
        event = ActorEnteredSite(
            message=f"你从{from_label}走到{site.name}。",
            actor=entity.name,
            stage=site.name,
            site=site.name,
        )
        self.announce_departure(
            entity, stage=map_stage, from_label=from_label, agent_event=event
        )

        entity.replace(ActorComponent, site.name)
        if entity.has(MapPositionComponent):
            entity.remove(MapPositionComponent)

        self.announce_arrival(entity, stage=site, to_label=site.name, agent_event=event)
        self.record_journey(
            entity, from_label=from_label, to_label=site.name, agent_event=event
        )
        self.publish(event)


###############################################################################
__all__ = ["ActorEnterSiteSystem"]
