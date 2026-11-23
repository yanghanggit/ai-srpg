"""接管一个角色：把玩家下的命令变成同一 pass 里的一次「决策」。

命令不直接写记忆，而是挂上「该想一次」与行为动作两个组件：计划系统在 pipeline 的
原位看到已决定的动作就不再问模型，只把决策写成记忆。这样接管与自主的记忆顺序与
形状完全一致——先有这一轮的环境与在场者，再有自己的决定。
"""

from typing import Type

from ..entitas import Entity
from ..entitas.components import Component
from ..models import PlanAction
from .context import SRPGGame
from .entities.action_rules import action_arguments


############################################################################################################
def mount_command(srpg_game: SRPGGame, actor: Entity, action: Component) -> None:
    """挂上「该想一次」与行为动作；守卫与绑定由调用方先校验。"""
    action_type: Type[Component] = type(action)
    actor.replace(PlanAction)
    actor.replace(action_type, *action_arguments(action))


###############################################################################
__all__ = ["mount_command"]
