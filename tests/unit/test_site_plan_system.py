"""地点内的计划：看到区域、环境、在场者与相邻区域，只能发起地点内的动作。"""

from typing import Any, Dict, List

import pytest

from ai_srpg.game.systems.site_plan_system import SitePlanSystem, site_plan_prompt
from ai_srpg.llm import AgentLoopResult
from ai_srpg.models import (
    ActorExitSiteAction,
    ActorMoveWithinSiteAction,
    ActorPlanAction,
    ActorSpeakAction,
    ActorTravelAction,
    ActorWaitAction,
)
from ai_srpg.utils import get_prompt_builders
from world_fixture import (
    CAMP,
    CAMP_ENVIRONMENT,
    FIRE_ROOM,
    HERE,
    MAP,
    OTHER,
    SENTRY,
    TOWER,
    WANDERER,
    build_world,
    entity,
)


def _capture(monkeypatch: pytest.MonkeyPatch) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> AgentLoopResult:
        calls.append(dict(kwargs))
        messages = kwargs["messages"]
        return AgentLoopResult(
            success=True,
            start_index=len(messages),
            end_index=len(messages),
            messages=messages,
        )

    monkeypatch.setattr("ai_srpg.game.systems.actor_plan_mixin.agent_loop", _fake)
    return calls


def _planner(game: Any, *actor_names: str) -> SitePlanSystem:
    """先开收集器再挂计划动作：动作的 ADDED 才是触发事件。"""
    system = SitePlanSystem(game)
    system.activate()
    for name in actor_names:
        entity(game, name).replace(ActorPlanAction)
    return system


###############################################################################
# 谁在这一层计划
###############################################################################
async def test_only_actors_inside_a_site_are_planned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, HERE, WANDERER)

    await system.execute()

    assert [call["name"] for call in calls] == [f"plan:{HERE}"]


async def test_planned_actors_run_in_creation_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, OTHER, HERE)

    await system.execute()

    assert [call["name"] for call in calls] == [f"plan:{HERE}", f"plan:{OTHER}"]


###############################################################################
# 看到什么
###############################################################################
async def test_prompt_has_area_environment_and_present_actors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, HERE)

    await system.execute()

    (call,) = calls
    message = call["input_message"]
    assert f"当前区域：{CAMP}" in message
    assert CAMP_ENVIRONMENT in message
    assert OTHER in message
    assert WANDERER not in message  # 大地图上的人不在场


async def test_prompt_lists_adjacent_areas_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """可去之处是子区域与父区域；另一个地点不在其中。"""
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, HERE)

    await system.execute()

    (call,) = calls
    message = call["input_message"]
    assert FIRE_ROOM in message
    assert TOWER not in message
    assert MAP not in message.split("可去之处：")[1].split("用工具")[0]


async def test_prompt_says_no_destination_when_there_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """哨塔没有子区域、父是大地图，所以可去之处写「无」，不留一个空标题。"""
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, SENTRY)

    await system.execute()

    (call,) = calls
    assert "可去之处：\n- 无" in call["input_message"]


async def test_prompt_builder_is_registered() -> None:
    builders = get_prompt_builders()
    assert any(builder is site_plan_prompt for builder in builders.values())


###############################################################################
# 能发起什么
###############################################################################
async def test_site_tools_are_the_site_verbs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, HERE)

    await system.execute()

    (call,) = calls
    names = [tool.function.name for tool in call["tools"]]
    assert names == ["speak", "move_within", "exit", "wait"]
    assert [tool.function.name for tool in call["terminal_tools"]] == names


async def test_handlers_mount_actions_and_keep_one_per_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, HERE)

    await system.execute()

    (call,) = calls
    actor = entity(game, HERE)
    handlers = call["handlers"]

    assert handlers["speak"](content="风变了。") == "（已记下）"
    assert actor.get(ActorSpeakAction).content == "风变了。"
    assert "忽略" in str(handlers["exit"]())
    assert not actor.has(ActorExitSiteAction)


async def test_move_within_handler_carries_the_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, HERE)

    await system.execute()

    (call,) = calls
    call["handlers"]["move_within"](destination=FIRE_ROOM)

    assert entity(game, HERE).get(ActorMoveWithinSiteAction).destination == FIRE_ROOM


async def test_travel_action_is_not_allowed_in_this_layer() -> None:
    """大地图动词不能从地点内部层的处理器挂上——层级边界在代码里守住。"""
    game = build_world()
    system = SitePlanSystem(game)

    with pytest.raises(ValueError):
        system.mount_action(entity(game, HERE), ActorTravelAction, 3, 3)


async def test_wait_handler_mounts_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, HERE)

    await system.execute()

    (call,) = calls
    call["handlers"]["wait"]()

    assert entity(game, HERE).has(ActorWaitAction)
