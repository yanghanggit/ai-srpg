"""区域内移动：在地点内部从一个区域走到相邻区域。

可去的是子区域与父区域；父区域是大地图时不算——那是离开地点。
"""

from typing import Dict, List, final, override

from loguru import logger

from ...entitas import Entity, GroupEvent, Matcher, ReactiveProcessor
from ...models import (
    ActorComponent,
    ActorMovedWithinSite,
    ActorMoveWithinSiteAction,
)
from ..context import SRPGGame
from ..entities.action_rules import action_blocker
from ..entities.queries import get_site, get_stage_entity, resolve_stage_entity
from .location_change_mixin import LocationChangeMixin


@final
class ActorMoveWithinSiteSystem(ReactiveProcessor, LocationChangeMixin):
    """消费 ``ActorMoveWithinSiteAction``：校验相邻区域，改所在区域。"""

    ##########################################################################################
    def __init__(self, game: SRPGGame) -> None:
        ReactiveProcessor.__init__(self, game)
        LocationChangeMixin.__init__(self, game)

    ##########################################################################################
    @override
    def get_trigger(self) -> Dict[Matcher, GroupEvent]:
        return {
            Matcher(
                all_of=[ActorMoveWithinSiteAction, ActorComponent]
            ): GroupEvent.ADDED
        }

    ##########################################################################################
    @override
    def filter(self, entity: Entity) -> bool:
        """只处理仍挂着动作的角色：动作在处理的同一刻被消费。"""
        return entity.has(ActorComponent, ActorMoveWithinSiteAction)

    ##########################################################################################
    @override
    async def react(self, entities: List[Entity]) -> None:
        for entity in sorted(entities, key=lambda item: item.index):
            self._move(entity)

    ##########################################################################################
    def _move(self, entity: Entity) -> None:
        action = entity.get(ActorMoveWithinSiteAction)
        entity.remove(ActorMoveWithinSiteAction)
        blocker = action_blocker(self._game, entity, action)
        if blocker is not None:
            logger.warning(f"{entity.name} 的区域内移动被拒绝: {blocker}")
            return

        from_stage = resolve_stage_entity(self._game, entity)
        assert from_stage is not None, f"{entity.name} 无所在舞台"
        target = get_stage_entity(self._game, action.destination)
        assert target is not None, f"找不到舞台实体: {action.destination}"

        site = get_site(self._game, entity)
        assert site is not None, f"{entity.name} 在地点里却没有地点"
        event = ActorMovedWithinSite(
            message=f"你从{from_stage.name}走到{target.name}。",
            actor=entity.name,
            stage=target.name,
            site=site.name,
        )
        self.announce_departure(
            entity, stage=from_stage, from_label=from_stage.name, agent_event=event
        )

        entity.replace(ActorComponent, target.name)

        self.announce_arrival(
            entity, stage=target, to_label=target.name, agent_event=event
        )
        self.record_journey(
            entity, from_label=from_stage.name, to_label=target.name, agent_event=event
        )
        self.publish(event)


###############################################################################
__all__ = ["ActorMoveWithinSiteSystem"]
