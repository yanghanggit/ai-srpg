"""大地图广播：以大地图坐标为原点，按格距波及地点及其内部区域。

三条硬约束：范围按切比雪夫距离算、命中地点及其整棵子树、跨舞台的事件只发布
一次（否则会话历史里会出现重复记录）。
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
    NoneEvent,
    StageBlueprint,
    StageComponent,
    WorldBlueprint,
    WorldComponent,
)

###############################################################################
# 5x5 大地图：
#   (0,0) 营地 (1,0) 哨站 (2,0) 矿场
#   营地内挂 铁匠铺（无坐标）
###############################################################################
CAMP = "舞台.营地"
OUTPOST = "舞台.哨站"
MINE = "舞台.矿场"
FORGE = "舞台.铁匠铺"


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


def _entity(name: str, stage_name: str) -> ActorBlueprint:
    return ActorBlueprint(
        name=name,
        system_message=f"{name} 的设定",
        components={ActorComponent.__name__: {"current_stage": stage_name}},
    )


def _blueprint() -> Blueprint:
    root = StageBlueprint(
        name="舞台.大地图",
        system_message="舞台.大地图 的设定",
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
    for name in ("角色.营中人", "角色.铁匠", "角色.哨兵", "角色.矿工"):
        messages = _human_messages(game, name)
        if messages:
            heard[name] = [str(message.broadcast_stage) for message in messages]
    return heard


def _events(game: SRPGGame) -> List[Any]:
    events = game.events.events  # type: ignore[attr-defined]
    return list(events)


###############################################################################
def test_radius_zero_only_covers_the_origin_stage() -> None:
    """radius=0 只影响原点所在的那一处（含它的子树）。"""
    game = _game()
    camp = game.get_entity_by_name(CAMP)

    StageBroadcastMixin(game).broadcast_over_map(
        camp, NoneEvent(message="营地起火了"), radius=0  # type: ignore[arg-type]
    )

    assert _heard(game) == {
        "角色.营中人": [CAMP],
        "角色.铁匠": [FORGE],
    }


###############################################################################
def test_radius_is_chebyshev() -> None:
    """距离按八方向算：(0,0) 到 (1,1) 也是一格。"""
    blueprint = _blueprint()
    blueprint.stage_tree.children[1].map_position = MapPosition(x=1, y=1)
    game = create_srpg_game(name="BroadcastTest", events=RecordingEventSink())
    build_from_blueprint(game, blueprint)

    StageBroadcastMixin(game).broadcast_over_map(
        game.get_entity_by_name(CAMP),  # type: ignore[arg-type]
        NoneEvent(message="路口的动静"),
        radius=1,
    )

    assert "角色.哨兵" in _heard(game)


###############################################################################
def test_radius_one_reaches_neighbours_but_not_farther_stages() -> None:
    """半径 1 命中营地与哨站，矿场听不到。"""
    game = _game()

    StageBroadcastMixin(game).broadcast_over_map(
        game.get_entity_by_name(CAMP),  # type: ignore[arg-type]
        NoneEvent(message="远处有火光"),
        radius=1,
    )

    assert _heard(game) == {
        "角色.营中人": [CAMP],
        "角色.铁匠": [FORGE],
        "角色.哨兵": [OUTPOST],
    }


###############################################################################
def test_full_map_broadcast_reaches_every_region() -> None:
    """radius=None 是全图广播；大地图本身不收，因为它没有「在场者」。"""
    game = _game()
    map_stage = game.get_entity_by_name("舞台.大地图")

    StageBroadcastMixin(game).broadcast_over_map(
        map_stage, NoneEvent(message="天黑了"), radius=None  # type: ignore[arg-type]
    )

    assert set(_heard(game)) == {"角色.营中人", "角色.铁匠", "角色.哨兵", "角色.矿工"}
    assert _human_messages(game, "舞台.大地图") == []


###############################################################################
def test_broadcast_only_delivers() -> None:
    """广播只决定谁听见；事件由发起这件事的 system 发布一次，否则历史会重复。"""
    game = _game()

    StageBroadcastMixin(game).broadcast_over_map(
        game.get_entity_by_name(CAMP),  # type: ignore[arg-type]
        NoneEvent(message="讯息传开"),
        radius=1,
    )

    assert _events(game) == []
    assert _heard(game) == {
        "角色.营中人": [CAMP],
        "角色.铁匠": [FORGE],
        "角色.哨兵": [OUTPOST],
    }


###############################################################################
def test_anchor_inside_a_site_uses_the_parent_cell() -> None:
    """建筑没有坐标，用最近的有坐标祖先当锚点——结果与从营地发起完全一样。"""
    game = _game()
    forge = game.get_entity_by_name(FORGE)

    StageBroadcastMixin(game).broadcast_over_map(
        forge, NoneEvent(message="铁锤声传开"), radius=1  # type: ignore[arg-type]
    )

    assert set(_heard(game)) == {"角色.营中人", "角色.铁匠", "角色.哨兵"}


###############################################################################
def test_coordinate_less_stage_requires_full_map_radius() -> None:
    """没有坐标的区域做有限半径广播是说不通的，必须当场报错。

    蓝图装配期不允许出现这种区域，这里直接造一个，验证兜底而不是正常路径。
    """
    game = _game()
    orphans = game.create_entity("舞台.无名地")
    orphans.add(StageComponent, "舞台.大地图")

    with pytest.raises(AssertionError, match="没有坐标"):
        StageBroadcastMixin(game).broadcast_over_map(
            orphans, NoneEvent(message="?"), radius=1
        )


###############################################################################
def test_negative_radius_is_rejected() -> None:
    game = _game()

    with pytest.raises(AssertionError, match="半径不能为负数"):
        StageBroadcastMixin(game).broadcast_over_map(
            game.get_entity_by_name(CAMP), NoneEvent(message="?"), radius=-1  # type: ignore[arg-type]
        )


###############################################################################
def test_excluded_entities_do_not_hear_it() -> None:
    """说话者自己可以被排除，即使它就在范围里。"""
    game = _game()
    speaker = game.get_entity_by_name(CAMP)
    assert speaker is not None

    StageBroadcastMixin(game).broadcast_over_map(
        speaker,
        NoneEvent(message="我喊了一声"),
        radius=0,
        exclude_entities={speaker},
    )

    assert CAMP not in _heard(game)
    assert "角色.营中人" in _heard(game)
