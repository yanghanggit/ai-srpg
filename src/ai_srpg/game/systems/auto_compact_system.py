"""自动压缩：记忆占满到阈值，就替它挂上压缩动作。

阈值是玩法策略，不是机制：这里只决定「谁的记忆该折一次」，怎么折仍由
``CompactSystem`` 负责。两个 system 分开，是为了让「何时压」可以随玩法改，
而「怎么压」保持唯一。

它在计划系统之前运行，于是压缩发生在「这一轮开始时的记忆状态」上——本轮新产生的
消息不会被当轮吞掉。
"""

from typing import Final, final, override

from loguru import logger

from ...entitas import Entity, ExecuteProcessor
from ...models import CompactAction
from ..memory import get_agent_memory
from .system_mixin import SystemMixin

#: 上下文占比超过它就该压；这个数属于运营口径，等玩法规则定
COMPACT_THRESHOLD: Final[float] = 0.6

#: 少于这个条数的记忆压了也没意义（首条 system + 摘要都不止一条）
_MIN_MESSAGES: Final[int] = 4


@final
class AutoCompactSystem(SystemMixin, ExecuteProcessor):
    """每轮检查一次记忆满度，超阈值就挂上压缩动作。"""

    ##########################################################################################################
    @override
    async def execute(self) -> None:
        for entity in self._crowded():
            if entity.has(CompactAction):
                continue
            logger.info(
                f"{entity.name} 的上下文占比 {get_agent_memory(self._game, entity).context_usage_ratio:.2%}，安排压缩"
            )
            entity.replace(CompactAction, "")

    ##########################################################################################################
    def _crowded(self) -> list[Entity]:
        """超过阈值且确实有可折叠内容的实体；顺序按实体下标，便于重放。"""
        crowded: list[Entity] = []
        for name, memory in self._game.agent_memory_store.snapshot().items():
            if memory.context_usage_ratio < COMPACT_THRESHOLD:
                continue
            if len(memory.messages) <= _MIN_MESSAGES:
                continue
            entity = self._game.get_entity_by_name(name)
            if entity is None:
                continue
            crowded.append(entity)
        return sorted(crowded, key=lambda item: item.index)


###############################################################################
__all__ = ["AutoCompactSystem", "COMPACT_THRESHOLD"]
