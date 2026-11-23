"""舞台心跳 system：可插拔样板与发布链路的独立验证。

覆盖四件事：每个有角色的区域只广播一次、广播同时进入 agent 记忆、大地图
不参与、以及独立执行时事件经 ``SessionEventSink`` 落进会话历史并带上当前 job 标识。
"""

from typing import Any, List

from ai_srpg.entitas.entity import Entity
from ai_srpg.game.assembly import create_srpg_game
from ai_srpg.game.context import SRPGGame
from ai_srpg.game.events.sink import RecordingEventSink
from ai_srpg.game.memory import get_agent_memory
from ai_srpg.game.pipelines.runner import process_pipeline
from ai_srpg.game.systems.stage_pulse_system import StagePulseSystem
from ai_srpg.gameplay.session_history import SessionEventSink
from ai_srpg.models import (
    ActorComponent,
    GridComponent,
    SessionMessage,
    StageComponent,
)
from ai_srpg.session.job_context import reset_current_job, set_current_job
from ai_srpg.session.player_session import PlayerSession
from ai_srpg.session.room import Room

###############################################################################
_MAP_STAGE = "舞台.大地图"


def _make_stage(
    game: SRPGGame, name: str, *, parent_stage: str | None = _MAP_STAGE
) -> Entity:
    """创建舞台实体；默认当作地点挂在测试大地图下。"""
    if parent_stage == _MAP_STAGE and game.get_entity_by_name(_MAP_STAGE) is None:
        map_entity: Entity = game.create_entity(_MAP_STAGE)
        map_entity.add(StageComponent, None)
        map_entity.add(GridComponent, 5, 5)
    entity: Entity = game.create_entity(name)
    entity.add(StageComponent, parent_stage)
    return entity


def _make_actor(game: SRPGGame, name: str, stage_name: str) -> Entity:
    entity: Entity = game.create_entity(name)
    entity.add(ActorComponent, stage_name)
    return entity


class _FakeStore:
    def __init__(self) -> None:
        self.appended: List[SessionMessage] = []

    def latest_sequence(self, room_id: str) -> int:
        return max((m.sequence_id for m in self.appended), default=0)

    def append(self, room_id: str, message: SessionMessage) -> None:
        self.appended.append(message)

    def messages_since(
        self,
        room_id: str,
        after_sequence_id: int,
        *,
        viewer: str | None = None,
        limit: int = 500,
    ) -> List[SessionMessage]:
        return []


class _FakeJob:
    def __init__(self, job_id: int) -> None:
        self.job_id: int = job_id

    def bind_room(self, room: object) -> None:
        return None

    def on_processor_started(self, system: str) -> None:
        return None

    def on_processor_finished(self, system: str, duration_ms: float) -> None:
        return None

    def on_processor_failed(
        self, system: str, error: BaseException, duration_ms: float
    ) -> None:
        return None


###############################################################################
async def test_broadcasts_once_per_non_empty_stage() -> None:
    game = create_srpg_game(name="Game1", events=RecordingEventSink())
    _make_stage(game, "舞台.营地")
    _make_actor(game, "角色.乙", "舞台.营地")
    _make_actor(game, "角色.甲", "舞台.营地")
    _make_stage(game, "舞台.空")

    await StagePulseSystem(game).execute()

    events: List[Any] = game.events.events  # type: ignore[attr-defined]
    assert len(events) == 1
    assert events[0].message == "舞台.营地：当前在场 角色.乙、角色.甲。"


async def test_broadcast_reaches_stage_and_actors_memory() -> None:
    game = create_srpg_game(name="Game1", events=RecordingEventSink())
    stage = _make_stage(game, "舞台.营地")
    actor = _make_actor(game, "角色.无名", "舞台.营地")

    await StagePulseSystem(game).execute()

    assert get_agent_memory(game, stage).messages[-1].content.startswith("舞台.营地：")
    assert get_agent_memory(game, actor).messages[-1].content.startswith("舞台.营地：")


async def test_map_stage_is_never_broadcast() -> None:
    """大地图没有「在场者」，即使站着角色也不发区域广播。"""
    game = create_srpg_game(name="Game1", events=RecordingEventSink())
    map_stage = _make_stage(game, "舞台.大地图", parent_stage=None)
    map_stage.add(GridComponent, 5, 5)
    _make_actor(game, "角色.游荡者", "舞台.大地图")

    await StagePulseSystem(game).execute()

    assert game.events.events == []  # type: ignore[attr-defined]
    assert get_agent_memory(game, map_stage).messages == []


###############################################################################
async def test_empty_game_publishes_nothing() -> None:
    game = create_srpg_game(name="Game1", events=RecordingEventSink())

    await StagePulseSystem(game).execute()

    assert game.events.events == []  # type: ignore[attr-defined]


###############################################################################
async def test_stage_pulse_writes_session_history_with_job_id() -> None:
    """闭环：舞台心跳 → 事件出口 → 会话历史，消息带当前 job 与游戏上下文。"""
    store = _FakeStore()
    room = Room(room_id="alice", owner="alice")
    session = PlayerSession(user_name="alice", room_id="alice")
    room.attach_session(session)
    game = create_srpg_game(
        name="Game1", events=SessionEventSink(room, session, store=store)
    )
    _make_stage(game, "舞台.营地")
    _make_actor(game, "角色.无名", "舞台.营地")
    session.set_context(actor="角色.无名", game="Game1")

    token = set_current_job(_FakeJob(job_id=7))
    try:
        await StagePulseSystem(game).execute()
    finally:
        reset_current_job(token)

    assert len(store.appended) == 1
    message = store.appended[0]
    assert message.job_id == 7
    assert message.game_name == "Game1"
    assert message.actor == "角色.无名"
    assert message.sequence_id == 1
    assert message.agent_event is not None
    assert message.agent_event.message == "舞台.营地：当前在场 角色.无名。"


async def test_stage_pulse_is_not_in_the_default_pipeline() -> None:
    """舞台心跳是可插拔样例：默认管线不挂它，但它的独立测试仍然保留。"""
    game = create_srpg_game(name="Game1")

    result = await process_pipeline(game.pipeline, None)

    assert "StagePulseSystem" not in result.ran
