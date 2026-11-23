"""实体查询、蓝图装配、玩家绑定与舞台分组查询。

实体创建/销毁/快照序列化是 ``SRPGGame``（``ECSContext``）自身的方法，不在此包内。
"""

from .player_binding import bind_player_actor
from .queries import (
    MapCell,
    get_actor_entity,
    get_actors_by_stage,
    get_actors_by_stage_as_names,
    get_actors_in_stage,
    get_adjacent_regions,
    get_ancestor_stages,
    get_child_stages,
    get_map_position,
    get_map_stage,
    get_player_actor_name,
    get_player_entity,
    get_site,
    get_site_at_cell,
    get_stage_entity,
    get_visible_cells,
    get_world_entity,
    is_map_stage,
    resolve_stage_entity,
)
from .world_builder import build_from_blueprint

__all__ = [
    "MapCell",
    "bind_player_actor",
    "build_from_blueprint",
    "get_actor_entity",
    "get_actors_by_stage",
    "get_actors_by_stage_as_names",
    "get_actors_in_stage",
    "get_adjacent_regions",
    "get_ancestor_stages",
    "get_child_stages",
    "get_map_position",
    "get_map_stage",
    "get_player_actor_name",
    "get_player_entity",
    "get_site",
    "get_site_at_cell",
    "get_stage_entity",
    "get_visible_cells",
    "get_world_entity",
    "is_map_stage",
    "resolve_stage_entity",
]
