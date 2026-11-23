"""测试配置与共享夹具。

描述刷新会真的调用 LLM；测试里统一替换成固定文本（见 ``fake_llm``），
避免联网与不确定性。
"""

from typing import List, Sequence

import pytest

from ai_srpg.game.assembly import create_srpg_game
from ai_srpg.game.context import SRPGGame
from ai_srpg.game.events.sink import RecordingEventSink
from ai_srpg.llm import ChatCompletionRequest, ChatCompletionResult
from ai_srpg.models import (
    ActorBlueprint,
    ActorComponent,
)
from fake_llm import fake_agent_loop, fake_completion


@pytest.fixture(autouse=True)
def offline_descriptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """把描述刷新用到的 LLM 调用换成固定回复（不联网）。"""

    async def _fake(
        requests: Sequence[ChatCompletionRequest], *, max_concurrency: int = 2
    ) -> List[ChatCompletionResult]:
        return fake_completion(requests)

    monkeypatch.setattr(
        "ai_srpg.game.systems.description_refresh_mixin.batch_complete", _fake
    )


@pytest.fixture(autouse=True)
def offline_plans(monkeypatch: pytest.MonkeyPatch) -> None:
    """计划系统用 agent loop 会联网；测试里换成空转实现。"""
    monkeypatch.setattr("ai_srpg.game.systems.plan_mixin.agent_loop", fake_agent_loop)


@pytest.fixture
def sample_game() -> SRPGGame:
    """Create a sample game for testing."""
    return create_srpg_game(name="test_blueprint", events=RecordingEventSink())


@pytest.fixture
def sample_actor() -> ActorBlueprint:
    """Create a sample actor blueprint for testing."""
    return ActorBlueprint(
        name="test_actor",
        system_message="test system message",
        components={ActorComponent.__name__: {"current_stage": "test_stage"}},
        assets={"portrait": ".assets/image/test.meta"},
    )
