"""接管：命令经由计划系统写记忆，形状与自主计划逐字一致。

命令只挂两个动作（「该想一次」+ 行为动作），计划系统在 pipeline 的原位看到已决定的
动作就不再问模型，只把决策写成三条消息。于是记忆顺序也一致：先有这一轮的环境与
在场者，再有自己的决定。
"""

from typing import Any, List

import pytest

from ai_srpg.game.command import mount_command
from ai_srpg.game.context import SRPGGame
from ai_srpg.game.memory import get_agent_memory
from ai_srpg.game.systems.actor_plan_mixin import ACK
from ai_srpg.game.systems.actor_speak_system import ActorSpeakSystem
from ai_srpg.game.systems.actor_travel_system import ActorTravelSystem
from ai_srpg.game.systems.map_plan_system import MapPlanSystem
from ai_srpg.game.systems.site_plan_system import SitePlanSystem
from ai_srpg.llm import AgentLoopResult
from ai_srpg.models import (
    ActorComponent,
    ActorEnterSiteAction,
    ActorPlanAction,
    ActorSpeakAction,
    ActorTravelAction,
    ActorWaitAction,
    AIMessage,
    ChatMessage,
    HumanMessage,
    MapPositionComponent,
    ToolMessage,
)
from world_fixture import (
    CAMP,
    CAMP_ENVIRONMENT,
    HERE,
    OTHER,
    WANDERER,
    build_world,
    entity,
    heard,
    said,
)


def _memory(game: SRPGGame, name: str) -> List[Any]:
    return list(get_agent_memory(game, entity(game, name)).messages)


def _planner(game: SRPGGame, plan_type: type) -> Any:
    system = plan_type(game)
    system.activate()
    return system


###############################################################################
# 接管 = 挂两个动作
###############################################################################
def test_mount_command_mounts_plan_and_behaviour() -> None:
    game = build_world()
    actor = entity(game, HERE)

    mount_command(game, actor, ActorSpeakAction(content="火还能撑多久？"))

    assert actor.has(ActorPlanAction)
    assert actor.get(ActorSpeakAction).content == "火还能撑多久？"


###############################################################################
# 计划系统只把决策写成记忆，不再问模型
###############################################################################
async def test_predecided_command_writes_the_three_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(**kwargs: Any) -> AgentLoopResult:
        raise AssertionError("接管时不应该再问模型")

    monkeypatch.setattr("ai_srpg.game.systems.actor_plan_mixin.agent_loop", _boom)
    game = build_world()
    system = _planner(game, SitePlanSystem)
    mount_command(game, entity(game, HERE), ActorSpeakAction(content="喂"))

    await system.execute()

    assert [type(message) for message in _memory(game, HERE)[1:]] == [
        HumanMessage,
        AIMessage,
        ToolMessage,
    ]


async def test_recorded_input_is_the_compressed_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """记忆里留摘要：环境收成一句、在场者只留名字。"""
    game = build_world()
    system = _planner(game, SitePlanSystem)
    mount_command(game, entity(game, HERE), ActorSpeakAction(content="喂"))

    await system.execute()

    recorded = _memory(game, HERE)[1]
    assert isinstance(recorded, HumanMessage)
    assert f"当前区域：{CAMP}" in recorded.content
    assert CAMP_ENVIRONMENT.split("。")[0] in recorded.content
    assert f"- {OTHER}\n" in recorded.content


async def test_recorded_tool_call_matches_the_action() -> None:
    game = build_world()
    system = _planner(game, MapPlanSystem)
    mount_command(game, entity(game, WANDERER), ActorTravelAction(x=1, y=2))

    await system.execute()

    ai_message = _memory(game, WANDERER)[2]
    assert isinstance(ai_message, AIMessage)
    call = ai_message.additional_kwargs["tool_calls"][0]
    assert call["function"]["name"] == "travel"
    assert call["function"]["arguments"] == '{"x": 1, "y": 2}'
    tool_message = _memory(game, WANDERER)[3]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.content == ACK
    assert tool_message.tool_call_id == call["id"]


async def test_enter_command_records_the_site_name() -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    actor.replace(MapPositionComponent, 2, 2)
    system = _planner(game, MapPlanSystem)
    mount_command(game, actor, ActorEnterSiteAction(site=CAMP))

    await system.execute()

    call = _memory(game, WANDERER)[2].additional_kwargs["tool_calls"][0]
    assert call["function"]["arguments"] == f'{{"site": "{CAMP}"}}'


async def test_wait_command_records_no_arguments() -> None:
    game = build_world()
    system = _planner(game, SitePlanSystem)
    mount_command(game, entity(game, HERE), ActorWaitAction())

    await system.execute()

    call = _memory(game, HERE)[2].additional_kwargs["tool_calls"][0]
    assert call["function"]["arguments"] == "{}"


###############################################################################
# 两条来源的记忆输入逐字相同
###############################################################################
async def test_plan_records_the_same_input_as_a_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake(**kwargs: Any) -> AgentLoopResult:
        messages: List[ChatMessage] = kwargs["messages"]
        start = len(messages)
        start_message = HumanMessage(content=kwargs["input_message"])
        messages.append(start_message)
        return AgentLoopResult(
            success=True,
            start_index=start,
            end_index=len(messages),
            messages=messages,
            start_message=start_message,
        )

    monkeypatch.setattr("ai_srpg.game.systems.actor_plan_mixin.agent_loop", _fake)
    planned = build_world()
    system = _planner(planned, SitePlanSystem)
    entity(planned, HERE).replace(ActorPlanAction)
    await system.execute()

    commanded = build_world()
    command_system = _planner(commanded, SitePlanSystem)
    mount_command(commanded, entity(commanded, HERE), ActorSpeakAction(content="喂"))
    await command_system.execute()

    assert _memory(planned, HERE)[1].content == _memory(commanded, HERE)[1].content


###############################################################################
# 行为系统在同一 pass 里接着生效
###############################################################################
async def test_command_travel_takes_effect_and_is_announced() -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    plan_system = _planner(game, MapPlanSystem)
    move_system = ActorTravelSystem(game)
    move_system.activate()
    mount_command(game, actor, ActorTravelAction(x=1, y=2))

    await plan_system.execute()
    await move_system.execute()

    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (1, 2)
    assert said(game, WANDERER)[-1] == "你从舞台.大地图(1,1)走到舞台.大地图(1,2)。"


async def test_command_speak_reaches_the_other_actor() -> None:
    game = build_world()
    plan_system = _planner(game, SitePlanSystem)
    speak_system = ActorSpeakSystem(game)
    speak_system.activate()
    mount_command(game, entity(game, HERE), ActorSpeakAction(content="火还能撑多久？"))

    await plan_system.execute()
    await speak_system.execute()

    assert heard(game, OTHER)[-1] == f"{HERE}说：火还能撑多久？"


async def test_command_matching_the_wrong_layer_is_still_guarded() -> None:
    """接管也得服从层级：大地图上的说话不会被写进记忆，也不会广播。"""
    game = build_world()
    actor = entity(game, WANDERER)
    plan_system = _planner(game, MapPlanSystem)
    mount_command(game, actor, ActorSpeakAction(content="有人吗？"))

    await plan_system.execute()

    # 大地图上的计划只认大地图动词，说话动作留在原地、无人处理
    assert actor.has(ActorSpeakAction)
    assert actor.get(ActorComponent).current_stage == "舞台.大地图"
