"""手动压缩走 pipeline：挂动作、system 折叠记忆、失败自动回滚。"""

from typing import Any

import pytest

from ai_srpg.game.context import SRPGGame
from ai_srpg.game.memory import get_agent_memory, insert_messages
from ai_srpg.game.systems.compact_system import (
    DEFAULT_COMPACT_SUMMARY,
    CompactSystem,
)
from ai_srpg.models import AIMessage, CompactAction, HumanMessage, SystemMessage
from world_fixture import HERE, build_world, entity


def _system(game: SRPGGame) -> CompactSystem:
    system = CompactSystem(game)
    system.activate()
    return system


def _fill(game: SRPGGame, turns: int = 3) -> None:
    actor = entity(game, HERE)
    messages: list[Any] = []
    for index in range(turns):
        messages.append(HumanMessage(content=f"第 {index} 句"))
        messages.append(AIMessage(content=f"第 {index} 答"))
    insert_messages(game, actor, len(get_agent_memory(game, actor).messages), messages)


###############################################################################
async def test_action_folds_history_into_one_summary() -> None:
    game = build_world()
    _fill(game)
    system = _system(game)
    before = len(get_agent_memory(game, entity(game, HERE)).messages)

    entity(game, HERE).replace(CompactAction, "")
    await system.execute()

    messages = get_agent_memory(game, entity(game, HERE)).messages
    assert len(messages) < before
    assert isinstance(messages[0], SystemMessage)
    assert messages[1].content == DEFAULT_COMPACT_SUMMARY
    assert not entity(game, HERE).has(CompactAction)


async def test_given_summary_is_the_one_written() -> None:
    game = build_world()
    _fill(game)
    system = _system(game)

    entity(game, HERE).replace(CompactAction, "（此前的谈话已折叠）")
    await system.execute()

    messages = get_agent_memory(game, entity(game, HERE)).messages
    assert messages[1].content == "（此前的谈话已折叠）"


async def test_failure_notices_survive_compaction() -> None:
    """带保留标记的消息不被折叠：一次失败的重试记录要留给下一轮看。"""
    game = build_world()
    _fill(game)
    actor = entity(game, HERE)
    insert_messages(
        game,
        actor,
        len(get_agent_memory(game, actor).messages),
        [HumanMessage(content="（上一次调用失败）", keep_on_compact=True)],
    )
    system = _system(game)

    entity(game, HERE).replace(CompactAction, "")
    await system.execute()

    contents = [
        message.content
        for message in get_agent_memory(game, entity(game, HERE)).messages
    ]
    assert "（上一次调用失败）" in contents


async def test_entity_without_memory_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """没有记忆可压时只告警，不抛异常：不该让整次 pass 失败。"""
    game = build_world()
    system = _system(game)
    target = entity(game, HERE)
    get_agent_memory(game, target).messages.clear()

    target.replace(CompactAction, "")
    await system.execute()

    assert not target.has(CompactAction)
    assert get_agent_memory(game, target).messages == []


async def test_system_is_registered_in_the_pipeline() -> None:
    """装配顺序决定它每轮都会跑；漏装就等于动作永远没人消费。"""
    game = build_world()

    assert any(
        isinstance(processor, CompactSystem)
        for processor in game.pipeline._execute_processors
    )
