"""收集器跨 execute 存活，动作只活一次 pass：每轮边界必须对齐一次。

group 在成员组件被替换时先派发 removed 再派发 added，于是「处理完自己」的 system
会把自己重新塞进收集器；这条回声只能在下一轮 execute 被看到。而那时动作已经被
``ActionCleanupSystem`` 清掉——不清理收集器，下一轮就会拿到悬空的动作引用。
"""

from typing import Type, TypeVar

import pytest

from ai_srpg.game.lifecycle import initialize_pipeline
from ai_srpg.game.pipelines.runner import process_pipeline
from ai_srpg.game.systems.actor_speak_system import ActorSpeakSystem
from ai_srpg.game.systems.actor_travel_system import ActorTravelSystem
from ai_srpg.game.systems.actor_wait_system import ActorWaitSystem
from ai_srpg.models import ActorTravelAction, ActorWaitAction, MapPositionComponent
from world_fixture import WANDERER, build_world, entity

_Processor = TypeVar("_Processor")


def _system_of(game: object, wanted: Type[_Processor]) -> _Processor:
    """从 pipeline 里取出某个 system 实例：断言它自己那份收集器。"""
    pipeline = game.pipeline  # type: ignore[attr-defined]
    for processor in pipeline._execute_processors:
        if isinstance(processor, wanted):
            return processor
    raise AssertionError(f"pipeline 里没有 {wanted.__name__}")


async def test_collectors_are_empty_after_a_pass() -> None:
    """移动会替换 ActorComponent，从而把实体重新塞回收集器；pass 结束时必须清空。"""
    game = build_world()
    await initialize_pipeline(game)
    actor = entity(game, WANDERER)
    system = _system_of(game, ActorTravelSystem)

    actor.replace(ActorTravelAction, 1, 2)
    await process_pipeline(game.pipeline, None)

    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (1, 2)
    assert system._collector.collected_entities == set()


async def test_second_pass_does_not_see_the_stale_action() -> None:
    """动作被清理后，残留的收集项不该让第二轮再去取那个已不存在的动作。"""
    game = build_world()
    await initialize_pipeline(game)
    actor = entity(game, WANDERER)

    actor.replace(ActorTravelAction, 1, 2)
    await process_pipeline(game.pipeline, None)
    await process_pipeline(game.pipeline, None)

    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (1, 2)


async def test_collector_is_cleared_even_when_the_pass_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失败路径同样对齐：否则回滚后的下一轮会拿到幽灵实体。"""
    game = build_world()
    await initialize_pipeline(game)
    wait_system = _system_of(game, ActorWaitSystem)
    entity(game, WANDERER).replace(ActorWaitAction)

    async def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("前面的 system 炸了")

    monkeypatch.setattr(ActorSpeakSystem, "execute", _boom)
    with pytest.raises(RuntimeError):
        await process_pipeline(game.pipeline, None)

    # ActorWaitSystem 收到了动作却没能执行；收集器在失败路径上也要清空
    assert wait_system._collector.collected_entities == set()
