"""描述刷新链路：状态守卫、两个反应式处理器、主动与自动两条路径。

链路的形状是「收集 → 反应」：``StaleDescriptionSystem`` 只在描述仍等于底稿时挂动作，
两个反应式处理器消费动作去问 LLM，动作在收尾被清掉。因此自动路径天然幂等——写过一次
就不再写；想强制重写，直接挂动作即可。
"""

from typing import Callable, Dict, List, Sequence

import pytest

from ai_srpg.entitas import Entity
from ai_srpg.game.assembly import create_srpg_game
from ai_srpg.game.context import SRPGGame
from ai_srpg.game.entities import build_from_blueprint
from ai_srpg.game.lifecycle import initialize_pipeline
from ai_srpg.game.memory import add_human_message, get_agent_memory
from ai_srpg.game.pipelines import process_pipeline
from ai_srpg.game.systems.appearance_refresh_system import (
    AppearanceRefreshSystem,
    appearance_prompt,
)
from ai_srpg.game.systems.environment_refresh_system import (
    EnvironmentRefreshSystem,
    environment_prompt,
)
from ai_srpg.game.systems.stale_description_system import StaleDescriptionSystem
from ai_srpg.llm import ChatCompletionRequest, ChatCompletionResult
from ai_srpg.models import (
    ActorBlueprint,
    ActorComponent,
    AppearanceComponent,
    Blueprint,
    EnvironmentComponent,
    GridComponent,
    HumanMessage,
    MapPosition,
    RefreshAppearanceAction,
    RefreshEnvironmentAction,
    StageBlueprint,
    StageComponent,
)
from ai_srpg.utils import get_prompt_builders
from fake_llm import FAKE_DESCRIPTION_PREFIX, failed_completion, fake_completion

STAGE = "舞台.营地"
ACTOR = "角色.甲"
BASE_BODY = "瘦削，洗得发白的旧斗篷"
BASE_ENVIRONMENT = "碎石浅坑，灰土，风从旧道来"


###############################################################################
def _actor(appearance: str | None = None) -> ActorBlueprint:
    components: Dict[str, Dict[str, object]] = {
        ActorComponent.__name__: {"current_stage": STAGE},
        AppearanceComponent.__name__: {"base_body": BASE_BODY},
    }
    if appearance is not None:
        components[AppearanceComponent.__name__]["appearance"] = appearance
    return ActorBlueprint(
        name=ACTOR,
        system_message=f"{ACTOR} 的设定",
        components=components,
    )


def _camp(narrative: str | None = None) -> StageBlueprint:
    components: Dict[str, Dict[str, object]] = {
        StageComponent.__name__: {},
        EnvironmentComponent.__name__: {"base_environment": BASE_ENVIRONMENT},
    }
    if narrative is not None:
        components[EnvironmentComponent.__name__]["narrative"] = narrative
    return StageBlueprint(
        name=STAGE,
        system_message=f"{STAGE} 的设定",
        components=components,
        map_position=MapPosition(x=2, y=2),
    )


def _game(*, appearance: str | None = None, narrative: str | None = None) -> SRPGGame:
    game = create_srpg_game(name="RefreshTest")
    build_from_blueprint(
        game,
        Blueprint(
            name="RefreshTest",
            campaign_setting="设定",
            global_rules="规则",
            stage_tree=StageBlueprint(
                name="舞台.大地图",
                system_message="舞台.大地图 的设定",
                components={
                    StageComponent.__name__: {},
                    GridComponent.__name__: {"width": 5, "height": 5},
                },
                children=[_camp(narrative)],
            ),
            actors=[_actor(appearance)],
            worlds=[],
        ),
    )
    return game


def _entity(game: SRPGGame, name: str) -> Entity:
    entity = game.get_entity_by_name(name)
    assert entity is not None
    return entity


ResultsFactory = Callable[[Sequence[ChatCompletionRequest]], List[ChatCompletionResult]]


def _record_requests(
    monkeypatch: pytest.MonkeyPatch, results_factory: ResultsFactory = fake_completion
) -> List[ChatCompletionRequest]:
    """替换 batch 调用，返回被调用时收集到的请求列表。"""
    captured: List[ChatCompletionRequest] = []

    async def _fake(
        requests: Sequence[ChatCompletionRequest], *, max_concurrency: int = 2
    ) -> List[ChatCompletionResult]:
        captured.extend(requests)
        return results_factory(requests)

    monkeypatch.setattr(
        "ai_srpg.game.systems.description_refresh_mixin.batch_complete", _fake
    )
    return captured


###############################################################################
# 收集端：状态守卫
###############################################################################
async def test_untouched_descriptions_are_marked_for_refresh() -> None:
    """底稿还没被改写过，角色与舞台都被挂上动作。"""
    game = _game()

    await StaleDescriptionSystem(game).execute()

    assert _entity(game, ACTOR).has(RefreshAppearanceAction)
    assert _entity(game, STAGE).has(RefreshEnvironmentAction)


async def test_customized_descriptions_are_not_marked() -> None:
    """已经改写过的描述不再挂动作——这就是自动路径的幂等来源。"""
    game = _game(appearance="已经改过的样子", narrative="已经改过的环境")

    await StaleDescriptionSystem(game).execute()

    assert not _entity(game, ACTOR).has(RefreshAppearanceAction)
    assert not _entity(game, STAGE).has(RefreshEnvironmentAction)


async def test_marking_twice_is_harmless() -> None:
    """同一轮执行两次不会重复挂动作，也不会报错。"""
    game = _game()
    system = StaleDescriptionSystem(game)

    await system.execute()
    await system.execute()

    assert _entity(game, ACTOR).has(RefreshAppearanceAction)


###############################################################################
# 反应端：写回组件
###############################################################################
async def test_actor_appearance_is_rewritten_and_base_kept() -> None:
    game = _game()
    actor = _entity(game, ACTOR)
    system = AppearanceRefreshSystem(game)
    system.activate()

    actor.replace(RefreshAppearanceAction)
    await system.execute()

    appearance = actor.get(AppearanceComponent)
    assert appearance.appearance.startswith(FAKE_DESCRIPTION_PREFIX)
    assert appearance.base_body == BASE_BODY


async def test_actor_memory_records_the_update() -> None:
    """刷新之后记忆里留下一条「已更新为…」的确认，底稿同时在场。"""
    game = _game()
    actor = _entity(game, ACTOR)
    system = AppearanceRefreshSystem(game)
    system.activate()

    actor.replace(RefreshAppearanceAction)
    await system.execute()

    last = get_agent_memory(game, actor).messages[-1]
    assert last.content.startswith("你的外观已更新为：")
    assert BASE_BODY in last.content


async def test_stage_memory_records_the_update() -> None:
    """舞台同样留一条确认，并且写的是环境底稿。"""
    game = _game()
    stage = _entity(game, STAGE)
    system = EnvironmentRefreshSystem(game)
    system.activate()

    stage.replace(RefreshEnvironmentAction)
    await system.execute()

    last = get_agent_memory(game, stage).messages[-1]
    assert last.content.startswith("你的环境已更新为：")
    assert BASE_ENVIRONMENT in last.content


async def test_stage_environment_is_rewritten_and_base_kept() -> None:
    game = _game()
    stage = _entity(game, STAGE)
    system = EnvironmentRefreshSystem(game)
    system.activate()

    stage.replace(RefreshEnvironmentAction)
    await system.execute()

    environment = stage.get(EnvironmentComponent)
    assert environment.narrative.startswith(FAKE_DESCRIPTION_PREFIX)
    assert environment.base_environment == BASE_ENVIRONMENT


async def test_each_system_only_reacts_to_its_own_action() -> None:
    """挂错动作不该触发另一个系统的改写。"""
    game = _game()
    actor = _entity(game, ACTOR)
    appearance_system = AppearanceRefreshSystem(game)
    appearance_system.activate()

    actor.replace(RefreshEnvironmentAction)
    await appearance_system.execute()

    assert actor.get(AppearanceComponent).appearance == BASE_BODY


###############################################################################
# 提示词与历史：各走各的记忆与任务说明
###############################################################################
async def test_requests_carry_own_memory_and_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """角色用外观说明、舞台用环境说明，历史都是各自的 agent 记忆。"""
    game = _game()
    captured = _record_requests(monkeypatch)

    await initialize_pipeline(game)
    await process_pipeline(game.pipeline, None)

    instructions = {request.label: request.input_message for request in captured}
    assert instructions[f"appearance:{ACTOR}"] == appearance_prompt()
    assert instructions[f"environment:{STAGE}"] == environment_prompt()

    for request in captured:
        name = request.label.split(":", 1)[1]
        memory = get_agent_memory(game, _entity(game, name))
        assert request.messages[0].content == memory.messages[0].content


###############################################################################
def test_both_prompts_are_registered_builders() -> None:
    """两条任务说明都登记在提示词注册表里，可被枚举出来审查或预演。"""
    builders = get_prompt_builders()

    for builder in (appearance_prompt, environment_prompt):
        key = f"{builder.__module__}.{builder.__qualname__}"
        assert builders[key] is builder
        assert builder().strip() != ""


async def test_environment_history_skips_event_broadcasts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件广播只说明谁在场、谁做了什么，环境刷新不该读到它。"""
    game = _game()
    stage = _entity(game, STAGE)
    add_human_message(
        game,
        stage,
        HumanMessage(content="舞台.营地：当前在场 角色.甲。", agent_event="none"),
    )
    captured = _record_requests(monkeypatch)

    system = EnvironmentRefreshSystem(game)
    system.activate()
    stage.replace(RefreshEnvironmentAction)
    await system.execute()

    (request,) = captured
    contents = [message.content for message in request.messages]
    assert contents[0] == get_agent_memory(game, stage).messages[0].content
    assert not any("当前在场" in content for content in contents)


###############################################################################
# 失败路径
###############################################################################
async def test_llm_failure_keeps_the_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """生成失败时什么都不写：外观仍等于底稿，下一轮还会再试。"""
    _record_requests(monkeypatch, failed_completion)
    game = _game()
    actor = _entity(game, ACTOR)
    system = AppearanceRefreshSystem(game)
    system.activate()

    actor.replace(RefreshAppearanceAction)
    await system.execute()

    appearance = actor.get(AppearanceComponent)
    assert appearance.appearance == appearance.base_body == BASE_BODY
    assert (
        not get_agent_memory(game, actor)
        .messages[-1]
        .content.startswith("你的外观已更新为：")
    )


async def test_batch_exception_keeps_the_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """整批调用抛异常也不炸：底稿保持，下一轮守卫会再挂动作。"""

    async def _boom(*args: object, **kwargs: object) -> List[ChatCompletionResult]:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "ai_srpg.game.systems.description_refresh_mixin.batch_complete", _boom
    )
    game = _game()
    actor = _entity(game, ACTOR)
    system = AppearanceRefreshSystem(game)
    system.activate()

    actor.replace(RefreshAppearanceAction)
    await system.execute()

    assert actor.get(AppearanceComponent).appearance == BASE_BODY


###############################################################################
# 主动路径：直接挂动作强制重写
###############################################################################
async def test_manual_action_forces_rewrite_of_customized_description() -> None:
    """已经改写过的描述，挂上动作仍会被重写——守卫只拦自动路径。"""
    game = _game(appearance="很久以前的样子")
    actor = _entity(game, ACTOR)
    system = AppearanceRefreshSystem(game)
    system.activate()

    await StaleDescriptionSystem(game).execute()
    assert not actor.has(RefreshAppearanceAction)

    actor.replace(RefreshAppearanceAction)
    await system.execute()

    assert actor.get(AppearanceComponent).appearance.startswith(FAKE_DESCRIPTION_PREFIX)


###############################################################################
# 整条 pipeline：自动、幂等、动作每轮清空
###############################################################################
async def test_pipeline_refreshes_once_then_stays_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game()
    await initialize_pipeline(game)
    captured = _record_requests(monkeypatch)

    await process_pipeline(game.pipeline, None)
    first_pass = len(captured)
    assert first_pass == 2  # 一个角色 + 一个舞台

    await process_pipeline(game.pipeline, None)
    assert len(captured) == first_pass  # 第二轮没有任何刷新请求

    for name in (ACTOR, STAGE):
        entity = _entity(game, name)
        assert not entity.has(RefreshAppearanceAction, RefreshEnvironmentAction)
