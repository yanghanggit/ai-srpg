"""手动压缩也走 pipeline：挂动作、跑一次 pass、失败自动回滚。

压缩改的是记忆，因此和其它改变状态的操作一样，只能在 pipeline 里发生——这里只负责
把「压缩这个实体」这个动作挂上去，并回报折叠前后的规模。
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from ..entitas import Entity
from ..game.context import SRPGGame
from ..game.memory import get_agent_memory
from ..game.systems.compact_system import DEFAULT_COMPACT_SUMMARY
from ..gameplay.offline import load_or_create_game, run_offline_pass
from ..models import CompactAction, SystemMessage


@dataclass(frozen=True)
class CompactContextOutcome:
    entity_name: str
    before_messages: int
    after_messages: int
    before_ratio: float
    after_ratio: float
    snapshot_id: int


###############################################################################
async def compact_context_game(
    user: str,
    game: str,
    target: str,
    snapshot_id: Optional[int],
    *,
    summary: str = DEFAULT_COMPACT_SUMMARY,
) -> CompactContextOutcome:
    """给目标实体挂压缩动作，跑一次 pass，回来后报告折叠前后的规模。"""
    srpg_game = await load_or_create_game(user, game, snapshot_id=snapshot_id)
    entity = srpg_game.get_entity_by_name(target)
    if entity is None:
        raise LookupError(f"找不到实体: {target!r}")
    _require_compactable(srpg_game, entity)

    before_messages, before_ratio = _size(srpg_game, entity)
    entity.replace(CompactAction, summary)
    outcome = await run_offline_pass(srpg_game, user)
    after_messages, after_ratio = _size(srpg_game, entity)
    return CompactContextOutcome(
        entity_name=target,
        before_messages=before_messages,
        after_messages=after_messages,
        before_ratio=before_ratio,
        after_ratio=after_ratio,
        snapshot_id=outcome.snapshot_id,
    )


###############################################################################
def _require_compactable(srpg_game: SRPGGame, entity: Entity) -> None:
    """提前报错，而不是让 pipeline 跑一趟却什么都没发生。"""
    messages = get_agent_memory(srpg_game, entity).messages
    if not messages:
        raise ValueError(f"实体 {entity.name!r} 没有 agent 记忆可压缩")
    if not isinstance(messages[0], SystemMessage):
        raise ValueError(f"实体 {entity.name!r} 的首条记忆不是 SystemMessage")


###############################################################################
def _size(srpg_game: SRPGGame, entity: Entity) -> Tuple[int, float]:
    memory = get_agent_memory(srpg_game, entity)
    return len(memory.messages), memory.context_usage_ratio


###############################################################################
__all__ = ["CompactContextOutcome", "compact_context_game"]
