"""舞台树上的查询：分组顺序确定、父子关系可查。

组查询来自 ``set``（按对象哈希迭代），顺序不可预期；同一份蓝图每次构建都应得到
同样的顺序，否则「重放同一快照得到同样历史」不成立。
"""

import pytest

from ai_srpg.game.assembly import create_srpg_game
from ai_srpg.game.context import SRPGGame
from ai_srpg.game.entities import (
    build_from_blueprint,
    get_actors_by_stage,
    get_actors_by_stage_as_names,
    get_actors_in_stage,
    get_ancestor_stages,
    get_child_stages,
    get_stage_entity,
)
from ai_srpg.models import (
    ActorBlueprint,
    ActorComponent,
    Blueprint,
    GridComponent,
    MapPosition,
    StageBlueprint,
    StageComponent,
    WorldBlueprint,
    WorldComponent,
)


###############################################################################
def _stage(
    name: str, *, map_position: MapPosition = MapPosition(x=0, y=0)
) -> StageBlueprint:
    return StageBlueprint(
        name=name,
        system_message=f"{name} 的设定",
        components={StageComponent.__name__: {}},
        map_position=map_position,
    )


def _blueprint(world_count: int = 1) -> Blueprint:
    """大地图 (0,0) 下挂营地与哨站，营地再挂铁匠铺；另有站在大地图上的角色。"""
    camp = _stage("舞台.营地", map_position=MapPosition(x=1, y=1))
    camp.children = [
        StageBlueprint(
            name="舞台.铁匠铺",
            system_message="舞台.铁匠铺 的设定",
            components={StageComponent.__name__: {}},
        )
    ]
    root = StageBlueprint(
        name="舞台.大地图",
        system_message="舞台.大地图 的设定",
        components={
            StageComponent.__name__: {},
            GridComponent.__name__: {"width": 5, "height": 5},
        },
        children=[camp, _stage("舞台.哨站", map_position=MapPosition(x=2, y=2))],
    )
    return Blueprint(
        name="TreeTest",
        campaign_setting="设定",
        global_rules="规则",
        stage_tree=root,
        actors=[
            ActorBlueprint(
                name="角色.游荡者",
                system_message="角色.游荡者",
                components={ActorComponent.__name__: {"current_stage": "舞台.大地图"}},
            ),
            ActorBlueprint(
                name="角色.铁匠",
                system_message="角色.铁匠",
                components={ActorComponent.__name__: {"current_stage": "舞台.铁匠铺"}},
            ),
        ],
        worlds=[
            WorldBlueprint(
                name=f"世界.{index}",
                system_message=f"世界.{index}",
                components={WorldComponent.__name__: {}},
            )
            for index in range(world_count)
        ],
    )


def _build(world_count: int = 1) -> SRPGGame:
    game = create_srpg_game(name="TreeTest")
    build_from_blueprint(game, _blueprint(world_count))
    return game


###############################################################################
def test_grouping_covers_every_stage_in_tree_preorder() -> None:
    """空舞台也在映射里，顺序是舞台树的先序（父在子前）。"""
    game = _build()

    names = list(get_actors_by_stage_as_names(game))

    assert names == ["舞台.大地图", "舞台.营地", "舞台.铁匠铺", "舞台.哨站"]


###############################################################################
@pytest.mark.parametrize("world_count", [1, 2, 3])
def test_grouping_order_does_not_depend_on_entity_count(world_count: int) -> None:
    """实体总数会改变 set 的迭代顺序，但分组顺序不能跟着变。"""
    game = _build(world_count)

    assert list(get_actors_by_stage_as_names(game)) == [
        "舞台.大地图",
        "舞台.营地",
        "舞台.铁匠铺",
        "舞台.哨站",
    ]


###############################################################################
def test_grouping_only_holds_direct_members() -> None:
    """只含直接归属：大地图上是游荡者，铁匠在铁匠铺，营地本身是空的。"""
    game = _build()

    mapping = get_actors_by_stage_as_names(game)

    assert mapping["舞台.大地图"] == ["角色.游荡者"]
    assert mapping["舞台.铁匠铺"] == ["角色.铁匠"]
    assert mapping["舞台.营地"] == []


###############################################################################
def test_actors_in_stage_does_not_include_descendants() -> None:
    """按舞台取角色同样只看直接归属，与广播范围保持一致。"""
    game = _build()
    map_stage = get_stage_entity(game, "舞台.大地图")
    assert map_stage is not None

    actors = get_actors_in_stage(game, map_stage)

    assert {actor.name for actor in actors} == {"角色.游荡者"}


###############################################################################
def test_child_stages_follow_declaration_order() -> None:
    """子舞台按蓝图里的声明顺序返回。"""
    game = _build()
    map_stage = get_stage_entity(game, "舞台.大地图")
    assert map_stage is not None

    children = get_child_stages(game, "舞台.大地图")

    assert [child.name for child in children] == ["舞台.营地", "舞台.哨站"]
    assert get_child_stages(game, "舞台.铁匠铺") == []


###############################################################################
def test_ancestors_are_listed_nearest_first() -> None:
    """祖先链由近到远，根舞台没有祖先。"""
    game = _build()

    ancestors = get_ancestor_stages(game, "舞台.铁匠铺")

    assert [stage.name for stage in ancestors] == ["舞台.营地", "舞台.大地图"]
    assert get_ancestor_stages(game, "舞台.大地图") == []


###############################################################################
def test_ancestors_of_actor_stage() -> None:
    """角色所在舞台同样能上溯——玩法里判断「附近有什么」会用到。"""
    game = _build()

    assert [stage.name for stage in get_ancestor_stages(game, "舞台.铁匠铺")][-1] == (
        "舞台.大地图"
    )


###############################################################################
def test_actor_group_is_sorted_by_creation_order() -> None:
    """同一舞台内的角色也按创建顺序排列。"""
    game = _build()
    camp = get_stage_entity(game, "舞台.营地")
    assert camp is not None

    mapping = get_actors_by_stage(game)

    for actors in mapping.values():
        assert [actor.index for actor in actors] == sorted(
            actor.index for actor in actors
        )
