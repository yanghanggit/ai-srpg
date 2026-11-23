"""六个行为系统：说话、等待、大地图移动、进入地点、离开地点、区域内移动。

每个动词只在它所属的层生效：说话与离开地点在地点里，大地图移动与进入地点在大地图上，区域内移动
在地点内部，等待在两层都可用（大地图上没有可告知的对象）。
"""

from typing import Type, TypeVar

from ai_srpg.entitas import ReactiveProcessor
from ai_srpg.game.context import SRPGGame
from ai_srpg.game.systems.actor_enter_site_system import ActorEnterSiteSystem
from ai_srpg.game.systems.actor_exit_site_system import ActorExitSiteSystem
from ai_srpg.game.systems.actor_move_within_site_system import (
    ActorMoveWithinSiteSystem,
)
from ai_srpg.game.systems.actor_speak_system import ActorSpeakSystem
from ai_srpg.game.systems.actor_travel_system import ActorTravelSystem
from ai_srpg.game.systems.actor_wait_system import ActorWaitSystem
from ai_srpg.models import (
    ActorComponent,
    ActorEnterSiteAction,
    ActorExitSiteAction,
    ActorMoveWithinSiteAction,
    ActorSpeakAction,
    ActorTravelAction,
    ActorWaitAction,
    MapPositionComponent,
)
from world_fixture import (
    CAMP,
    FIRE_ROOM,
    HERE,
    MAP,
    OTHER,
    TOWER,
    WANDERER,
    build_world,
    entity,
    heard,
    said,
)

_Processor = TypeVar("_Processor", bound=ReactiveProcessor)


def _system(system_type: Type[_Processor], game: SRPGGame) -> _Processor:
    system = system_type(game)
    system.activate()
    return system


###############################################################################
# 说话：只在地点里
###############################################################################
async def test_speak_reaches_the_region_only() -> None:
    game = build_world()
    actor = entity(game, HERE)
    system = _system(ActorSpeakSystem, game)

    actor.replace(ActorSpeakAction, "风变了。")
    await system.execute()

    assert heard(game, OTHER) == [f"{HERE}说：风变了。"]
    assert heard(game, CAMP) == [f"{HERE}说：风变了。"]
    assert heard(game, HERE) == []
    assert heard(game, WANDERER) == []
    assert heard(game, TOWER) == []


async def test_speak_on_the_map_is_not_a_thing() -> None:
    """大地图不是场所：站在大地图上说话，谁也不会听见，包括大地图自己。"""
    game = build_world()
    actor = entity(game, WANDERER)
    system = _system(ActorSpeakSystem, game)

    actor.replace(ActorSpeakAction, "有人吗？")
    await system.execute()

    assert heard(game, HERE) == []
    assert heard(game, MAP) == []


async def test_wait_on_the_map_tells_nobody() -> None:
    """大地图上没有听众：原地不动只是「这轮没动」，不产生任何广播。"""
    game = build_world()
    actor = entity(game, WANDERER)
    system = _system(ActorWaitSystem, game)

    actor.replace(ActorWaitAction)
    await system.execute()

    assert heard(game, MAP) == []
    assert heard(game, HERE) == []


async def test_wait_tells_others_that_nothing_happened() -> None:
    game = build_world()
    actor = entity(game, HERE)
    system = _system(ActorWaitSystem, game)

    actor.replace(ActorWaitAction)
    await system.execute()

    assert heard(game, OTHER) == [f"{HERE}留在原地。"]
    assert heard(game, CAMP) == [f"{HERE}留在原地。"]
    assert heard(game, HERE) == []


###############################################################################
# 大地图移动：只改坐标，不改变所在层
###############################################################################
async def test_travel_moves_one_cell_on_the_map() -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    system = _system(ActorTravelSystem, game)

    actor.replace(ActorTravelAction, 1, 2)
    await system.execute()

    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (1, 2)
    assert actor.get(ActorComponent).current_stage == MAP
    assert said(game, WANDERER) == [f"你从{MAP}(1,1)走到{MAP}(1,2)。"]
    assert heard(game, MAP) == [
        f"{WANDERER}离开了{MAP}(1,1)。",
        f"{WANDERER}来到了{MAP}(1,2)。",
    ]


async def test_travel_can_stop_on_a_site_cell() -> None:
    """站在地点所在格：走到地点格不算进入地点，仍然站在大地图上。"""
    game = build_world()
    actor = entity(game, WANDERER)
    system = _system(ActorTravelSystem, game)

    actor.replace(ActorTravelAction, 2, 2)
    await system.execute()

    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (2, 2)
    assert actor.get(ActorComponent).current_stage == MAP


async def test_travel_rejects_non_adjacent_cells() -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    system = _system(ActorTravelSystem, game)

    actor.replace(ActorTravelAction, 4, 4)
    await system.execute()

    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (1, 1)
    assert said(game, WANDERER) == []


async def test_travel_requires_being_on_the_map() -> None:
    """地点内部的人收到大地图移动动作也不会动：层级不符的动作不生效。"""
    game = build_world()
    actor = entity(game, HERE)
    system = _system(ActorTravelSystem, game)

    actor.replace(ActorTravelAction, 3, 3)
    await system.execute()

    assert actor.get(ActorComponent).current_stage == CAMP
    assert not actor.has(MapPositionComponent)


###############################################################################
# 进入地点 / 离开地点：边界上的一对
###############################################################################
async def test_enter_requires_standing_on_the_site_cell() -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    actor.replace(MapPositionComponent, 2, 2)
    system = _system(ActorEnterSiteSystem, game)

    actor.replace(ActorEnterSiteAction, CAMP)
    await system.execute()

    assert actor.get(ActorComponent).current_stage == CAMP
    assert not actor.has(MapPositionComponent)
    # 离开发生在大地图上：只有大地图记下；地点里的人只看见他进来
    assert heard(game, MAP) == [f"{WANDERER}离开了{MAP}(2,2)。"]
    assert heard(game, OTHER) == [f"{WANDERER}来到了{CAMP}。"]
    assert said(game, WANDERER) == [f"你从{MAP}(2,2)走到{CAMP}。"]


async def test_enter_is_rejected_from_another_cell() -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    system = _system(ActorEnterSiteSystem, game)

    actor.replace(ActorEnterSiteAction, CAMP)
    await system.execute()

    assert actor.get(ActorComponent).current_stage == MAP
    assert said(game, WANDERER) == []


async def test_exit_lands_on_the_site_cell() -> None:
    game = build_world()
    actor = entity(game, HERE)
    system = _system(ActorExitSiteSystem, game)

    actor.replace(ActorExitSiteAction)
    await system.execute()

    assert actor.get(ActorComponent).current_stage == MAP
    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (2, 2)
    assert heard(game, OTHER) == [f"{HERE}离开了{CAMP}。"]
    assert heard(game, MAP) == [f"{HERE}来到了{MAP}(2,2)。"]
    assert said(game, HERE) == [f"你从{CAMP}走到{MAP}(2,2)。"]


async def test_exit_from_a_deeper_area_still_lands_on_the_site_cell() -> None:
    """地点对外只占一格：在里面走到再深，离开地点也是从地点那一格出去。"""
    game = build_world()
    actor = entity(game, HERE)
    actor.replace(ActorComponent, FIRE_ROOM)
    system = _system(ActorExitSiteSystem, game)
    actor.replace(ActorExitSiteAction)

    await system.execute()

    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (2, 2)
    assert actor.get(ActorComponent).current_stage == MAP


###############################################################################
# 区域内移动：子区域与父区域
###############################################################################
async def test_move_within_goes_to_a_child_area() -> None:
    game = build_world()
    actor = entity(game, HERE)
    system = _system(ActorMoveWithinSiteSystem, game)

    actor.replace(ActorMoveWithinSiteAction, FIRE_ROOM)
    await system.execute()

    assert actor.get(ActorComponent).current_stage == FIRE_ROOM
    assert heard(game, OTHER) == [f"{HERE}离开了{CAMP}。"]
    assert heard(game, FIRE_ROOM) == [f"{HERE}来到了{FIRE_ROOM}。"]
    assert said(game, HERE) == [f"你从{CAMP}走到{FIRE_ROOM}。"]


async def test_move_within_goes_back_to_the_parent_area() -> None:
    game = build_world()
    actor = entity(game, OTHER)
    actor.replace(ActorComponent, FIRE_ROOM)
    system = _system(ActorMoveWithinSiteSystem, game)

    actor.replace(ActorMoveWithinSiteAction, CAMP)
    await system.execute()

    assert actor.get(ActorComponent).current_stage == CAMP


async def test_move_within_cannot_leave_the_site() -> None:
    """去另一个地点不是区域内移动：那是先离开地点、再上路的组合。"""
    game = build_world()
    actor = entity(game, HERE)
    system = _system(ActorMoveWithinSiteSystem, game)

    actor.replace(ActorMoveWithinSiteAction, TOWER)
    await system.execute()

    assert actor.get(ActorComponent).current_stage == CAMP
    assert said(game, HERE) == []


async def test_move_within_requires_being_inside_a_site() -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    system = _system(ActorMoveWithinSiteSystem, game)

    actor.replace(ActorMoveWithinSiteAction, CAMP)
    await system.execute()

    assert actor.get(ActorComponent).current_stage == MAP
    assert said(game, WANDERER) == []


###############################################################################
# 触发器语义：进入匹配集合（不是「同时添加两个组件」）
###############################################################################
async def test_replacing_the_action_triggers_again() -> None:
    """ActorComponent 早就在了，更新动作也会再触发一次。"""
    game = build_world()
    actor = entity(game, WANDERER)
    system = _system(ActorTravelSystem, game)

    actor.replace(ActorTravelAction, 1, 2)
    await system.execute()
    actor.replace(ActorTravelAction, 2, 2)
    await system.execute()

    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (2, 2)


async def test_action_mounted_before_activation_is_not_collected() -> None:
    """先挂动作再开收集器，这次变更不会进来——动作只活一次 pass 的前提。"""
    game = build_world()
    actor = entity(game, WANDERER)
    actor.replace(ActorTravelAction, 1, 2)
    system = _system(ActorTravelSystem, game)

    await system.execute()

    position = actor.get(MapPositionComponent)
    assert (position.x, position.y) == (1, 1)
