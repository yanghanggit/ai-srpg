"""蓝图：构建期输入，描述一局游戏要落进 ECS 的东西。

一个实体只承载三样东西：名字、进游戏后的第一条记忆（``system_message``）、组件数据。
声明类把类别写在类型上——装配期据此要求实体带对了标记组件，运行期的行为差异全部由
组件承担，因此这里没有类别枚举。

舞台按树存储：根是大地图（自带网格），直接子舞台是地点，地点内部是图；角色仍然只属于
某一个舞台。名字里用 ``.`` 分隔只是给人看的，引擎不做任何拆分或推断。
"""

from typing import Dict, Iterator, List, Optional, Tuple, final

from pydantic import BaseModel, Field

from ..entitas import EntityData


###############################################################################################################################################
@final
class MapPosition(BaseModel):
    """大地图上的格子坐标（左上角为原点）。"""

    x: int = Field(ge=0)
    y: int = Field(ge=0)


###############################################################################################################################################
@final
class ActorBlueprint(BaseModel):
    """角色声明；所在舞台写在 ``ActorComponent.current_stage`` 里。"""

    name: str
    system_message: str
    components: EntityData = {}
    assets: Dict[str, str] = Field(
        default_factory=dict
    )  # 资源键（业务层约定）-> meta 路径（.assets/image/<file>.meta）


###############################################################################################################################################
@final
class StageBlueprint(BaseModel):
    """舞台声明；子树关系由 ``children`` 表达，父指针由装配期写入。"""

    name: str
    system_message: str
    components: EntityData = {}
    assets: Dict[str, str] = Field(
        default_factory=dict
    )  # 资源键（业务层约定）-> meta 路径（.assets/image/<file>.meta）

    # 地点在大地图上的位置；大地图本身与地点内部的区域都不需要
    map_position: Optional[MapPosition] = None

    children: List["StageBlueprint"] = Field(default_factory=list)


StageBlueprint.model_rebuild()


###############################################################################################################################################
@final
class WorldBlueprint(BaseModel):
    """世界声明：高于所有舞台但不出场，只给因果、不给行动。"""

    name: str
    system_message: str
    components: EntityData = {}


###############################################################################################################################################################
@final
class Blueprint(BaseModel):
    """一局的构建输入：世界、舞台树与角色，加上组装提示词用的故事级设定。"""

    name: str
    campaign_setting: str  # 组装 system_message 用，不进 ECS
    global_rules: (
        str  # 所有实体共同遵守的纯机制规则（扮演契约、实体、全名、位置与移动）
    )
    worlds: List[WorldBlueprint]
    stage_tree: StageBlueprint
    actors: List[ActorBlueprint]


###############################################################################################################################################
def walk_stages(
    stage_tree: StageBlueprint, parent: Optional[str] = None
) -> Iterator[Tuple[StageBlueprint, Optional[str]]]:
    """按先序产出 (舞台声明, 父舞台名)；大地图的父舞台名为 ``None``。"""
    yield stage_tree, parent
    for child in stage_tree.children:
        yield from walk_stages(child, stage_tree.name)


###############################################################################
__all__ = [
    "ActorBlueprint",
    "Blueprint",
    "MapPosition",
    "StageBlueprint",
    "WorldBlueprint",
    "walk_stages",
]
