"""角色等待：告诉同一处的人他没有动。

等待也有信息量——「什么都没发生」与「没人在」是两件事。大地图不是场所，没有可告知的
对象，所以站在大地图上的等待只是「这一轮没动」，不产生广播。
"""

from typing import Dict, List, final, override

from ...entitas import Entity, GroupEvent, Matcher, ReactiveProcessor
from ...models import ActorComponent, ActorWaitAction, ActorWaited
from ..context import SRPGGame
from ..entities.queries import get_site, is_on_map, resolve_stage_entity
from .stage_broadcast_mixin import StageBroadcastMixin


@final
class ActorWaitSystem(ReactiveProcessor, StageBroadcastMixin):
    """消费 ``ActorWaitAction``：在所在地广播一条「留在原地」。"""

    ##########################################################################################
    def __init__(self, game: SRPGGame) -> None:
        ReactiveProcessor.__init__(self, game)
        StageBroadcastMixin.__init__(self, game)

    ##########################################################################################
    @override
    def get_trigger(self) -> Dict[Matcher, GroupEvent]:
        return {Matcher(all_of=[ActorWaitAction, ActorComponent]): GroupEvent.ADDED}

    ##########################################################################################
    @override
    def filter(self, entity: Entity) -> bool:
        """只处理仍挂着动作的角色：动作在处理的同一刻被消费。"""
        return entity.has(ActorComponent, ActorWaitAction)

    ##########################################################################################
    @override
    async def react(self, entities: List[Entity]) -> None:
        for entity in sorted(entities, key=lambda item: item.index):
            entity.remove(ActorWaitAction)
            stage_entity = resolve_stage_entity(self._game, entity)
            assert stage_entity is not None, f"{entity.name} 无所在舞台"
            site = get_site(self._game, entity)
            event = ActorWaited(
                message=f"{entity.name}留在原地。",
                actor=entity.name,
                stage=stage_entity.name,
                site=site.name if site is not None else None,
            )
            if not is_on_map(self._game, entity):
                # 大地图不是场所：没有可告知的对象，但「这轮没动」仍是发生过的事
                self.broadcast_at_stage(stage_entity, event, exclude_entities={entity})
            self.publish(event)


###############################################################################
__all__ = ["ActorWaitSystem"]
