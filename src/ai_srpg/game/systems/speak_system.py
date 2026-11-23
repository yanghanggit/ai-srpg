"""角色说话：把话告诉同一个区域里的人。

说话是「场所里的事」：大地图不是场所，所以站在大地图上的角色不开口。
"""

from typing import Dict, List, final, override

from loguru import logger

from ...entitas import Entity, GroupEvent, Matcher, ReactiveProcessor
from ...models import ActorComponent, ActorSpoke, SpeakAction
from ..context import SRPGGame
from ..entities.action_rules import action_blocker
from ..entities.queries import get_site, resolve_stage_entity
from .stage_broadcast_mixin import StageBroadcastMixin


@final
class SpeakSystem(ReactiveProcessor, StageBroadcastMixin):
    """消费 ``SpeakAction``：在所在区域里广播这句话。"""

    ##########################################################################################
    def __init__(self, game: SRPGGame) -> None:
        ReactiveProcessor.__init__(self, game)
        StageBroadcastMixin.__init__(self, game)

    ##########################################################################################
    @override
    def get_trigger(self) -> Dict[Matcher, GroupEvent]:
        return {Matcher(all_of=[SpeakAction, ActorComponent]): GroupEvent.ADDED}

    ##########################################################################################
    @override
    def filter(self, entity: Entity) -> bool:
        """只处理仍挂着动作的角色：动作在处理的同一刻被消费。"""
        return entity.has(ActorComponent, SpeakAction)

    ##########################################################################################
    @override
    async def react(self, entities: List[Entity]) -> None:
        for entity in sorted(entities, key=lambda item: item.index):
            action = entity.get(SpeakAction)
            entity.remove(SpeakAction)
            blocker = action_blocker(self._game, entity, action)
            if blocker is not None:
                logger.warning(f"{entity.name} 的说话被拒绝: {blocker}")
                continue
            stage_entity = resolve_stage_entity(self._game, entity)
            assert stage_entity is not None, f"{entity.name} 无所在舞台"
            content = action.content
            site = get_site(self._game, entity)
            assert site is not None, f"{entity.name} 在地点之外，不能说话"
            event = ActorSpoke(
                message=f"{entity.name}说：{content}",
                actor=entity.name,
                stage=stage_entity.name,
                site=site.name,
                content=content,
            )
            self.broadcast_in_region(stage_entity, event, exclude_entities={entity})
            self.publish(event)


###############################################################################
__all__ = ["SpeakSystem"]
