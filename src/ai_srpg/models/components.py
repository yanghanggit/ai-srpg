"""ECS 组件定义。添加到实体后由对应系统读取处理。

实体名在 ``Entity.name`` 与快照的键里，组件不再重复保存它；标记组件只带
真正的状态（例如角色所在的舞台）。
"""

from typing import Optional, final

from pydantic import Field, model_validator

from ..entitas.components import Component
from .registry import register_component_type


############################################################################################################
@final
@register_component_type
class IdentityComponent(Component):
    """为实体提供创建顺序与全局唯一 ID（名字由实体自身持有）。"""

    creation_order: int  # 序列化时保证顺序一致性
    entity_id: str  # UUID 格式


############################################################################################################
@final
@register_component_type
class WorldComponent(Component):
    """标记实体为世界级实体（全局、唯一、独立于舞台）。"""


############################################################################################################
@final
@register_component_type
class StageComponent(Component):
    """标记实体为舞台（空间单位），记录挂在哪个舞台之下。"""

    parent_stage: Optional[str] = None  # 树上层的舞台；根为 None


############################################################################################################
@final
@register_component_type
class GridComponent(Component):
    """舞台的网格坐标系：左上角为原点，``x ∈ [0, width)``、``y ∈ [0, height)``。

    网格属于大地图；地点占据其中一个格子，地点内部是一张图、没有坐标。
    """

    width: int = Field(gt=0)
    height: int = Field(gt=0)

    def contains(self, x: int, y: int) -> bool:
        """这一格是否落在网格内。"""
        return 0 <= x < self.width and 0 <= y < self.height


############################################################################################################
@final
@register_component_type
class MapPositionComponent(Component):
    """在大地图网格上的格子坐标（左上角为原点）：地点与站在大地图上的角色都用它。"""

    x: int = Field(ge=0)
    y: int = Field(ge=0)


############################################################################################################
@final
@register_component_type
class ActorComponent(Component):
    """标记实体为角色类型，记录当前所在舞台。"""

    current_stage: str  # 当前所在舞台名称


############################################################################################################
@final
@register_component_type
class EnvironmentComponent(Component):
    """舞台环境：底稿 + 当前叙述，``narrative`` 缺省时等于 ``base_environment``。

    叙述只写舞台自身，不写在场者：角色状态不该从环境里推断出来。
    """

    base_environment: str
    narrative: str = ""

    @model_validator(mode="after")
    def _fill_narrative(self) -> "EnvironmentComponent":
        if not self.narrative:
            object.__setattr__(self, "narrative", self.base_environment)
        return self


############################################################################################################
@final
@register_component_type
class NPCComponent(Component):
    """标记角色是 NPC；目前只是类型记录。"""


############################################################################################################
@final
@register_component_type
class PlayerComponent(Component):
    """标记角色由某玩家控制；一个玩家控制一个角色。"""

    user_name: str


############################################################################################################
@final
@register_component_type
class DestroyComponent(Component):
    """标记实体在下一帧销毁。"""


############################################################################################################
@final
@register_component_type
class AppearanceComponent(Component):
    """存储角色外观描述；未给出 ``appearance`` 时与 ``base_body`` 相同。"""

    base_body: str  # 基础身体形态描述（不含装备）
    appearance: str = ""  # 最终外观描述（含装备）

    @model_validator(mode="after")
    def _fill_appearance(self) -> "AppearanceComponent":
        if not self.appearance:
            object.__setattr__(self, "appearance", self.base_body)
        return self


###############################################################################
__all__ = [
    "ActorComponent",
    "AppearanceComponent",
    "DestroyComponent",
    "EnvironmentComponent",
    "GridComponent",
    "IdentityComponent",
    "MapPositionComponent",
    "NPCComponent",
    "PlayerComponent",
    "StageComponent",
    "WorldComponent",
]
