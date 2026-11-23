"""位置广播：地点内只到当前区域，大地图只到同一格。

三条硬约束：地点广播不沿区域树扩散、地图格广播不跨格也不进入地点、
广播只投递不发布事件。
"""

from typing import Any, Dict, List

import pytest

from ai_srpg.game.assembly import create_srpg_game
from ai_srpg.game.context import SRPGGame
from ai_srpg.game.entities import build_from_blueprint
from ai_srpg.game.events.sink import RecordingEventSink
from ai_srpg.game.memory import get_agent_memory
from ai_srpg.game.systems.stage_broadcast_mixin import StageBroadcastMixin
from ai_srpg.models import (
    ActorBlueprint,
    ActorComponent,
    Blueprint,
    GridComponent,
    MapPosition,
    MapPositionComponent,
    NoneEvent,
    StageBlueprint,
    StageComponent,
    WorldBlueprint,
    WorldComponent,
)

###############################################################################
# 5x5 大地图：
#   (0,0) 营地（内含 铁匠铺）  (1,0) 哨站  (2,0) 矿场
#   地图上另有两个角色站在 (1,0)，一个站在 (2,0)
###############################################################################
CAMP = "舞台.营地"
FORGE = "舞台.铁匠铺"
OUTPOST = "舞台.哨站"
MINE = "舞台.矿场"
MAP = "舞台.大地图"


def _stage(
    name: str,
    *,
    map_position: MapPosition | None = None,
    children: List[StageBlueprint] | None = None,
) -> StageBlueprint:
    return StageBlueprint(
        name=name,
        system_message=f"{name} 的设定",
        components={StageComponent.__name__: {}},
        map_position=map_position,
        children=children or [],
    )


def _entity(
    name: str, stage_name: str, map_position: MapPosition | None = None
) -> ActorBlueprint:
    components: Dict[str, Dict[str, object]] = {
        ActorComponent.__name__: {"current_stage": stage_name}
    }
    if map_position is not None:
        components[MapPositionComponent.__name__] = {
            "x": map_position.x,
            "y": map_position.y,
        }
    return ActorBlueprint(
        name=name,
        system_message=f"{name} 的设定",
        components=components,
    )


def _blueprint() -> Blueprint:
    root = StageBlueprint(
        name=MAP,
        system_message=f"{MAP} 的设定",
        components={
            StageComponent.__name__: {},
            GridComponent.__name__: {"width": 5, "height": 5},
        },
        children=[
            _stage(CAMP, map_position=MapPosition(x=0, y=0), children=[_stage(FORGE)]),
            _stage(OUTPOST, map_position=MapPosition(x=1, y=0)),
            _stage(MINE, map_position=MapPosition(x=2, y=0)),
        ],
    )
    return Blueprint(
        name="BroadcastTest",
        campaign_setting="设定",
        global_rules="规则",
        stage_tree=root,
        actors=[
            _entity("角色.营中人", CAMP),
            _entity("角色.铁匠", FORGE),
            _entity("角色.哨兵", OUTPOST),
            _entity("角色.矿工", MINE),
            _entity("角色.地图甲", MAP, MapPosition(x=1, y=0)),
            _entity("角色.地图乙", MAP, MapPosition(x=1, y=0)),
            _entity("角色.地图丙", MAP, MapPosition(x=2, y=0)),
        ],
        worlds=[
            WorldBlueprint(
                name="世界.甲",
                system_message="世界.甲",
                components={WorldComponent.__name__: {}},
            )
        ],
    )


def _game() -> SRPGGame:
    game = create_srpg_game(name="BroadcastTest", events=RecordingEventSink())
    build_from_blueprint(game, _blueprint())
    return game


def _human_messages(game: SRPGGame, entity_name: str) -> List[Any]:
    """实体收到的领域事件消息（跳过 memories[0] 的系统提示）。"""
    entity = game.get_entity_by_name(entity_name)
    assert entity is not None
    return [
        message
        for message in get_agent_memory(game, entity).messages
        if getattr(message, "agent_event", None)
    ]


def _heard(game: SRPGGame) -> Dict[str, List[str]]:
    """谁收到了广播，以及各自的广播标记。"""
    heard: Dict[str, List[str]] = {}
    for name in (
        "角色.营中人",
        "角色.铁匠",
        "角色.哨兵",
        "角色.矿工",
        "角色.地图甲",
        "角色.地图乙",
        "角色.地图丙",
    ):
        messages = _human_messages(game, name)
        if messages:
            heard[name] = [str(message.broadcast_stage) for message in messages]
    return heard


def _events(game: SRPGGame) -> List[Any]:
    events = game.events.events  # type: ignore[attr-defined]
    return list(events)


###############################################################################
def test_region_broadcast_only_reaches_the_current_region() -> None:
    """地点内广播只看当前区域：不传子区域，也不传到地图格。"""
    game = _game()
    camp = game.get_entity_by_name(CAMP)

    StageBroadcastMixin(game).broadcast_in_region(
        camp, NoneEvent(message="营地起火了")  # type: ignore[arg-type]
    )

    assert _heard(game) == {"角色.营中人": [CAMP]}
    assert _human_messages(game, CAMP)[-1].content == "营地起火了"
    assert _human_messages(game, FORGE) == []
    assert _human_messages(game, OUTPOST) == []
    assert _human_messages(game, MAP) == []


###############################################################################
def test_map_cell_broadcast_only_reaches_the_same_cell() -> None:
    """地图格广播只看同一格：不跨格，也不进入格上的地点。"""
    game = _game()
    anchor = game.get_entity_by_name("角色.地图甲")

    StageBroadcastMixin(game).broadcast_in_map_cell(
        anchor, NoneEvent(message="路口有人喊话")  # type: ignore[arg-type]
    )

    assert _heard(game) == {
        "角色.地图甲": [MAP],
        "角色.地图乙": [MAP],
    }
    assert _human_messages(game, "角色.地图丙") == []
    assert _human_messages(game, "角色.哨兵") == []
    assert _human_messages(game, MAP) == []


###############################################################################
def test_map_cell_broadcast_can_exclude_the_anchor() -> None:
    game = _game()
    anchor = game.get_entity_by_name("角色.地图甲")
    assert anchor is not None

    StageBroadcastMixin(game).broadcast_in_map_cell(
        anchor,
        NoneEvent(message="我喊了一声"),
        exclude_entities={anchor},
    )

    assert _heard(game) == {"角色.地图乙": [MAP]}


###############################################################################
def test_broadcast_only_delivers() -> None:
    """广播只决定谁听见；事件由发起这件事的 system 发布一次。"""
    game = _game()

    StageBroadcastMixin(game).broadcast_in_region(
        game.get_entity_by_name(CAMP),  # type: ignore[arg-type]
        NoneEvent(message="讯息传开"),
    )
    StageBroadcastMixin(game).broadcast_in_map_cell(
        game.get_entity_by_name("角色.地图甲"),  # type: ignore[arg-type]
        NoneEvent(message="讯息传开"),
    )

    assert _events(game) == []
    assert set(_heard(game)) == {"角色.营中人", "角色.地图甲", "角色.地图乙"}


###############################################################################
def test_region_broadcast_rejects_the_map() -> None:
    game = _game()

    with pytest.raises(AssertionError, match="不能作为区域广播"):
        StageBroadcastMixin(game).broadcast_in_region(
            game.get_entity_by_name(MAP),  # type: ignore[arg-type]
            NoneEvent(message="?"),
        )


###############################################################################
def test_map_cell_broadcast_rejects_an_entity_inside_a_site() -> None:
    game = _game()

    with pytest.raises(AssertionError, match="不在大地图上"):
        StageBroadcastMixin(game).broadcast_in_map_cell(
            game.get_entity_by_name("角色.营中人"),  # type: ignore[arg-type]
            NoneEvent(message="?"),
        )
