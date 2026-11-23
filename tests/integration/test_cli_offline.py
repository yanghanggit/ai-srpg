"""CLI 端到端：list → new → bind → stages → actors → act → plan → advance → compact → snapshots。"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from click.testing import CliRunner

from ai_srpg.cli.srpg_agent_game import main
from ai_srpg.models import ActorComponent, Blueprint, walk_stages
from ai_srpg.pgsql import pgsql_ensure_database_tables
from ai_srpg.pgsql.client import SessionLocal
from ai_srpg.pgsql.game_snapshot import GameSnapshotDB
from seeds import create_blueprint


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    pgsql_ensure_database_tables()


@pytest.fixture
def blueprint() -> Blueprint:
    """默认剧本：断言里的实体名与舞台名都从这里取，不手抄内容。"""
    return create_blueprint("dark_fantasy/mercenary_camp", "Game1")


@pytest.fixture
def blueprint_dir(
    blueprint: Blueprint, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    (tmp_path / "Game1.json").write_text(
        blueprint.model_dump_json(indent=2), encoding="utf-8"
    )
    monkeypatch.setattr("ai_srpg.game.offline.BLUEPRINTS_DIR", tmp_path)
    return tmp_path


def _expected_stages(blueprint: Blueprint) -> Dict[str, List[str]]:
    """由蓝图推出「舞台 → 在场角色」：舞台按树先序，角色按名字排序。"""
    expected: Dict[str, List[str]] = {
        stage.name: [] for stage, _ in walk_stages(blueprint.stage_tree)
    }
    for candidate in blueprint.actors:
        current_stage = candidate.components[ActorComponent.__name__]["current_stage"]
        expected[current_stage].append(candidate.name)
    return {name: sorted(actors) for name, actors in expected.items()}


def _json_lines(output: str) -> List[Any]:
    """逐行 JSON 输出同样混着日志行，只取以 ``{`` 开头的行。"""
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


def _json_output(output: str) -> Any:
    """CLI 输出里混着日志行，取第一段完整 JSON。"""
    payload, _ = json.JSONDecoder().raw_decode(output[output.index("{") :])
    return payload


@pytest.fixture
def user_name() -> Iterator[str]:
    name = f"test-cli-{uuid.uuid4()}"
    yield name
    db = SessionLocal()
    try:
        db.query(GameSnapshotDB).filter(GameSnapshotDB.room_id == name).delete()
        db.commit()
    finally:
        db.close()


def test_cli_offline_flow(
    blueprint_dir: Path, blueprint: Blueprint, user_name: str, tmp_path: Path
) -> None:
    runner = CliRunner()
    actor = blueprint.actors[0].name
    other_actor = blueprint.actors[1].name
    missing_actor = f"角色.{uuid.uuid4().hex}"

    created = runner.invoke(main, ["new", "--user", user_name, "--game", "Game1"])
    assert created.exit_code == 0, created.output
    assert "entities:" in created.output
    assert "snapshot:" in created.output

    duplicate = runner.invoke(main, ["new", "--user", user_name, "--game", "Game1"])
    assert duplicate.exit_code == 1
    assert "已有 1 个快照" in duplicate.output

    listed = runner.invoke(main, ["list", "--user", user_name])
    assert listed.exit_code == 0, listed.output
    assert "Game1" in listed.output
    assert "snapshots=1" in listed.output

    unknown = runner.invoke(
        main,
        ["bind", "--user", user_name, "--game", "NoSuchGame", "--actor", actor],
    )
    assert unknown.exit_code == 1
    assert "先用 new 建局" in unknown.output

    bound = runner.invoke(
        main, ["bind", "--user", user_name, "--game", "Game1", "--actor", actor]
    )
    assert bound.exit_code == 0, bound.output
    assert f"actor:     {actor}" in bound.output
    assert "snapshot:" in bound.output

    rebound_to_same = runner.invoke(
        main, ["bind", "--user", user_name, "--game", "Game1", "--actor", actor]
    )
    assert rebound_to_same.exit_code == 0, rebound_to_same.output

    unknown_actor = runner.invoke(
        main, ["bind", "--user", user_name, "--game", "Game1", "--actor", missing_actor]
    )
    assert unknown_actor.exit_code == 1
    assert "找不到角色实体" in unknown_actor.output

    stages = runner.invoke(
        main, ["stages", "--user", user_name, "--game", "Game1", "--json"]
    )
    assert stages.exit_code == 0, stages.output
    assert _json_output(stages.output) == _expected_stages(blueprint)

    actors = runner.invoke(
        main, ["actors", "--user", user_name, "--game", "Game1", "--json"]
    )
    assert actors.exit_code == 0, actors.output
    roster = _json_lines(actors.output)
    assert {summary["name"] for summary in roster} == {
        candidate.name for candidate in blueprint.actors
    }
    assert all(summary["stage"] for summary in roster)

    acted = runner.invoke(
        main,
        [
            "act",
            "--user",
            user_name,
            "--game",
            "Game1",
            "--actor",
            actor,
            "--wait",
        ],
    )
    assert acted.exit_code == 0, acted.output
    assert f"actor:     {actor}" in acted.output
    assert "action:    Wait" in acted.output
    assert f"where:     " in acted.output
    assert "snapshot:" in acted.output

    unbound = runner.invoke(
        main,
        [
            "act",
            "--user",
            user_name,
            "--game",
            "Game1",
            "--actor",
            other_actor,
            "--wait",
        ],
    )
    assert unbound.exit_code == 1
    assert "没有控制" in unbound.output

    forced = runner.invoke(
        main,
        [
            "act",
            "--user",
            user_name,
            "--game",
            "Game1",
            "--actor",
            other_actor,
            "--wait",
            "--force",
        ],
    )
    assert forced.exit_code == 0, forced.output

    blocked = runner.invoke(
        main,
        [
            "act",
            "--user",
            user_name,
            "--game",
            "Game1",
            "--actor",
            actor,
            "--speak",
            "喂",
        ],
    )
    assert blocked.exit_code == 0, blocked.output

    bad_verb = runner.invoke(
        main,
        [
            "act",
            "--user",
            user_name,
            "--game",
            "Game1",
            "--actor",
            actor,
            "--wait",
            "--exit",
        ],
    )
    assert bad_verb.exit_code == 2

    planned = runner.invoke(
        main,
        ["plan", "--user", user_name, "--game", "Game1", "--actor", actor],
    )
    assert planned.exit_code == 0, planned.output
    assert f"planned:   {actor}" in planned.output
    assert "snapshot:" in planned.output

    unknown_plan = runner.invoke(
        main,
        ["plan", "--user", user_name, "--game", "Game1", "--actor", missing_actor],
    )
    assert unknown_plan.exit_code == 1
    assert "找不到角色实体" in unknown_plan.output

    advanced = runner.invoke(main, ["advance", "--user", user_name, "--game", "Game1"])
    assert advanced.exit_code == 0, advanced.output
    assert "completed:" in advanced.output
    assert "snapshot:" in advanced.output

    compacted = runner.invoke(
        main,
        [
            "compact-context",
            "--user",
            user_name,
            "--game",
            "Game1",
            "--target",
            actor,
        ],
    )
    assert compacted.exit_code == 0, compacted.output
    assert "messages:" in compacted.output
    assert "snapshot:" in compacted.output

    dumped = runner.invoke(
        main,
        [
            "memories",
            "--user",
            user_name,
            "--game",
            "Game1",
            "--entity",
            actor,
            "--dir",
            str(tmp_path / "memories"),
        ],
    )
    assert dumped.exit_code == 0, dumped.output
    assert "entities:  1" in dumped.output
    memory_file = Path(tmp_path / "memories" / f"{actor}.md")
    assert memory_file.read_text(encoding="utf-8").startswith(f"# {actor}")

    unknown_entity = runner.invoke(
        main,
        ["memories", "--user", user_name, "--game", "Game1", "--entity", missing_actor],
    )
    assert unknown_entity.exit_code == 1
    assert "没有记忆" in unknown_entity.output

    history = runner.invoke(main, ["snapshots", "--user", user_name, "--game", "Game1"])
    assert history.exit_code == 0, history.output
    # 每次 pass 落两条快照（执行前回滚点 + 结果）。compact 也走 pass，
    # 因此与 act / plan / advance 一样算两条。
    assert history.output.count("id=") == 15

    reset = runner.invoke(
        main,
        ["new", "--user", user_name, "--game", "Game1", "--reset"],
    )
    assert reset.exit_code == 0, reset.output
    assert "snapshot:" in reset.output
