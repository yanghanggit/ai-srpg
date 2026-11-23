"""记忆压缩：消费 ``CompactAction``，把目标实体的历史折叠成一条摘要。

压缩改的是记忆，因此走 pipeline：失败自动回滚到 pass 前，不在半压缩的状态上继续。
它不发领域事件——这不是世界里发生的事，没有听众，也不该进任何人的记忆。
"""

from typing import Dict, List, final, override

from loguru import logger

from ...entitas import Entity, GroupEvent, Matcher, ReactiveProcessor
from ...models import CompactAction, HumanMessage, SystemMessage
from ..context import SRPGGame
from ..memory import compact_agent_memory, get_agent_memory
from .system_mixin import SystemMixin

#: 未指定摘要时的折叠文本
DEFAULT_COMPACT_SUMMARY = "（上下文已手动压缩，此前的对话在此折叠。）"


@final
class CompactSystem(ReactiveProcessor, SystemMixin):
    """把挂上压缩动作的实体的记忆折叠一次。"""

    ##########################################################################################
    def __init__(self, game: SRPGGame) -> None:
        ReactiveProcessor.__init__(self, game)
        SystemMixin.__init__(self, game)

    ##########################################################################################
    @override
    def get_trigger(self) -> Dict[Matcher, GroupEvent]:
        return {Matcher(all_of=[CompactAction]): GroupEvent.ADDED}

    ##########################################################################################
    @override
    def filter(self, entity: Entity) -> bool:
        """只处理仍挂着动作的实体：动作在处理的同一刻被消费。"""
        return entity.has(CompactAction)

    ##########################################################################################
    @override
    async def react(self, entities: List[Entity]) -> None:
        for entity in sorted(entities, key=lambda item: item.index):
            action = entity.get(CompactAction)
            entity.remove(CompactAction)
            messages = get_agent_memory(self._game, entity).messages
            if not messages or not isinstance(messages[0], SystemMessage):
                logger.warning(f"{entity.name} 没有可压缩的记忆，跳过")
                continue
            summary = action.summary or DEFAULT_COMPACT_SUMMARY
            compact_agent_memory(self._game, entity, HumanMessage(content=summary))


###############################################################################
__all__ = ["CompactSystem", "DEFAULT_COMPACT_SUMMARY"]
