"""地点内的计划：这一刻的区域、在场者与相邻区域。

地点内部是场所：有环境、有在场者、有可以走过去的相邻区域，也可以离开地点回到大地图。
"""

from typing import (
    Awaitable,
    Callable,
    Dict,
    Final,
    List,
    Tuple,
    Type,
    Union,
    final,
    override,
)

from ...entitas import Entity, GroupEvent, Matcher, ReactiveProcessor
from ...entitas.components import Component
from ...llm import ToolDefinition, ToolFunction
from ...models import (
    ActorComponent,
    AppearanceComponent,
    EnvironmentComponent,
    ExitSiteAction,
    MoveWithinSiteAction,
    PlanAction,
    SpeakAction,
    WaitAction,
)
from ...utils import prompt_builder
from ..context import SRPGGame
from ..entities.queries import (
    get_actors_in_stage,
    get_adjacent_regions,
    is_on_map,
    resolve_stage_entity,
)
from .plan_mixin import PlanMixin

_NO_ENVIRONMENT: Final[str] = "（暂无环境描述）"

############################################################################################################
# 地点内能发起的行为
_SPEAK_TOOL: Final[ToolDefinition] = ToolDefinition(
    function=ToolFunction(
        name="speak",
        description="对同一区域里的人说一句话或一段话。",
        parameters={
            "type": "object",
            "properties": {"content": {"type": "string", "description": "要说的话"}},
            "required": ["content"],
        },
    )
)

_MOVE_WITHIN_TOOL: Final[ToolDefinition] = ToolDefinition(
    function=ToolFunction(
        name="move_within",
        description="在地点内部走到一个相邻的区域（子区域或父区域）。",
        parameters={
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "目标区域的名字"}
            },
            "required": ["destination"],
        },
    )
)

_EXIT_TOOL: Final[ToolDefinition] = ToolDefinition(
    function=ToolFunction(
        name="exit",
        description="离开这个地点，回到大地图上它所在的那一格。",
        parameters={"type": "object", "properties": {}},
    )
)

_WAIT_TOOL: Final[ToolDefinition] = ToolDefinition(
    function=ToolFunction(
        name="wait",
        description="这一轮什么都不做，留在原地。",
        parameters={"type": "object", "properties": {}},
    )
)

_SITE_TOOLS: Final[List[ToolDefinition]] = [
    _SPEAK_TOOL,
    _MOVE_WITHIN_TOOL,
    _EXIT_TOOL,
    _WAIT_TOOL,
]

_SITE_ACTIONS: Final[Tuple[Type[Component], ...]] = (
    SpeakAction,
    MoveWithinSiteAction,
    ExitSiteAction,
    WaitAction,
)


############################################################################################################
@prompt_builder
def site_plan_prompt(
    *,
    region_name: str,
    environment: str,
    actors: List[str],
    destinations: List[str],
    compact: bool = False,
) -> str:
    """地点内计划的任务说明：这一刻的区域、环境、在场者与相邻区域。

    ``compact`` 给记忆用：环境收成一句、在场者只留名字。发出去的提示词始终是完整版，
    记忆里留摘要——过去那一刻的细节不必陪着角色走完后面所有回合。
    """
    lines = [
        f"当前区域：{region_name}",
        f"环境：{_compact_text(environment) if compact else environment}",
        "",
        "在场角色：",
    ]
    if compact:
        lines.extend(f"- {actor.split('：')[0]}" for actor in actors)
    else:
        lines.extend(f"- {actor}" for actor in actors)
    lines.extend(["", "可去之处："])
    lines.extend(f"- {item}" for item in destinations)
    if not destinations:
        lines.append("- 无")
    lines.extend(
        [
            "",
            "用工具表达你这一轮的行动：说话、在地点内移动、离开地点，或者原地不动。一次只做一件事。",
        ]
    )
    return "\n".join(lines)


############################################################################################################
@final
class SitePlanSystem(ReactiveProcessor, PlanMixin):
    """消费 ``PlanAction``：给地点里的角色跑一轮计划。"""

    ##########################################################################################
    def __init__(self, game: SRPGGame) -> None:
        ReactiveProcessor.__init__(self, game)
        PlanMixin.__init__(self, game)

    ##########################################################################################
    @override
    def get_trigger(self) -> Dict[Matcher, GroupEvent]:
        return {Matcher(all_of=[PlanAction, ActorComponent]): GroupEvent.ADDED}

    ##########################################################################################
    @override
    def filter(self, entity: Entity) -> bool:
        """只处理仍在地点里、且挂着计划动作的角色。"""
        return entity.has(ActorComponent, PlanAction) and not is_on_map(
            self._game, entity
        )

    ##########################################################################################
    @override
    def allowed_actions(self) -> Tuple[Type[Component], ...]:
        return _SITE_ACTIONS

    ##########################################################################################
    @override
    async def react(self, entities: List[Entity]) -> None:
        for entity in sorted(entities, key=lambda item: item.index):
            # 「该想一次」在处理的同一刻被消费；行为动作留给后面的 system
            entity.remove(PlanAction)
            record_message = site_plan_input(self._game, entity, compact=True)
            decided = self.predecided_action(entity)
            if decided is not None:
                self.record_decision(entity, action=decided, prompt=record_message)
                continue
            await self.run_plan(
                entity,
                input_message=site_plan_input(self._game, entity, compact=False),
                record_message=record_message,
                tools=_SITE_TOOLS,
                handlers=self._handlers(entity),
            )

    ##########################################################################################
    ##########################################################################################
    def _handlers(
        self, entity: Entity
    ) -> Dict[str, Callable[..., Union[str, Awaitable[str]]]]:
        return {
            "speak": lambda content: self.mount_action(entity, SpeakAction, content),
            "move_within": lambda destination: self.mount_action(
                entity, MoveWithinSiteAction, destination
            ),
            "exit": lambda: self.mount_action(entity, ExitSiteAction),
            "wait": lambda: self.mount_action(entity, WaitAction),
        }


############################################################################################################
def site_plan_input(srpg_game: SRPGGame, entity: Entity, *, compact: bool) -> str:
    """地点内部这一刻的输入；计划与接管共用，只有 compact 不同。"""
    region_entity = resolve_stage_entity(srpg_game, entity)
    assert region_entity is not None, f"{entity.name} 无所在舞台"
    return site_plan_prompt(
        region_name=region_entity.name,
        environment=_environment_of(region_entity),
        actors=[
            _describe_actor(actor)
            for actor in sorted(
                get_actors_in_stage(srpg_game, region_entity),
                key=lambda item: item.index,
            )
        ],
        destinations=[stage.name for stage in get_adjacent_regions(srpg_game, entity)],
        compact=compact,
    )


############################################################################################################
def _compact_text(text: str, *, limit: int = 40) -> str:
    """取第一句，超长截断——记忆里的环境只需要认得出「这是哪儿」。"""
    head = text.split("。")[0]
    if len(head) <= limit:
        return head
    return f"{head[:limit]}…"


############################################################################################################
def _environment_of(stage_entity: Entity) -> str:
    if not stage_entity.has(EnvironmentComponent):
        return _NO_ENVIRONMENT
    return stage_entity.get(EnvironmentComponent).narrative


############################################################################################################
def _describe_actor(actor: Entity) -> str:
    """一行一个角色：名字加此刻的样子。"""
    if not actor.has(AppearanceComponent):
        return actor.name
    return f"{actor.name}：{actor.get(AppearanceComponent).appearance}"


###############################################################################
__all__ = ["SitePlanSystem", "site_plan_input", "site_plan_prompt"]
