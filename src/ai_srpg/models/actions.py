"""动作组件：一次 pass 内有效，由 ``ActionCleanupSystem`` 在收尾阶段清除。

动作组件是普通组件外加一层声明，装饰器顺序固定：

    @final
    @register_action_component_type
    @register_component_type
    class SomeAction(Component):
        name: str

``register_action_component_type`` 必须写在 ``register_component_type`` 之上——
装饰器自下而上应用，内层先把这个类登记为普通组件。

以后新增动作组件直接写在本模块：导入本模块即完成注册。
"""

from typing import Dict, Final, Type, final

from ..entitas.components import Component
from .registry import COMPONENT_TYPES, ComponentT, register_component_type

############################################################################################################
ACTION_COMPONENT_TYPES: Final[Dict[str, Type[Component]]] = {}


############################################################################################################
def register_action_component_type(cls: Type[ComponentT]) -> Type[ComponentT]:
    """把已注册的组件类再登记为动作组件。

    动作组件必须是已注册的组件（否则不会进快照），因此本装饰器要求
    ``@register_component_type`` 先于它应用。
    """
    if not issubclass(cls, Component):
        raise TypeError(f"{cls.__name__} is not a valid Component class.")

    class_name = cls.__name__
    if class_name not in COMPONENT_TYPES:
        order = "@register_action_component_type 在上、@register_component_type 在下"
        raise ValueError(f"{class_name} 还不是组件：装饰器顺序应为 {order}。")
    if class_name in ACTION_COMPONENT_TYPES:
        raise ValueError(f"Class {class_name} is already registered as an action.")

    ACTION_COMPONENT_TYPES[class_name] = cls
    return cls


############################################################################################################
@final
@register_action_component_type
@register_component_type
class RefreshAppearanceAction(Component):
    """动作：本轮用 LLM 重写该角色的当前外观。"""


############################################################################################################
@final
@register_action_component_type
@register_component_type
class RefreshEnvironmentAction(Component):
    """动作：本轮用 LLM 重写该舞台的当前环境叙述。"""


############################################################################################################
@final
@register_action_component_type
@register_component_type
class ActorPlanAction(Component):
    """动作：本轮让该角色做一次行动计划。"""


############################################################################################################
@final
@register_action_component_type
@register_component_type
class ActorSpeakAction(Component):
    """动作：本轮该角色开口说话。"""

    content: str


############################################################################################################
@final
@register_action_component_type
@register_component_type
class ActorTravelAction(Component):
    """动作：本轮该角色在大地图上移动到相邻一格（不改变所在层）。"""

    x: int
    y: int


############################################################################################################
@final
@register_action_component_type
@register_component_type
class ActorEnterSiteAction(Component):
    """动作：本轮该角色从格子走进那一格上的地点。"""

    site: str


############################################################################################################
@final
@register_action_component_type
@register_component_type
class ActorExitSiteAction(Component):
    """动作：本轮该角色离开所在地点，回到大地图上地点所在的那一格。"""


############################################################################################################
@final
@register_action_component_type
@register_component_type
class ActorMoveWithinSiteAction(Component):
    """动作：本轮该角色在地点内部移动到一个相邻的区域。"""

    destination: str


############################################################################################################
@final
@register_action_component_type
@register_component_type
class ActorWaitAction(Component):
    """动作：本轮该角色留在原地。"""


############################################################################################################
@final
@register_action_component_type
@register_component_type
class CompactMemoryAction(Component):
    """动作：把该实体的历史记忆折叠成一条摘要；``summary`` 为空时用默认摘要。

    动作组件的字段一律必填（组件引擎不套用默认值），「空串表示用默认」由消费方解释。
    """

    summary: str


############################################################################################################
__all__ = [
    "ACTION_COMPONENT_TYPES",
    "ActorEnterSiteAction",
    "ActorExitSiteAction",
    "ActorMoveWithinSiteAction",
    "ActorPlanAction",
    "ActorSpeakAction",
    "ActorTravelAction",
    "ActorWaitAction",
    "CompactMemoryAction",
    "RefreshAppearanceAction",
    "RefreshEnvironmentAction",
    "register_action_component_type",
]
