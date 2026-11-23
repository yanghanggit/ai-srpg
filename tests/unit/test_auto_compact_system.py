"""自动压缩：满度到阈值才挂动作；压不压是策略，怎么压是机制。"""

from typing import Any

from ai_srpg.game.context import SRPGGame
from ai_srpg.game.memory import get_agent_memory, insert_messages
from ai_srpg.game.systems.auto_compact_system import (
    COMPACT_THRESHOLD,
    AutoCompactSystem,
)
from ai_srpg.game.systems.compact_system import CompactSystem
from ai_srpg.models import AIMessage, CompactAction, HumanMessage
from world_fixture import HERE, OTHER, build_world, entity


def _fill(game: SRPGGame, name: str, ratio: float, turns: int = 3) -> None:
    """写入若干消息，最后一条 AI 消息带上上下文占比。"""
    actor = entity(game, name)
    messages: list[Any] = []
    for index in range(turns):
        messages.append(HumanMessage(content=f"第 {index} 句"))
        messages.append(AIMessage(content=f"第 {index} 答", context_usage_ratio=ratio))
    insert_messages(game, actor, len(get_agent_memory(game, actor).messages), messages)


def _system(game: SRPGGame) -> AutoCompactSystem:
    """每轮执行一次的 system，不需要订阅触发器。"""
    return AutoCompactSystem(game)


###############################################################################
async def test_crowded_memory_gets_a_compaction_action() -> None:
    game = build_world()
    _fill(game, HERE, ratio=COMPACT_THRESHOLD + 0.1)
    system = _system(game)

    await system.execute()

    assert entity(game, HERE).has(CompactAction)


async def test_roomy_memory_is_left_alone() -> None:
    game = build_world()
    _fill(game, HERE, ratio=COMPACT_THRESHOLD - 0.1)
    system = _system(game)

    await system.execute()

    assert not entity(game, HERE).has(CompactAction)


async def test_exactly_at_the_threshold_counts_as_crowded() -> None:
    game = build_world()
    _fill(game, HERE, ratio=COMPACT_THRESHOLD)
    system = _system(game)

    await system.execute()

    assert entity(game, HERE).has(CompactAction)


async def test_only_the_crowded_ones_get_actions() -> None:
    game = build_world()
    _fill(game, HERE, ratio=0.9)
    _fill(game, OTHER, ratio=0.1)
    system = _system(game)

    await system.execute()

    assert entity(game, HERE).has(CompactAction)
    assert not entity(game, OTHER).has(CompactAction)


async def test_short_memory_is_not_worth_compacting() -> None:
    """只有一两条消息时压了也没意义：摘要本身就要占一条。"""
    game = build_world()
    actor = entity(game, HERE)
    insert_messages(
        game,
        actor,
        len(get_agent_memory(game, actor).messages),
        [AIMessage(content="一句", context_usage_ratio=0.99)],
    )
    system = _system(game)

    await system.execute()

    assert not actor.has(CompactAction)


async def test_already_scheduled_memory_is_not_mounted_twice() -> None:
    game = build_world()
    _fill(game, HERE, ratio=0.9)
    actor = entity(game, HERE)
    actor.replace(CompactAction, "（已有的摘要）")
    system = _system(game)

    await system.execute()

    assert actor.get(CompactAction).summary == "（已有的摘要）"


###############################################################################
# 与消费者配合：同一 pass 内先挂后折
###############################################################################
async def test_action_is_consumed_in_the_same_pass() -> None:
    game = build_world()
    _fill(game, HERE, ratio=0.95)
    actor = entity(game, HERE)
    before = len(get_agent_memory(game, actor).messages)
    auto = _system(game)
    consumer = CompactSystem(game)
    consumer.activate()

    await auto.execute()
    await consumer.execute()

    memory = get_agent_memory(game, actor)
    assert len(memory.messages) == 2
    assert len(memory.messages) < before
    assert memory.context_usage_ratio == 0.0
    assert not actor.has(CompactAction)


async def test_batch_insert_keeps_the_ratio_signal() -> None:
    """agent_loop 走批量插入，占比信号必须跟着走，否则阈值永远看不到满度。"""
    game = build_world()
    _fill(game, HERE, ratio=0.42)

    assert get_agent_memory(game, entity(game, HERE)).context_usage_ratio == 0.42
