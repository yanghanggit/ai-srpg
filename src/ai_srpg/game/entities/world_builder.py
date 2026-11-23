"""从蓝图构建实体。

装配期只做三件事：按名字建实体、把 ``system_message`` 写成 ``memories[0]``、
按 ``components`` 逐项挂组件。生成值（创建顺序、实体 ID、舞台树的父指针）由引擎填，
其余状态一律来自内容侧的组件数据——因此这里没有跨实体查找，也没有中间态。
"""

import uuid
from typing import Any, Dict, Optional, Set, Tuple, Type, Union

from ...entitas import Entity
from ...entitas.components import Component
from ...models import (
    ActorBlueprint,
    ActorComponent,
    Blueprint,
    GridComponent,
    IdentityComponent,
    MapPositionComponent,
    SiteComponent,
    StageBlueprint,
    StageComponent,
    SystemMessage,
    WorldBlueprint,
    WorldComponent,
    resolve_component_type,
    walk_stages,
)
from ..context import SRPGGame
from ..memory.access import add_system_message

BlueprintEntity = Union[ActorBlueprint, StageBlueprint, WorldBlueprint]


###############################################################################################################################################
def build_from_blueprint(srpg_game: SRPGGame, blueprint: Blueprint) -> None:
    """按蓝图装配游戏世界：世界、舞台树、角色。

    只装配世界，不涉及玩家：谁能控制哪个角色由 ``bind_player_actor`` 在进场时决定。
    """
    assert srpg_game.entity_count == 0, "游戏中有实体，不能创建新的游戏"

    _assert_unique_names(blueprint)

    for world in blueprint.worlds:
        _create_entity(srpg_game, world, WorldComponent, "世界")

    _create_stage_tree(srpg_game, blueprint.stage_tree)

    stage_names = {stage.name for stage, _ in walk_stages(blueprint.stage_tree)}
    for actor in blueprint.actors:
        actor_entity = _create_entity(srpg_game, actor, ActorComponent, "角色")
        _assert_actor_on_declared_stage(actor_entity, stage_names)


###############################################################################################################################################
def _create_entity(
    srpg_game: SRPGGame,
    model: BlueprintEntity,
    marker: Type[Component],
    kind: str,
    *,
    derived: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Entity:
    """按蓝图声明建一个实体；缺标记组件即视为内容写错。

    ``derived`` 是引擎算出来的组件字段（例如舞台的父指针），会覆盖内容侧的同名值：
    结构关系只在蓝图里写一次，不在组件数据里复述。
    """
    entity = srpg_game.create_entity(model.name)
    entity.add(
        IdentityComponent,
        srpg_game.entity_naming.next_creation_order(),
        str(uuid.uuid4()),
    )

    assert (
        model.name in model.system_message
    ), f"{kind} {model.name} 的系统消息缺少实体名"
    add_system_message(srpg_game, entity, SystemMessage(content=model.system_message))

    for comp_name, comp_data in model.components.items():
        data = dict(comp_data)
        if derived is not None:
            data.update(derived.get(comp_name, {}))
        comp_class = resolve_component_type(comp_name, data)
        entity.set(comp_class, comp_class(**data))

    assert entity.has(marker), f"{kind} {model.name} 缺少标记组件 {marker.__name__}"
    return entity


###############################################################################################################################################
def _create_stage_tree(srpg_game: SRPGGame, root: StageBlueprint) -> None:
    """按先序建舞台树：父舞台先建，地点的位置按大地图的网格校验。"""
    grids: Dict[str, GridComponent] = {}
    occupied: Dict[str, Set[Tuple[int, int]]] = {}

    for stage, parent_name in walk_stages(root):
        assert (
            SiteComponent.__name__ not in stage.components
        ), f"SiteComponent 由装配期按树位置派生，蓝图不要声明: {stage.name}"

        entity = _create_entity(
            srpg_game,
            stage,
            StageComponent,
            "舞台",
            derived={StageComponent.__name__: {"parent_stage": parent_name}},
        )
        if parent_name == root.name:
            # 地点不是内容声明的类型，而是树上的位置：大地图的直接子舞台。
            entity.add(SiteComponent)
        if stage.map_position is not None:
            entity.set(
                MapPositionComponent,
                MapPositionComponent(x=stage.map_position.x, y=stage.map_position.y),
            )

        grid = entity.get(GridComponent) if entity.has(GridComponent) else None
        if parent_name is None:
            assert (
                grid is not None
            ), f"根舞台是大地图，必须带网格（缺 GridComponent）: {stage.name}"
            assert (
                stage.map_position is None
            ), f"根舞台是大地图，没有大地图位置: {stage.name}"
        else:
            assert grid is None, f"只有大地图（根舞台）可以有网格: {stage.name}"
            _assert_placed_on_parent(stage, parent_name, grids, occupied)

        if grid is not None:
            grids[stage.name] = grid


###############################################################################################################################################
def _assert_placed_on_parent(
    stage: StageBlueprint,
    parent_name: str,
    grids: Dict[str, GridComponent],
    occupied: Dict[str, Set[Tuple[int, int]]],
) -> None:
    """大地图有网格时，地点必须落在格内且一格一物。"""
    grid = grids.get(parent_name)
    if grid is None:
        assert (
            stage.map_position is None
        ), f"舞台 {parent_name} 没有网格，{stage.name} 不能声明大地图位置"
        return

    assert (
        stage.map_position is not None
    ), f"地点 {stage.name} 必须声明它在大地图上的位置"
    cell = (stage.map_position.x, stage.map_position.y)
    assert grid.contains(
        *cell
    ), f"地点 {stage.name} 的位置 {cell} 超出 {parent_name} 的 {grid.width}x{grid.height} 网格"
    taken = occupied.setdefault(parent_name, set())
    assert cell not in taken, f"大地图格 {cell} 已被占用: {stage.name}"
    taken.add(cell)


###############################################################################################################################################
def _assert_unique_names(blueprint: Blueprint) -> None:
    """实体名是 ECS 的索引键；重名会静默覆盖，必须在装配期拦住。"""
    names = [world.name for world in blueprint.worlds]
    names.extend(actor.name for actor in blueprint.actors)
    names.extend(stage.name for stage, _ in walk_stages(blueprint.stage_tree))

    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert (
        not duplicates
    ), f"蓝图里有重名实体（名字是索引键，必须全局唯一）: {duplicates}"


###############################################################################################################################################
def _assert_actor_on_declared_stage(entity: Entity, stage_names: Set[str]) -> None:
    """角色的 ``current_stage`` 必须指向蓝图里声明过的舞台。"""
    current_stage = entity.get(ActorComponent).current_stage
    assert (
        current_stage in stage_names
    ), f"角色 {entity.name} 的所在舞台不存在: {current_stage}"


###############################################################################
__all__ = ["build_from_blueprint"]
