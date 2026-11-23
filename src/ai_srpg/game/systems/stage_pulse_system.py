"""舞台心跳：每轮把舞台现状广播给舞台内的角色。

它不改世界结构：把「此刻舞台里有哪些角色」写成一条领域事件，再经区域广播进入
agent 记忆，并通过事件出口交给订阅者。大地图不参与：那里没有「在场者」。

定位是「管线里第一个业务 system 的样板」：真实玩法替换或追加它时，发布链路与
job / 会话历史的关联方式保持不变。
"""

from typing import final, override

from ...entitas import ExecuteProcessor
from ...models import StagePulse
from ..entities import get_actors_by_stage, is_map_stage
from .stage_broadcast_mixin import StageBroadcastMixin


@final
class StagePulseSystem(StageBroadcastMixin, ExecuteProcessor):
    """每轮为每个有角色的区域广播一条现状事件。"""

    ############################################################################################################
    @override
    async def execute(self) -> None:
        # 空舞台不广播：没有角色时「谁在场」没有信息量，只会污染记忆与历史
        for stage_entity, actors in get_actors_by_stage(self._game).items():
            if not actors or is_map_stage(stage_entity):
                continue

            names = sorted(actor.name for actor in actors)
            event = StagePulse(
                message=f"{stage_entity.name}：当前在场 {'、'.join(names)}。",
                stage=stage_entity.name,
                actors=tuple(names),
            )
            self.broadcast_at_stage(stage_entity, event)
            self.publish(event)
