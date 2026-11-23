"""领域事件：一个动作一个事件；位置变化说给三处听，但事件只发布一次。"""

from typing import Any, List

import pytest
from pydantic import TypeAdapter, ValidationError

from ai_srpg.game.context import SRPGGame
from ai_srpg.game.events.sink import RecordingEventSink
from ai_srpg.game.systems.enter_site_system import EnterSiteSystem
from ai_srpg.game.systems.exit_site_system import ExitSiteSystem
from ai_srpg.game.systems.move_within_site_system import (
    MoveWithinSiteSystem,
)
from ai_srpg.game.systems.speak_system import SpeakSystem
from ai_srpg.game.systems.stage_pulse_system import StagePulseSystem
from ai_srpg.game.systems.travel_system import TravelSystem
from ai_srpg.game.systems.wait_system import WaitSystem
from ai_srpg.models import (
    ActorEnteredSite,
    ActorExitedSite,
    ActorMovedWithinSite,
    ActorSpoke,
    ActorTraveled,
    ActorWaited,
    AnyAgentEvent,
    EnterSiteAction,
    ExitSiteAction,
    MapPositionComponent,
    MoveWithinSiteAction,
    NoneEvent,
    SpeakAction,
    StagePulse,
    TravelAction,
    WaitAction,
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
    messages,
)

_EVENT: TypeAdapter[AnyAgentEvent] = TypeAdapter(AnyAgentEvent)


def _world() -> tuple[SRPGGame, RecordingEventSink]:
    sink = RecordingEventSink()
    return build_world(events=sink), sink


def _activate(game: SRPGGame, system_type: Any) -> Any:
    system = system_type(game)
    system.activate()
    return system


def _tags(game: SRPGGame, name: str) -> List[str]:
    """该实体记忆里每条人类消息的事件标记。"""
    return [
        str(getattr(message, "agent_event", "")) for message in messages(game, name)
    ]


###############################################################################
# 事件的形状
###############################################################################
def test_events_round_trip_through_the_union() -> None:
    """每种事件都能按 type 判别解析回自己，字段不丢。"""
    events: List[Any] = [
        StagePulse(message="在场", stage=CAMP, actors=(HERE, OTHER)),
        ActorSpoke(message="说了", actor=HERE, stage=CAMP, site=CAMP, content="说了"),
        ActorWaited(message="没动", actor=HERE, stage=CAMP, site=CAMP),
        ActorTraveled(message="走了", actor=WANDERER, stage=MAP, x=1, y=2),
        ActorEnteredSite(message="进入", actor=WANDERER, stage=CAMP, site=CAMP),
        ActorExitedSite(message="离开", actor=HERE, stage=MAP, site=CAMP),
        ActorMovedWithinSite(message="挪了", actor=HERE, stage=FIRE_ROOM, site=CAMP),
        NoneEvent(message="兜底"),
    ]

    for event in events:
        parsed = _EVENT.validate_python(event.model_dump())
        assert parsed == event
        assert parsed.type == event.type


def test_unknown_field_is_rejected() -> None:
    """事件是契约：多一个字段就是写错了，不静默吞掉。"""
    with pytest.raises(ValidationError):
        ActorSpoke.model_validate(
            {
                "message": "x",
                "actor": HERE,
                "stage": CAMP,
                "site": CAMP,
                "content": "x",
                "extra": 1,
            }
        )


###############################################################################
# 一个动作一个事件
###############################################################################
async def test_speak_publishes_what_was_said() -> None:
    game, sink = _world()
    system = _activate(game, SpeakSystem)
    entity(game, HERE).replace(SpeakAction, "风变了。")
    await system.execute()

    (event,) = sink.events
    assert isinstance(event, ActorSpoke)
    assert (event.actor, event.stage, event.content) == (HERE, CAMP, "风变了。")
    assert _tags(game, OTHER) == ["actor_spoke"]


async def test_travel_publishes_once_and_only_tells_the_journey() -> None:
    """同格没有其他 actor，地图移动不广播；他自己另有一句路程记录。"""
    game, sink = _world()
    system = _activate(game, TravelSystem)

    entity(game, WANDERER).replace(TravelAction, 1, 2)
    await system.execute()

    (event,) = sink.events
    assert isinstance(event, ActorTraveled)
    assert (event.actor, event.stage, event.x, event.y) == (
        WANDERER,
        MAP,
        1,
        2,
    )
    # 旧格与新格都没有其他 actor；他自己另有一句路程记录
    assert _tags(game, MAP) == []
    assert _tags(game, WANDERER) == ["actor_traveled"]


async def test_enter_publishes_the_site_it_entered() -> None:
    game, sink = _world()
    actor = entity(game, WANDERER)
    actor.replace(MapPositionComponent, 2, 2)
    system = _activate(game, EnterSiteSystem)

    actor.replace(EnterSiteAction, CAMP)
    await system.execute()

    (event,) = sink.events
    assert isinstance(event, ActorEnteredSite)
    assert (event.actor, event.stage, event.site) == (WANDERER, CAMP, CAMP)
    assert _tags(game, CAMP) == ["actor_entered_site"]


async def test_exit_publishes_the_site_it_left() -> None:
    game, sink = _world()
    system = _activate(game, ExitSiteSystem)

    entity(game, HERE).replace(ExitSiteAction)
    await system.execute()

    (event,) = sink.events
    assert isinstance(event, ActorExitedSite)
    assert (event.actor, event.stage, event.site) == (HERE, MAP, CAMP)


async def test_move_within_publishes_destination_and_site() -> None:
    game, sink = _world()
    system = _activate(game, MoveWithinSiteSystem)

    entity(game, HERE).replace(MoveWithinSiteAction, FIRE_ROOM)
    await system.execute()

    (event,) = sink.events
    assert isinstance(event, ActorMovedWithinSite)
    assert (event.actor, event.stage, event.site) == (HERE, FIRE_ROOM, CAMP)


async def test_wait_inside_a_site_publishes_and_tells_others() -> None:
    game, sink = _world()
    system = _activate(game, WaitSystem)

    entity(game, HERE).replace(WaitAction)
    await system.execute()

    (event,) = sink.events
    assert isinstance(event, ActorWaited)
    assert (event.actor, event.stage, event.site) == (HERE, CAMP, CAMP)
    assert _tags(game, OTHER) == ["actor_waited"]


async def test_wait_on_the_map_publishes_but_tells_nobody() -> None:
    """大地图上没有听众，但「这轮没动」仍是发生过的事。"""
    game, sink = _world()
    system = _activate(game, WaitSystem)

    entity(game, WANDERER).replace(WaitAction)
    await system.execute()

    (event,) = sink.events
    assert isinstance(event, ActorWaited)
    assert event.stage == MAP
    assert event.site is None
    assert messages(game, MAP) == []
    assert messages(game, HERE) == []


async def test_pulse_publishes_who_is_present() -> None:
    game, sink = _world()

    await StagePulseSystem(game).execute()  # 每轮执行一次，不需要订阅触发器

    published = {
        event.stage: event for event in sink.events if isinstance(event, StagePulse)
    }
    assert isinstance(published[CAMP], StagePulse)
    assert sorted(published[CAMP].actors) == sorted([HERE, OTHER])
    assert isinstance(published[TOWER], StagePulse)
    assert published[TOWER].actors == ("角色.丙",)
    # 大地图没有在场者，不发布
    assert MAP not in published


###############################################################################
# 被拒绝的动作不产生事件
###############################################################################
async def test_rejected_action_publishes_nothing() -> None:
    game, sink = _world()
    system = _activate(game, TravelSystem)

    entity(game, WANDERER).replace(TravelAction, 4, 4)  # 不相邻
    await system.execute()

    assert sink.events == []
