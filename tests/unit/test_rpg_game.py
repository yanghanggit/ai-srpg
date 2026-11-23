"""
Unit tests for game lifecycle/entity/memory/broadcast functions

覆盖范围（不重复 test_rpg_agent_memory.py 中已有的用例）：
  - get_agent_memory
  - destroy_entity（含 agent 记忆清理）
  - add_system_message
  - deliver_entities / publish_event
  - StageBroadcastMixin.broadcast_in_region / broadcast_in_map_cell
  - exit / initialize（冒烟测试）
"""

import uuid
from typing import Any

import pytest

from ai_srpg.entitas.entity import Entity
from ai_srpg.game.context import SRPGGame
from ai_srpg.game.events.publish import deliver_entities, publish_event
from ai_srpg.game.lifecycle import (
    exit_game,
    initialize_game,
)
from ai_srpg.game.memory import (
    add_human_message,
    add_system_message,
    get_agent_memory,
)
from ai_srpg.game.systems.stage_broadcast_mixin import StageBroadcastMixin
from ai_srpg.models import (
    ActorComponent,
    GridComponent,
    HumanMessage,
    IdentityComponent,
    MapPositionComponent,
    NoneEvent,
    SiteComponent,
    StageComponent,
    SystemMessage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_MAP_STAGE = "Stage_map"


def _make_stage(
    game: SRPGGame, stage_name: str, *, parent_stage: str | None = _MAP_STAGE
) -> Entity:
    """创建带 StageComponent 的舞台实体；默认当作地点挂在测试大地图下。"""
    if parent_stage == _MAP_STAGE and game.get_entity_by_name(_MAP_STAGE) is None:
        map_entity: Entity = game.create_entity(_MAP_STAGE)
        map_entity.add(StageComponent, None)
        map_entity.add(GridComponent, 5, 5)
    entity: Entity = game.create_entity(stage_name)
    entity.add(StageComponent, parent_stage)
    if parent_stage is not None:
        entity.add(SiteComponent)
    return entity


def _make_actor(game: SRPGGame, actor_name: str, current_stage_name: str) -> Entity:
    """创建带 ActorComponent 的角色实体。"""
    entity: Entity = game.create_entity(actor_name)
    entity.add(ActorComponent, current_stage_name)
    return entity


def _make_entity_with_identity(game: SRPGGame, name: str, order: int) -> Entity:
    """创建带 IdentityComponent 的实体（flush_entities 排序所需）。"""
    entity: Entity = game.create_entity(name)
    entity.add(IdentityComponent, order, str(uuid.uuid4()))
    return entity


def _agent_event(message: str = "hello") -> NoneEvent:
    return NoneEvent(message=message)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def game(sample_game: SRPGGame) -> SRPGGame:
    return sample_game


@pytest.fixture
def actor(game: SRPGGame) -> Entity:
    return game.create_entity("Actor_A")


@pytest.fixture
def second_actor(game: SRPGGame) -> Entity:
    return game.create_entity("Actor_B")


# ---------------------------------------------------------------------------
# get_agent_memory
# ---------------------------------------------------------------------------


class TestGetAgentMemory:
    def test_creates_memory_on_first_access(self, game: Any, actor: Entity) -> None:
        """首次访问不存在的实体时，自动创建 AgentMemory。"""
        assert actor.name not in game.agent_memory_store
        memory = get_agent_memory(game, actor)
        assert memory is not None
        assert actor.name in game.agent_memory_store

    def test_returns_same_object_on_repeated_call(
        self, game: Any, actor: Entity
    ) -> None:
        """同一实体重复调用返回同一对象（identity）。"""
        memory1 = get_agent_memory(game, actor)
        memory2 = get_agent_memory(game, actor)
        assert memory1 is memory2

    def test_memory_name_matches_entity(self, game: Any, actor: Entity) -> None:
        """返回的 AgentMemory.name 与实体名称一致。"""
        memory = get_agent_memory(game, actor)
        assert memory.name == actor.name

    def test_different_entities_have_independent_memories(
        self, game: Any, actor: Entity, second_actor: Entity
    ) -> None:
        """不同实体各自拥有独立的 AgentMemory 对象。"""
        memory_a = get_agent_memory(game, actor)
        memory_b = get_agent_memory(game, second_actor)
        assert memory_a is not memory_b
        assert memory_a.name != memory_b.name


# ---------------------------------------------------------------------------
# destroy_entity
# ---------------------------------------------------------------------------


class TestDestroyEntity:
    def test_destroy_removes_from_name_index(self, game: Any, actor: Entity) -> None:
        """销毁后 get_entity_by_name 返回 None。"""
        game.destroy_entity(actor)
        assert game.get_entity_by_name(actor.name) is None

    def test_destroy_cleans_up_agent_memories(self, game: Any, actor: Entity) -> None:
        """销毁时，agent_memory_store 中对应 key 被移除。"""
        get_agent_memory(game, actor)  # ensure memory exists
        assert actor.name in game.agent_memory_store
        game.destroy_entity(actor)
        assert actor.name not in game.agent_memory_store

    def test_destroy_entity_without_memory_ok(self, game: Any, actor: Entity) -> None:
        """没有记忆的实体销毁时不抛异常。"""
        assert actor.name not in game.agent_memory_store
        game.destroy_entity(actor)  # should not raise
        assert game.get_entity_by_name(actor.name) is None


# ---------------------------------------------------------------------------
# add_system_message
# ---------------------------------------------------------------------------


class TestAddSystemMessage:
    def test_basic_system_message(self, game: Any, actor: Entity) -> None:
        """成功添加 SystemMessage，内容与类型正确。"""
        add_system_message(game, actor, SystemMessage(content="system prompt"))
        messages = get_agent_memory(game, actor).messages
        assert len(messages) == 1
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == "system prompt"

    def test_system_message_not_first_raises(self, game: Any, actor: Entity) -> None:
        """memory 非空时调用 add_system_message 触发 AssertionError。"""
        add_human_message(game, actor, HumanMessage(content="already something here"))
        with pytest.raises(AssertionError):
            add_system_message(game, actor, SystemMessage(content="system prompt"))


# ---------------------------------------------------------------------------
# deliver_entities / publish_event
# ---------------------------------------------------------------------------


class TestDeliverEntities:
    def test_deliver_adds_message_to_all_entities(
        self, game: Any, actor: Entity, second_actor: Entity
    ) -> None:
        """deliver_entities 把事件消息添加给集合中的每个实体。"""
        event = _agent_event("broadcast")
        deliver_entities(game, {actor, second_actor}, event)

        assert get_agent_memory(game, actor).messages[-1].content == "broadcast"
        assert get_agent_memory(game, second_actor).messages[-1].content == "broadcast"

    def test_deliver_does_not_publish(self, game: Any, actor: Entity) -> None:
        """投递只决定谁听见；事件是否发布由发起这件事的 system 决定。"""
        before = len(game.events.events)
        deliver_entities(game, {actor}, _agent_event("event1"))
        assert len(game.events.events) == before

    def test_publish_does_not_touch_memory(self, game: Any, actor: Entity) -> None:
        """发布只记账，不写任何人的记忆。"""
        event = _agent_event("event2")
        publish_event(game, event)

        assert game.events.events[-1] == event
        assert len(get_agent_memory(game, actor).messages) == 0

    def test_deliver_stamps_event_type_without_broadcast_stage(
        self, game: Any, actor: Entity
    ) -> None:
        """私发消息只盖 agent_event 标记，不盖 broadcast_stage（不是全舞台广播）。"""
        deliver_entities(game, {actor}, _agent_event("private note"))

        message: Any = get_agent_memory(game, actor).messages[-1]
        assert message.agent_event == "none"
        assert not hasattr(message, "broadcast_stage")

    def test_deliver_empty_set_writes_nothing(self, game: Any) -> None:
        """没有听众时投递是空操作，但事件照样可以发布。"""
        event = _agent_event("empty broadcast")
        deliver_entities(game, set(), event)
        publish_event(game, event)

        assert game.events.events[-1] == event

    def test_domain_events_accumulate_in_order(self, game: Any) -> None:
        """每次 publish_event 都按调用顺序追加一条领域事件。"""
        before = list(game.events.events)
        publish_event(game, _agent_event("first"))
        publish_event(game, _agent_event("second"))

        assert game.events.events == before + [
            _agent_event("first"),
            _agent_event("second"),
        ]


# ---------------------------------------------------------------------------
# broadcast_in_region / broadcast_in_map_cell
# ---------------------------------------------------------------------------


class TestBroadcastToRegion:
    def test_broadcast_reaches_stage_and_actors(self, game: Any) -> None:
        """广播时，舞台实体及其所有 actor 都收到消息。"""
        stage = _make_stage(game, "Stage_1")
        a1 = _make_actor(game, "NPC_1", "Stage_1")
        a2 = _make_actor(game, "NPC_2", "Stage_1")

        StageBroadcastMixin(game).broadcast_in_region(stage, _agent_event("stage msg"))

        assert get_agent_memory(game, stage).messages[-1].content == "stage msg"
        assert get_agent_memory(game, a1).messages[-1].content == "stage msg"
        assert get_agent_memory(game, a2).messages[-1].content == "stage msg"

    def test_broadcast_excludes_specified_entities(self, game: Any) -> None:
        """被排除的实体不收到广播消息。"""
        stage = _make_stage(game, "Stage_2")
        a1 = _make_actor(game, "NPC_3", "Stage_2")
        a2 = _make_actor(game, "NPC_4", "Stage_2")

        StageBroadcastMixin(game).broadcast_in_region(
            stage, _agent_event("exclusive"), exclude_entities={a2}
        )

        # a1 and stage get it, a2 is excluded
        assert get_agent_memory(game, a1).messages[-1].content == "exclusive"
        assert get_agent_memory(game, stage).messages[-1].content == "exclusive"
        assert len(get_agent_memory(game, a2).messages) == 0

    def test_broadcast_with_no_actors_reaches_stage_only(self, game: Any) -> None:
        """舞台中无 actor 时，只有舞台实体收到广播。"""
        stage = _make_stage(game, "Stage_3")
        other_stage = _make_stage(game, "Stage_other")  # must exist for actor resolve
        unrelated_actor = _make_actor(game, "NPC_5", "Stage_other")

        StageBroadcastMixin(game).broadcast_in_region(
            stage, _agent_event("empty stage msg")
        )

        assert get_agent_memory(game, stage).messages[-1].content == "empty stage msg"
        assert len(get_agent_memory(game, unrelated_actor).messages) == 0

    def test_broadcast_stamps_event_type_and_stage(self, game: Any) -> None:
        """广播消息盖两个标记：agent_event（事件类型）与 broadcast_stage（广播范围）。"""
        stage = _make_stage(game, "Stage_4")
        actor = _make_actor(game, "NPC_6", "Stage_4")
        event = NoneEvent(message="喊了一声")

        StageBroadcastMixin(game).broadcast_in_region(actor, event)

        for entity in (stage, actor):
            message: Any = get_agent_memory(game, entity).messages[-1]
            assert message.agent_event == "none"
            assert message.broadcast_stage == "Stage_4"

    def test_broadcast_asserts_on_entity_without_stage(self, game: Any) -> None:
        """传入没有 StageComponent 也没有 ActorComponent 的实体触发 AssertionError。"""
        plain_entity = game.create_entity("PlainEntity")
        with pytest.raises(AssertionError, match="无法解析 Stage 实体"):
            StageBroadcastMixin(game).broadcast_in_region(
                plain_entity, _agent_event("fail")
            )

    def test_map_cell_broadcast_reaches_only_same_cell(self, game: Any) -> None:
        """大地图按格广播：同格 actor 收到，地图实体与邻格 actor 不收到。"""
        map_stage = game.create_entity("Stage_map")
        map_stage.add(StageComponent, None)
        map_stage.add(GridComponent, 5, 5)
        wanderer = _make_actor(game, "NPC_map", "Stage_map")
        wanderer.add(MapPositionComponent, 1, 1)
        same_cell = _make_actor(game, "NPC_same_cell", "Stage_map")
        same_cell.add(MapPositionComponent, 1, 1)
        other_cell = _make_actor(game, "NPC_other_cell", "Stage_map")
        other_cell.add(MapPositionComponent, 2, 2)

        StageBroadcastMixin(game).broadcast_in_map_cell(
            wanderer, _agent_event("cell wide")
        )

        assert get_agent_memory(game, wanderer).messages[-1].content == "cell wide"
        assert get_agent_memory(game, same_cell).messages[-1].content == "cell wide"
        assert get_agent_memory(game, other_cell).messages == []
        assert get_agent_memory(game, map_stage).messages == []


# ---------------------------------------------------------------------------
# exit / initialize（冒烟测试）
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_exit_with_pipeline(self, game: Any) -> None:
        """exit() 关闭唯一 pipeline 时不抛异常。"""
        exit_game(game)  # should not raise

    async def test_initialize_with_pipeline(self, game: Any) -> None:
        """initialize() 激活唯一 pipeline 时不抛异常。"""
        await initialize_game(game)
