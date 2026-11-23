"""大地图上的计划：看到脚下与相邻格，只能发起地图上的动作。"""

from typing import Any, Dict, List

import pytest

from ai_srpg.game.systems.map_plan_system import (
    MapPlanSystem,
    map_plan_input,
    map_plan_prompt,
)
from ai_srpg.llm import AgentLoopResult
from ai_srpg.models import (
    ActorComponent,
    EnterSiteAction,
    MapPositionComponent,
    PlanAction,
    SpeakAction,
    TravelAction,
    WaitAction,
)
from ai_srpg.utils import get_prompt_builders
from world_fixture import (
    CAMP,
    HERE,
    MAP,
    SENTRY,
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

    monkeypatch.setattr("ai_srpg.game.systems.plan_mixin.agent_loop", _fake)
    return calls


def _planner(game: Any, *actor_names: str) -> MapPlanSystem:
    system = MapPlanSystem(game)
    system.activate()
    for name in actor_names:
        entity(game, name).replace(PlanAction)
    return system


###############################################################################
# 谁在这一层计划
###############################################################################
async def test_only_actors_on_the_map_are_planned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, HERE, WANDERER)

    await system.execute()

    assert [call["name"] for call in calls] == [f"plan:{WANDERER}"]


###############################################################################
# 看到什么
###############################################################################
async def test_prompt_has_position_and_surrounding_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    message = call["input_message"]
    assert f"当前位置：({1},{1}) 空地" in message
    assert f"({2},{2}) {CAMP}" in message  # 相邻格上的地点
    assert f"({2},{1}) 空地" in message
    assert f"({3},{2})" not in message  # 两格之外不在视野里


async def test_map_has_no_environment_or_present_actors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """大地图不是场所：提示词里不出现环境与「在场角色」。"""
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    message = call["input_message"]
    assert "环境：" not in message
    assert "在场角色：" not in message


async def test_prompt_lists_the_actors_standing_on_a_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """格上的角色与格上的地点并排写出：一格可以是空地、地点，也可以站着人。"""
    game = build_world()
    sentry = entity(game, SENTRY)
    sentry.replace(ActorComponent, MAP)
    sentry.replace(MapPositionComponent, 2, 1)
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    assert f"({2},{1}) 空地，在场 {SENTRY}" in call["input_message"]


async def test_prompt_names_the_actors_on_the_same_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一格上的另一个人必须写出来，否则格上的人互相瞎。"""
    game = build_world()
    sentry = entity(game, SENTRY)
    sentry.replace(ActorComponent, MAP)
    sentry.replace(MapPositionComponent, 1, 1)
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    message = call["input_message"]
    assert f"与你同格：{SENTRY}" in message
    # 脚下是什么由位置行回答，不重复
    assert message.count(f"({1},{1})") == 1


async def test_prompt_says_nothing_about_the_same_cell_when_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    assert "与你同格" not in call["input_message"]


async def test_memory_keeps_the_actors_on_the_same_cell() -> None:
    """记忆里的压缩版同样保留同格的人：接管与自主都靠它。"""
    game = build_world()
    sentry = entity(game, SENTRY)
    sentry.replace(ActorComponent, MAP)
    sentry.replace(MapPositionComponent, 1, 1)

    compact = map_plan_input(game, entity(game, WANDERER), compact=True)

    assert f"与你同格：{SENTRY}" in compact
    assert "视野：" in compact


async def test_prompt_builder_is_registered() -> None:
    builders = get_prompt_builders()
    assert any(builder is map_plan_prompt for builder in builders.values())


###############################################################################
# 能发起什么
###############################################################################
async def test_map_tools_are_the_map_verbs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    names = [tool.function.name for tool in call["tools"]]
    assert names == ["travel", "enter", "wait"]
    assert [tool.function.name for tool in call["terminal_tools"]] == names


async def test_handlers_mount_actions_and_keep_one_per_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    actor = entity(game, WANDERER)
    handlers = call["handlers"]

    assert handlers["travel"](x=1, y=2) == "（已记下）"
    travel = actor.get(TravelAction)
    assert (travel.x, travel.y) == (1, 2)
    assert "忽略" in str(handlers["enter"](site=CAMP))
    assert not actor.has(EnterSiteAction)


async def test_enter_handler_carries_the_site_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    call["handlers"]["enter"](site=CAMP)

    assert entity(game, WANDERER).get(EnterSiteAction).site == CAMP


async def test_speak_is_not_allowed_in_this_layer() -> None:
    """说话是场所里的事，大地图层挂不上——层级边界在代码里守住。"""
    game = build_world()
    system = MapPlanSystem(game)

    with pytest.raises(ValueError):
        system.mount_action(entity(game, WANDERER), SpeakAction, "喂")


async def test_wait_handler_mounts_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    call["handlers"]["wait"]()

    assert entity(game, WANDERER).has(WaitAction)


###############################################################################
# 站在地点格上：当前位置要说明脚下是什么
###############################################################################
async def test_map_position_mentions_the_site_under_foot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    actor.replace(MapPositionComponent, 2, 2)
    calls = _capture(monkeypatch)
    system = _planner(game, WANDERER)

    await system.execute()

    (call,) = calls
    assert f"当前位置：({2},{2}) {CAMP}" in call["input_message"]
