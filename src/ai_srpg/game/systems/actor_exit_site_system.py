"""离开地点：从地点回到大地图上地点所在的那一格，无论在里面走得多深。

地点对外只占一格，所以离开地点不需要「先走到入口」——落点固定是地点所在的格。
"""

from typing import Dict, List, final, override

from loguru import logger

from ...entitas import Entity, GroupEvent, Matcher, ReactiveProcessor
from ...models import (
    ActorComponent,
    ActorExitedSite,
    ActorExitSiteAction,
    MapPositionComponent,
)
from ..context import SRPGGame
from ..entities.action_rules import action_blocker
from ..entities.queries import get_map_position, get_map_stage, get_site
from .location_change_mixin import LocationChangeMixin


@final
class ActorExitSiteSystem(ReactiveProcessor, LocationChangeMixin):
    """消费 ``ActorExitSiteAction``：摘掉地点归属，站到地点所在格。"""

    ##########################################################################################
    def __init__(self, game: SRPGGame) -> None:
        ReactiveProcessor.__init__(self, game)
        LocationChangeMixin.__init__(self, game)

    ##########################################################################################
    @override
    def get_trigger(self) -> Dict[Matcher, GroupEvent]:
        return {Matcher(all_of=[ActorExitSiteAction, ActorComponent]): GroupEvent.ADDED}

    ##########################################################################################
    @override
    def filter(self, entity: Entity) -> bool:
        """只处理仍挂着动作的角色：动作在处理的同一刻被消费。"""
        return entity.has(ActorComponent, ActorExitSiteAction)

    ##########################################################################################
    @override
    async def react(self, entities: List[Entity]) -> None:
        for entity in sorted(entities, key=lambda item: item.index):
            self._exit(entity)

    ##########################################################################################
    def _exit(self, entity: Entity) -> None:
        action = entity.get(ActorExitSiteAction)
        entity.remove(ActorExitSiteAction)
        blocker = action_blocker(self._game, entity, action)
        if blocker is not None:
            logger.warning(f"{entity.name} 的离开地点被拒绝: {blocker}")
            return

        site = get_site(self._game, entity)
        assert site is not None, f"{entity.name} 在地点里却没有地点"
        map_stage = get_map_stage(self._game, site.name)
        _, position = get_map_position(self._game, entity)

        to_label = f"{map_stage.name}({position.x},{position.y})"
        event = ActorExitedSite(
            message=f"你从{site.name}走到{to_label}。",
            actor=entity.name,
            stage=map_stage.name,
            site=site.name,
        )
        self.announce_departure(
            entity, stage=site, from_label=site.name, agent_event=event
        )

        entity.replace(ActorComponent, map_stage.name)
        entity.replace(MapPositionComponent, position.x, position.y)

        self.announce_arrival(
            entity, stage=map_stage, to_label=to_label, agent_event=event
        )
        self.record_journey(
            entity, from_label=site.name, to_label=to_label, agent_event=event
        )
        self.publish(event)


###############################################################################
__all__ = ["ActorExitSiteSystem"]
