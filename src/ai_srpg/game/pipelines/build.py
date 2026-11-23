"""唯一的游戏流程装配：按业务顺序线性排列全部 system。

这里是游戏业务的核心执行序列。所有 system 每轮都按固定顺序执行，
由 system 自己判断当前 world 状态是否适用；调用方不再选择房间或动作 pipeline。
"""

from ...entitas import ProcessorPipeline
from ...models import ACTION_COMPONENT_TYPES
from ..context import SRPGGame


def build_game_pipeline(srpg_game: SRPGGame) -> ProcessorPipeline:
    """构建全局唯一的线性 system 流程。"""

    ### 不这样就循环引用：systems 依赖 game 领域模块，而 game 装配又依赖 systems。
    from ..systems.action_cleanup_system import ActionCleanupSystem
    from ..systems.appearance_refresh_system import AppearanceRefreshSystem
    from ..systems.auto_compact_system import AutoCompactSystem
    from ..systems.compact_system import CompactSystem
    from ..systems.destroy_entity_system import DestroyEntitySystem
    from ..systems.enter_site_system import EnterSiteSystem
    from ..systems.environment_refresh_system import EnvironmentRefreshSystem
    from ..systems.epilogue_system import EpilogueSystem
    from ..systems.exit_site_system import ExitSiteSystem
    from ..systems.map_plan_system import MapPlanSystem
    from ..systems.move_within_site_system import MoveWithinSiteSystem
    from ..systems.prologue_system import PrologueSystem
    from ..systems.site_plan_system import SitePlanSystem
    from ..systems.speak_system import SpeakSystem
    from ..systems.stale_description_system import StaleDescriptionSystem
    from ..systems.travel_system import TravelSystem
    from ..systems.wait_system import WaitSystem

    pipeline = ProcessorPipeline()

    # ---------------------------------------------------------------------
    # 通用前置：每轮固定入口
    # ---------------------------------------------------------------------
    pipeline.add(PrologueSystem(srpg_game))

    # ---------------------------------------------------------------------
    # 业务：「当前描述」的刷新（先判定过期，再由两个反应式处理器重写）。
    # 舞台心跳 StagePulseSystem 保留为可插拔样例，默认管线不挂；需要时在这里 add。
    # ---------------------------------------------------------------------
    pipeline.add(StaleDescriptionSystem(srpg_game))
    pipeline.add(AppearanceRefreshSystem(srpg_game))
    pipeline.add(EnvironmentRefreshSystem(srpg_game))
    pipeline.add(AutoCompactSystem(srpg_game))
    pipeline.add(CompactSystem(srpg_game))

    # 计划：大地图与地点各有各的上下文与动词，靠 filter 的层级判定互斥。
    pipeline.add(SitePlanSystem(srpg_game))
    pipeline.add(MapPlanSystem(srpg_game))

    # 行为：一个动作只做一件事，层级不符的动作不会被处理。
    pipeline.add(SpeakSystem(srpg_game))
    pipeline.add(WaitSystem(srpg_game))
    pipeline.add(TravelSystem(srpg_game))
    pipeline.add(EnterSiteSystem(srpg_game))
    pipeline.add(ExitSiteSystem(srpg_game))
    pipeline.add(MoveWithinSiteSystem(srpg_game))

    # ---------------------------------------------------------------------
    # 通用尾部：清理动作组件、销毁待销毁实体并收尾
    # 顺序不可对调：先清理动作，再销毁实体，最后收尾。
    # ---------------------------------------------------------------------
    pipeline.add(ActionCleanupSystem(srpg_game, ACTION_COMPONENT_TYPES.values()))
    pipeline.add(DestroyEntitySystem(srpg_game))
    pipeline.add(EpilogueSystem(srpg_game))

    return pipeline
