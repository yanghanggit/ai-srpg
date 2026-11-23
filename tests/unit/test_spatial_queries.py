"""空间查询：大地图、地点、区域之间的结构关系。

这些查询是位置语义的单一入口：舞台树的根是大地图，大地图的直接子舞台是地点，
地点内部按父子关系成图。测试直接钉住这些边界，避免行为系统各自解释。
"""

import pytest

from ai_srpg.game.entities.queries import (
    get_adjacent_regions,
    get_map_position,
    get_map_stage,
    get_site,
    get_site_at_cell,
    get_sites,
    get_visible_cells,
    is_map_stage,
)
from ai_srpg.models import (
    ActorComponent,
    MapPosition,
    MapPositionComponent,
    SiteComponent,
)
from world_fixture import (
    CAMP,
    FIRE_ROOM,
    HERE,
    MAP,
    SENTRY,
    TOWER,
    WANDERER,
    build_world,
    entity,
)


###############################################################################
# 舞台树的层级
###############################################################################
def test_is_map_stage_only_true_for_the_root() -> None:
    game = build_world()

    assert is_map_stage(entity(game, MAP))
    assert not is_map_stage(entity(game, CAMP))
    assert not is_map_stage(entity(game, FIRE_ROOM))


def test_get_map_stage_walks_every_depth_to_the_root() -> None:
    game = build_world()

    for name in (MAP, CAMP, FIRE_ROOM, TOWER):
        assert get_map_stage(game, name).name == MAP


def test_get_map_stage_rejects_unknown_stage() -> None:
    game = build_world()

    with pytest.raises(AssertionError, match="找不到舞台实体"):
        get_map_stage(game, "舞台.不存在")


###############################################################################
# 地点归属
###############################################################################
def test_get_site_is_none_on_the_map() -> None:
    game = build_world()

    assert get_site(game, entity(game, WANDERER)) is None
    assert get_site(game, entity(game, MAP)) is None


def test_get_site_returns_the_direct_child_of_the_map() -> None:
    game = build_world()

    site = get_site(game, entity(game, CAMP))
    assert site is not None and site.name == CAMP

    site = get_site(game, entity(game, HERE))
    assert site is not None and site.name == CAMP


def test_get_sites_returns_marked_sites_in_creation_order() -> None:
    game = build_world()

    sites = get_sites(game)

    assert [site.name for site in sites] == [CAMP, TOWER]
    assert all(site.has(SiteComponent) for site in sites)
    assert not entity(game, MAP).has(SiteComponent)
    assert not entity(game, FIRE_ROOM).has(SiteComponent)


def test_get_site_is_stable_at_every_depth_inside_the_site() -> None:
    game = build_world()
    actor = entity(game, HERE)
    actor.replace(ActorComponent, FIRE_ROOM)

    site = get_site(game, actor)
    assert site is not None and site.name == CAMP

    site = get_site(game, entity(game, FIRE_ROOM))
    assert site is not None and site.name == CAMP


###############################################################################
# 大地图坐标
###############################################################################
def test_get_map_position_uses_the_actors_own_cell_on_the_map() -> None:
    game = build_world()

    map_stage, position = get_map_position(game, entity(game, WANDERER))

    assert map_stage.name == MAP
    assert (position.x, position.y) == (1, 1)


def test_get_map_position_uses_the_sites_cell_inside_a_site() -> None:
    game = build_world()
    actor = entity(game, HERE)
    actor.replace(ActorComponent, FIRE_ROOM)

    for target in (entity(game, CAMP), entity(game, FIRE_ROOM), actor):
        map_stage, position = get_map_position(game, target)
        assert map_stage.name == MAP
        assert (position.x, position.y) == (2, 2)


def test_get_map_position_requires_coordinates_on_the_map() -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    actor.remove(MapPositionComponent)

    with pytest.raises(AssertionError, match="没有格子坐标"):
        get_map_position(game, actor)


###############################################################################
# 视野
###############################################################################
def test_get_visible_cells_is_the_actors_cell_plus_eight_neighbours() -> None:
    game = build_world()

    cells = get_visible_cells(game, entity(game, WANDERER))

    assert cells == sorted(cells)
    assert {(cell.x, cell.y) for cell in cells} == {
        (x, y) for x in range(3) for y in range(3)
    }


def test_get_visible_cells_marks_sites_but_not_people_inside_them() -> None:
    game = build_world()

    by_cell = {
        (cell.x, cell.y): cell
        for cell in get_visible_cells(game, entity(game, WANDERER))
    }

    assert by_cell[(2, 2)].site == CAMP
    assert by_cell[(2, 2)].actors == ()  # 地点内部的人不在大地图格上
    assert by_cell[(1, 1)].site is None
    assert by_cell[(1, 1)].actors == ()


def test_get_visible_cells_excludes_self_and_includes_same_cell() -> None:
    game = build_world()
    sentry = entity(game, SENTRY)
    sentry.replace(ActorComponent, MAP)
    sentry.replace(MapPositionComponent, 1, 1)

    by_cell = {
        (cell.x, cell.y): cell
        for cell in get_visible_cells(game, entity(game, WANDERER))
    }

    assert by_cell[(1, 1)].actors == (SENTRY,)


def test_get_visible_cells_clamps_at_the_map_edge() -> None:
    game = build_world()
    actor = entity(game, WANDERER)
    actor.replace(MapPositionComponent, 0, 0)

    cells = get_visible_cells(game, actor)

    assert {(cell.x, cell.y) for cell in cells} == {(0, 0), (0, 1), (1, 0), (1, 1)}


###############################################################################
# 格上的地点
###############################################################################
def test_get_site_at_cell_finds_the_site_or_returns_none() -> None:
    game = build_world()
    map_stage = entity(game, MAP)

    camp = get_site_at_cell(game, map_stage, MapPosition(x=2, y=2))
    tower = get_site_at_cell(game, map_stage, MapPosition(x=3, y=2))

    assert camp is not None and camp.name == CAMP
    assert tower is not None and tower.name == TOWER
    assert get_site_at_cell(game, map_stage, MapPosition(x=0, y=0)) is None


###############################################################################
# 区域图
###############################################################################
def test_get_adjacent_regions_lists_children_but_not_the_map() -> None:
    game = build_world()

    assert [stage.name for stage in get_adjacent_regions(game, entity(game, HERE))] == [
        FIRE_ROOM
    ]


def test_get_adjacent_regions_lists_the_parent_but_not_the_map() -> None:
    game = build_world()
    actor = entity(game, HERE)
    actor.replace(ActorComponent, FIRE_ROOM)

    assert [stage.name for stage in get_adjacent_regions(game, actor)] == [CAMP]


def test_get_adjacent_regions_is_empty_at_a_leaf_site_root() -> None:
    game = build_world()

    assert get_adjacent_regions(game, entity(game, SENTRY)) == []


def test_get_adjacent_regions_is_refused_on_the_map() -> None:
    game = build_world()

    with pytest.raises(AssertionError, match="站在大地图上"):
        get_adjacent_regions(game, entity(game, WANDERER))
