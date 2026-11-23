"""蓝图装配的显式约束：类别标记、舞台树、网格坐标、名字唯一。

蓝图只给名字、``memories[0]`` 与组件数据；类别不靠枚举，而靠装配期要求实体带对了
标记组件——漏写就是内容写错，必须当场失败。
"""

from typing import Any, Dict, List, Optional

import pytest

from ai_srpg.game.assembly import create_srpg_game
from ai_srpg.game.context import SRPGGame
from ai_srpg.game.entities import (
    build_from_blueprint,
    get_actor_entity,
    get_stage_entity,
)
from ai_srpg.models import (
    ActorBlueprint,
    ActorComponent,
    AppearanceComponent,
    Blueprint,
    EnvironmentComponent,
    GridComponent,
    MapPosition,
    MapPositionComponent,
    StageBlueprint,
    StageComponent,
    WorldBlueprint,
    WorldComponent,
)

GRID = {"width": 5, "height": 5}


###############################################################################
def _world() -> WorldBlueprint:
    return WorldBlueprint(
        name="世界.甲",
        system_message="世界.甲 的设定",
        components={WorldComponent.__name__: {}},
    )


def _map_stage(
    *,
    components: Optional[Dict[str, Dict[str, Any]]] = None,
    children: Optional[List[StageBlueprint]] = None,
) -> StageBlueprint:
    return StageBlueprint(
        name="舞台.大地图",
        system_message="舞台.大地图 的设定",
        components=(
            {StageComponent.__name__: {}, GridComponent.__name__: dict(GRID)}
            if components is None
            else components
        ),
        children=children or [],
    )


def _camp(
    map_position: Optional[MapPosition] = None, *, name: str = "舞台.营地"
) -> StageBlueprint:
    return StageBlueprint(
        name=name,
        system_message=f"{name} 的设定",
        components={StageComponent.__name__: {}},
        map_position=map_position,
    )


def _blueprint(
    *,
    root: Optional[StageBlueprint] = None,
    actor_components: Optional[Dict[str, Dict[str, Any]]] = None,
    actor_stage: str = "舞台.营地",
    actors: Optional[List[ActorBlueprint]] = None,
    worlds: Optional[List[WorldBlueprint]] = None,
) -> Blueprint:
    return Blueprint(
        name="BuildTest",
        campaign_setting="设定",
        global_rules="规则",
        stage_tree=(
            root
            if root is not None
            else _map_stage(children=[_camp(MapPosition(x=2, y=2))])
        ),
        actors=(
            actors
            if actors is not None
            else [
                ActorBlueprint(
                    name="角色.甲",
                    system_message="角色.甲 的设定",
                    components=(
                        {ActorComponent.__name__: {"current_stage": actor_stage}}
                        if actor_components is None
                        else actor_components
                    ),
                )
            ]
        ),
        worlds=[_world()] if worlds is None else worlds,
    )


###############################################################################
def test_components_land_on_the_entity_verbatim() -> None:
    """组件数据原样进 ECS，装配期不猜任何字段。"""
    game = create_srpg_game(name="BuildTest")
    blueprint = _blueprint(
        actor_components={
            ActorComponent.__name__: {"current_stage": "舞台.营地"},
            AppearanceComponent.__name__: {"base_body": "瘦削"},
        }
    )

    build_from_blueprint(game, blueprint)

    actor = get_actor_entity(game, "角色.甲")
    assert actor is not None
    assert actor.get(AppearanceComponent).base_body == "瘦削"


###############################################################################
def test_appearance_defaults_to_base_body() -> None:
    """没给外观时，外观与基础体型相同——内容侧不必写两遍同一段文字。"""
    game = create_srpg_game(name="BuildTest")
    build_from_blueprint(
        game,
        _blueprint(
            actor_components={
                ActorComponent.__name__: {"current_stage": "舞台.营地"},
                AppearanceComponent.__name__: {"base_body": "瘦削"},
            }
        ),
    )

    actor = get_actor_entity(game, "角色.甲")
    assert actor is not None
    appearance = actor.get(AppearanceComponent)
    assert appearance.appearance == appearance.base_body == "瘦削"


###############################################################################
def test_environment_narrative_defaults_to_base_environment() -> None:
    """环境叙述缺省等于底稿——与外观的派生同一套路，内容侧只写一遍。"""
    game = create_srpg_game(name="BuildTest")
    build_from_blueprint(
        game,
        _blueprint(
            root=_map_stage(
                components={
                    StageComponent.__name__: {},
                    GridComponent.__name__: dict(GRID),
                    EnvironmentComponent.__name__: {"base_environment": "湿冷，风很大"},
                },
                children=[_camp(MapPosition(x=2, y=2))],
            )
        ),
    )

    map_stage = get_stage_entity(game, "舞台.大地图")
    assert map_stage is not None
    environment = map_stage.get(EnvironmentComponent)
    assert environment.narrative == environment.base_environment == "湿冷，风很大"


###############################################################################
def test_given_environment_narrative_is_kept() -> None:
    """显式给了当前叙述就不再被底稿覆盖。"""
    game = create_srpg_game(name="BuildTest")
    build_from_blueprint(
        game,
        _blueprint(
            root=_map_stage(
                components={
                    StageComponent.__name__: {},
                    GridComponent.__name__: dict(GRID),
                    EnvironmentComponent.__name__: {
                        "base_environment": "湿冷，风很大",
                        "narrative": "火堆被雨浇灭了",
                    },
                },
                children=[_camp(MapPosition(x=2, y=2))],
            )
        ),
    )

    map_stage = get_stage_entity(game, "舞台.大地图")
    assert map_stage is not None
    environment = map_stage.get(EnvironmentComponent)
    assert environment.narrative == "火堆被雨浇灭了"
    assert environment.base_environment == "湿冷，风很大"


###############################################################################
def test_stage_tree_sets_parent_and_map_position() -> None:
    """父子关系由嵌套决定，坐标由蓝图落成 ``MapPositionComponent``。"""
    game = create_srpg_game(name="BuildTest")
    build_from_blueprint(game, _blueprint())

    map_stage = get_stage_entity(game, "舞台.大地图")
    camp = get_stage_entity(game, "舞台.营地")
    assert map_stage is not None and camp is not None
    assert map_stage.get(StageComponent).parent_stage is None
    assert map_stage.get(GridComponent).width == 5
    assert camp.get(StageComponent).parent_stage == "舞台.大地图"
    position = camp.get(MapPositionComponent)
    assert (position.x, position.y) == (2, 2)


###############################################################################
def test_missing_actor_marker_is_rejected() -> None:
    """没挂 ``ActorComponent`` 的角色只是一个普通实体，必须当场报错。"""
    game = create_srpg_game(name="BuildTest")

    with pytest.raises(AssertionError, match="缺少标记组件 ActorComponent"):
        build_from_blueprint(
            game,
            _blueprint(
                actor_components={AppearanceComponent.__name__: {"base_body": "瘦削"}}
            ),
        )


###############################################################################
def test_missing_stage_marker_is_rejected() -> None:
    """没挂 ``StageComponent`` 的舞台不会被下游认出来，同样当场报错。"""
    game = create_srpg_game(name="BuildTest")

    with pytest.raises(AssertionError, match="缺少标记组件 StageComponent"):
        build_from_blueprint(
            game,
            _blueprint(
                root=_map_stage(components={GridComponent.__name__: dict(GRID)})
            ),
        )


###############################################################################
def test_root_stage_must_have_grid() -> None:
    """舞台树的根是大地图，必须带网格——否则整棵树没有坐标系。"""
    game = create_srpg_game(name="BuildTest")
    root = StageBlueprint(
        name="舞台.大地图",
        system_message="舞台.大地图 的设定",
        components={StageComponent.__name__: {}},
    )

    with pytest.raises(AssertionError, match="必须带网格"):
        build_from_blueprint(game, _blueprint(root=root))


###############################################################################
def test_only_the_root_stage_may_have_grid() -> None:
    """网格只能有一个，且只能在大地图（根）上。"""
    game = create_srpg_game(name="BuildTest")
    child = StageBlueprint(
        name="舞台.营地",
        system_message="舞台.营地 的设定",
        components={
            StageComponent.__name__: {},
            GridComponent.__name__: dict(GRID),
        },
        map_position=MapPosition(x=0, y=0),
    )

    with pytest.raises(AssertionError, match="只有大地图"):
        build_from_blueprint(
            game,
            _blueprint(root=_map_stage(children=[child])),
        )


###############################################################################
def test_root_stage_has_no_map_position() -> None:
    """大地图是坐标系本身，不能被摆在某个格子上。"""
    game = create_srpg_game(name="BuildTest")
    root = _map_stage()
    root.map_position = MapPosition(x=0, y=0)

    with pytest.raises(AssertionError, match="没有大地图位置"):
        build_from_blueprint(game, _blueprint(root=root))


###############################################################################
def test_child_stage_needs_a_map_position() -> None:
    """父舞台有网格时，子舞台必须说明自己在哪一格。"""
    game = create_srpg_game(name="BuildTest")

    with pytest.raises(AssertionError, match="必须声明"):
        build_from_blueprint(
            game,
            _blueprint(root=_map_stage(children=[_camp()])),
        )


###############################################################################
def test_child_stage_must_fit_in_the_grid() -> None:
    """坐标越界同样是内容写错，装配期就报出来。"""
    game = create_srpg_game(name="BuildTest")

    with pytest.raises(AssertionError, match="超出"):
        build_from_blueprint(
            game,
            _blueprint(root=_map_stage(children=[_camp(MapPosition(x=5, y=0))])),
        )


###############################################################################
def test_two_children_cannot_share_a_cell() -> None:
    """一格一物：同一父舞台下坐标不得重复。"""
    game = create_srpg_game(name="BuildTest")
    root = _map_stage(
        children=[
            _camp(MapPosition(x=1, y=1), name="舞台.营地"),
            _camp(MapPosition(x=1, y=1), name="舞台.哨站"),
        ]
    )

    with pytest.raises(AssertionError, match="已被占用"):
        build_from_blueprint(game, _blueprint(root=root))


###############################################################################
def test_map_position_without_grid_parent_is_rejected() -> None:
    """父舞台没有网格，子舞台的位置就没有意义，别让它悄悄失效。"""
    game = create_srpg_game(name="BuildTest")
    site = _camp(MapPosition(x=2, y=2), name="舞台.营地")
    site.children = [_camp(MapPosition(x=0, y=0), name="舞台.铁匠铺")]

    with pytest.raises(AssertionError, match="没有网格"):
        build_from_blueprint(
            game,
            _blueprint(root=_map_stage(children=[site])),
        )


###############################################################################
def test_duplicate_names_are_rejected() -> None:
    """名字是 ECS 的索引键，重名会静默覆盖，必须在装配期拦住。"""
    game = create_srpg_game(name="BuildTest")
    duplicated = _blueprint(
        actors=[
            ActorBlueprint(
                name="角色.甲",
                system_message="角色.甲 的设定",
                components={ActorComponent.__name__: {"current_stage": "舞台.营地"}},
            ),
            ActorBlueprint(
                name="角色.甲",
                system_message="角色.甲 的设定",
                components={ActorComponent.__name__: {"current_stage": "舞台.营地"}},
            ),
        ]
    )

    with pytest.raises(AssertionError, match="重名实体"):
        build_from_blueprint(game, duplicated)


###############################################################################
def test_actor_on_undeclared_stage_is_rejected() -> None:
    """角色的所在舞台必须是蓝图声明过的舞台，否则游戏一开局就是悬空的。"""
    game = create_srpg_game(name="BuildTest")

    with pytest.raises(AssertionError, match="所在舞台不存在: 舞台.别处"):
        build_from_blueprint(
            game,
            _blueprint(actor_stage="舞台.别处"),
        )


###############################################################################
def test_prompt_must_contain_entity_name() -> None:
    """实体全名是路由契约，system_message 里缺了它就是内容写错。"""
    game = create_srpg_game(name="BuildTest")
    root = _map_stage(children=[_camp(MapPosition(x=2, y=2))])
    root.system_message = "少了名字的设定"

    with pytest.raises(AssertionError, match="系统消息缺少实体名"):
        build_from_blueprint(game, _blueprint(root=root))


###############################################################################
def test_build_rejects_non_empty_game() -> None:
    """一局只构建一次，已有实体的游戏不能重复构建。"""
    game = create_srpg_game(name="BuildTest")
    build_from_blueprint(game, _blueprint())

    with pytest.raises(AssertionError, match="游戏中有实体"):
        build_from_blueprint(game, _blueprint())


###############################################################################
def test_actor_marker_carries_stage() -> None:
    """舞台归属写在组件里，不靠嵌套结构，读回来就是当初写下的值。"""
    game: SRPGGame = create_srpg_game(name="BuildTest")
    build_from_blueprint(game, _blueprint())

    actor = get_actor_entity(game, "角色.甲")
    assert actor is not None
    assert actor.get(ActorComponent).current_stage == "舞台.营地"
