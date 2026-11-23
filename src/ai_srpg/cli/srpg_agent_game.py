"""SRPG AI 操作工具 —— 快照驱动的离线游戏推进 CLI。

每条子命令只完成一个动作：加载快照 → 执行 → 按需保存新快照，命令之间
不保持进程内状态。状态与历史由 PostgreSQL 的 game_snapshots 承载。

命令一览：
  list             列出该玩家的所有对局
  new              从蓝图创建新游戏并写入基线快照
  bind             接管一个已有角色并写入快照
  snapshots        列出快照历史
  stages           列出舞台-角色映射
  actors           列出角色名册（所在舞台、控制者、当前外观）
  memories         把带记忆的实体导出成 markdown（可只导指定实体）
  plan             让一个或多个角色做本轮计划
  act              接管一个角色：直接下一条命令，跑一次 pass
  compact-context  手动压缩指定实体的 LLM 记忆并保存快照
  advance          执行一次 pass 并保存结果快照
"""

import asyncio
import datetime
import itertools
import json
import os
import sys
from pathlib import Path
from typing import Any, Coroutine, Final

import click
from loguru import logger

from ai_srpg.entitas.components import Component
from ai_srpg.gameplay.offline import GameAlreadyExistsError, OfflinePassFailed
from ai_srpg.llm.call_context import llm_call_trace
from ai_srpg.llm.call_records import find_llm_call, iter_llm_call_records
from ai_srpg.models import (
    EnterSiteAction,
    ExitSiteAction,
    MoveWithinSiteAction,
    SpeakAction,
    TravelAction,
    WaitAction,
)
from ai_srpg.paths import LOGS_DIR
from ai_srpg.srpg_game_agent.compact import compact_context_game
from ai_srpg.srpg_game_agent.core import (
    actors_game,
    advance_game,
    bind_actor_game,
    command_actor_game,
    create_and_initialize_game,
    list_games_game,
    memories_game,
    plan_game,
    snapshots_game,
    stages_game,
)

LOG_LEVEL: Final[str] = "DEBUG"


###############################################################################
def _setup_logger() -> Path:
    """初始化控制台与文件日志，返回本次运行日志文件路径。"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = LOGS_DIR / f"run_agent_game_{timestamp}.log"
    logger.remove()
    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    logger.add(log_file, level=LOG_LEVEL)
    logger.info(f"日志配置: 级别={LOG_LEVEL}, 文件路径={log_file}")
    return log_file


###############################################################################
def _run_game(
    coro: Coroutine[Any, Any, Any],
    *,
    command: str,
    user: str = "",
    game: str = "",
) -> Any:
    """在 CLI 作用域的 trace 中执行游戏动作。"""
    with llm_call_trace(
        scope="cli",
        scope_id=str(os.getpid()),
        command=command,
        user=user,
        game=game,
    ):
        return asyncio.run(coro)


###############################################################################
@click.group()
def main() -> None:
    """AI 操作工具：快照驱动的离线游戏推进。"""


###############################################################################
@main.command("llm-calls")
@click.option("--limit", default=20, show_default=True, help="最多显示多少条")
@click.option("--label", default=None, help="按 label 精确过滤")
@click.option("--user", default=None, help="按用户过滤")
@click.option("--game", default=None, help="按游戏过滤")
@click.option("--command", default=None, help="按命令/动作过滤")
@click.option("--loop-id", default=None, help="按 agent loop 过滤")
@click.option("--round", "round_num", type=int, default=None, help="按 loop 轮次过滤")
@click.option("--scope", default=None, help="按 cli / room 过滤")
@click.option(
    "--since",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]),
    default=None,
    help="起始时间（含）",
)
@click.option(
    "--until",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]),
    default=None,
    help="结束时间（含）",
)
@click.option("--json", "as_json", is_flag=True, help="逐行输出完整 JSON")
def llm_calls(
    limit: int,
    label: str | None,
    user: str | None,
    game: str | None,
    command: str | None,
    loop_id: str | None,
    round_num: int | None,
    scope: str | None,
    since: datetime.datetime | None,
    until: datetime.datetime | None,
    as_json: bool,
) -> None:
    """列出最近的 LLM 调用记录（查问题 / 调提示词）。"""
    records = list(
        itertools.islice(
            iter_llm_call_records(
                label=label,
                user=user,
                game=game,
                command=command,
                scope=scope,
                loop_id=loop_id,
                round_num=round_num,
                since=since,
                until=until,
            ),
            limit,
        )
    )
    if not records:
        click.echo("（没有 llm call 记录）")
        return
    if as_json:
        for record in records:
            click.echo(record.model_dump_json())
        return
    for record in records:
        status = "ERR" if record.response.get("error") else "OK"
        tokens = (record.usage or {}).get("total_tokens", "-")
        fields = [
            f"{record.created_at.astimezone():%Y-%m-%d %H:%M:%S}",
            record.request_id[:8],
            f"{status:<3}",
            f"{record.elapsed_ms:>6}ms",
            f"{str(tokens):>6}tok",
            f"{record.trace.scope or '-':<4}",
            record.label,
        ]
        click.echo("  ".join(fields))


###############################################################################
@main.command("llm-call")
@click.argument("request_id")
@click.option("--json", "as_json", is_flag=True, help="输出完整 JSON")
def llm_call(request_id: str, as_json: bool) -> None:
    """查看一条 LLM 调用记录（支持完整 id 或唯一前缀）。"""
    record = find_llm_call(request_id)
    if record is None:
        raise click.ClickException(f"找不到记录: {request_id}")

    if as_json:
        click.echo(record.model_dump_json(indent=2))
        return

    click.echo(f"request_id: {record.request_id}")
    click.echo(f"time:       {record.created_at.astimezone():%Y-%m-%d %H:%M:%S}")
    if record.started_at is not None:
        click.echo(f"started:    {record.started_at.astimezone():%Y-%m-%d %H:%M:%S}")
    click.echo(f"label:      {record.label}")
    click.echo(f"model:      {record.model or '(provider default)'}")
    click.echo(f"elapsed:    {record.elapsed_ms}ms")
    if record.context_usage_ratio is not None:
        click.echo(f"context:    {record.context_usage_ratio:.2%}")
    trace = record.trace.model_dump(exclude_defaults=True)
    if trace:
        click.echo(f"trace:      {json.dumps(trace, ensure_ascii=False)}")
    if record.usage:
        click.echo(f"usage:      {json.dumps(record.usage, ensure_ascii=False)}")

    error = record.response.get("error")
    if error:
        click.echo(f"error:      {json.dumps(error, ensure_ascii=False)}")

    last_index = len(record.messages) - 1
    for index, message in enumerate(record.messages):
        header = message.get("type", "?")
        if (
            index == last_index
            and (message.get("content") or "") == record.input_message
        ):
            header = "prompt（本轮输入）"
        click.echo(f"\n===== {header} =====")
        click.echo(message.get("content") or "")
        tool_calls = (message.get("additional_kwargs") or {}).get("tool_calls")
        if tool_calls:
            click.echo(json.dumps(tool_calls, ensure_ascii=False, indent=2))

    ai_message = record.response.get("ai_message") or {}
    click.echo("\n===== ai =====")
    click.echo(ai_message.get("content") or "")
    tool_calls = ai_message.get("additional_kwargs", {}).get("tool_calls")
    if tool_calls:
        click.echo(json.dumps(tool_calls, ensure_ascii=False, indent=2))
    reasoning = ai_message.get("additional_kwargs", {}).get("reasoning_content")
    if reasoning:
        click.echo("\n===== reasoning =====")
        click.echo(reasoning)


###############################################################################
@main.command("list")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--json", "as_json", is_flag=True, help="逐行输出完整 JSON")
def list_games(user: str, as_json: bool) -> None:
    """列出该玩家的所有对局。"""
    summaries = list_games_game(user)
    if not summaries:
        click.echo("（没有对局）")
        return
    if as_json:
        for summary in summaries:
            click.echo(summary.model_dump_json())
        return
    for summary in summaries:
        line = "  ".join(
            [
                f"{summary.updated_at.astimezone():%Y-%m-%d %H:%M:%S}",
                f"{summary.game_name:<12}",
                f"snapshots={summary.snapshot_count:<4}",
                f"latest={summary.latest_snapshot_id:<6}",
                f"entities={summary.entity_count}",
            ]
        )
        click.echo(line)


###############################################################################
@main.command("new")
@click.option("--user", required=True, help="玩家用户名")
@click.option(
    "--game", required=True, help="游戏名称（对应 BLUEPRINTS_DIR 下的文件名）"
)
@click.option(
    "--reset",
    is_flag=True,
    help="已有快照时仍从蓝图重建，并追加新的基线快照（旧历史保留）",
)
def new_game(user: str, game: str, reset: bool) -> None:
    """从蓝图创建新游戏并写入基线快照（不绑定玩家）。"""
    _setup_logger()
    try:
        outcome = _run_game(
            create_and_initialize_game(user, game, reset=reset),
            command="new",
            user=user,
            game=game,
        )
    except GameAlreadyExistsError as exc:
        raise click.ClickException(str(exc)) from exc
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"user:      {user}")
    click.echo(f"game:      {game}")
    click.echo(f"entities:  {outcome.game.entity_count}")
    click.echo(f"snapshot:  {outcome.snapshot_id}")


###############################################################################
@main.command("bind")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--game", required=True, help="游戏名称")
@click.option("--actor", required=True, help="要接管的角色名")
@click.option(
    "--snapshot-id", type=int, default=None, help="基于哪个快照接管；缺省用最新"
)
def bind_actor_cmd(user: str, game: str, actor: str, snapshot_id: int | None) -> None:
    """让该玩家接管一个已有角色，并写入新快照。"""
    _setup_logger()
    try:
        outcome = _run_game(
            bind_actor_game(user, game, actor, snapshot_id),
            command="bind",
            user=user,
            game=game,
        )
    except LookupError as exc:
        raise click.ClickException(str(exc)) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"user:      {outcome.user_name}")
    click.echo(f"game:      {game}")
    click.echo(f"actor:     {outcome.actor_name}")
    click.echo(f"snapshot:  {outcome.snapshot_id}")


###############################################################################
@main.command("snapshots")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--game", required=True, help="游戏名称")
@click.option("--limit", default=20, show_default=True, help="最多显示多少条")
@click.option("--json", "as_json", is_flag=True, help="逐行输出完整 JSON")
def snapshots(user: str, game: str, limit: int, as_json: bool) -> None:
    """按时间倒序列出快照历史。"""
    _setup_logger()
    infos = _run_game(
        snapshots_game(user, game, limit=limit),
        command="snapshots",
        user=user,
        game=game,
    )
    if not infos:
        click.echo("（没有快照）")
        return
    if as_json:
        for info in infos:
            click.echo(info.model_dump_json())
        return
    for info in infos:
        line = "  ".join(
            [
                f"{info.created_at.astimezone():%Y-%m-%d %H:%M:%S}",
                f"id={info.id:<6}",
                f"entities={info.entity_count:<4}",
                f"memories={info.memory_count:<4}",
                f"v{info.format_version}",
            ]
        )
        click.echo(line)


###############################################################################
@main.command("stages")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--game", required=True, help="游戏名称")
@click.option("--snapshot-id", type=int, default=None, help="指定快照 id；缺省用最新")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON")
def stages(user: str, game: str, snapshot_id: int | None, as_json: bool) -> None:
    """列出舞台-角色映射。"""
    _setup_logger()
    try:
        mapping = _run_game(
            stages_game(user, game, snapshot_id),
            command="stages",
            user=user,
            game=game,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except LookupError as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        click.echo(json.dumps(mapping, ensure_ascii=False, indent=2))
        return
    if not mapping:
        click.echo("（没有舞台）")
        return
    for stage_name, actor_names in mapping.items():
        actors = ", ".join(actor_names) if actor_names else "（无角色）"
        click.echo(f"{stage_name}: {actors}")


###############################################################################
@main.command("actors")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--game", required=True, help="游戏名称")
@click.option("--snapshot-id", type=int, default=None, help="指定快照 id；缺省用最新")
@click.option("--json", "as_json", is_flag=True, help="逐行输出完整 JSON")
def actors(user: str, game: str, snapshot_id: int | None, as_json: bool) -> None:
    """列出角色名册：所在舞台、控制者与当前外观。"""
    _setup_logger()
    try:
        summaries = _run_game(
            actors_game(user, game, snapshot_id),
            command="actors",
            user=user,
            game=game,
        )
    except LookupError as exc:
        raise click.ClickException(str(exc)) from exc

    if not summaries:
        click.echo("（没有角色）")
        return
    if as_json:
        for summary in summaries:
            click.echo(summary.model_dump_json())
        return
    for summary in summaries:
        line = "  ".join(
            [
                f"{summary.name:<12}",
                f"{summary.stage:<10}",
                f"player={summary.player or '-':<10}",
                summary.appearance or "（外观未定）",
            ]
        )
        click.echo(line)


###############################################################################
@main.command("memories")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--game", required=True, help="游戏名称")
@click.option(
    "--entity",
    "entities",
    multiple=True,
    help="只导这个实体的记忆，可重复；缺省导出全部",
)
@click.option(
    "--dir",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="输出目录（一实体一文件）；缺省写在 logs/memories/ 下",
)
@click.option("--snapshot-id", type=int, default=None, help="指定快照 id；缺省用最新")
def memories(
    user: str,
    game: str,
    entities: tuple[str, ...],
    out_dir: Path | None,
    snapshot_id: int | None,
) -> None:
    """把记忆导出成 markdown，一个实体一个文件。"""
    _setup_logger()
    try:
        outcome = _run_game(
            memories_game(
                user, game, list(entities), snapshot_id=snapshot_id, directory=out_dir
            ),
            command="memories",
            user=user,
            game=game,
        )
    except LookupError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"entities:  {outcome.entity_count}")
    click.echo(f"messages:  {outcome.message_count}")
    click.echo(f"dir:       {outcome.directory}")
    for path in outcome.files:
        click.echo(f"  {path.name}")


###############################################################################
@main.command("plan")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--game", required=True, help="游戏名称")
@click.option(
    "--actor",
    "actors",
    multiple=True,
    required=True,
    help="要计划的角色名，可重复",
)
@click.option("--snapshot-id", type=int, default=None, help="指定快照 id；缺省用最新")
def plan(
    user: str, game: str, actors: tuple[str, ...], snapshot_id: int | None
) -> None:
    """让一个或多个角色做本轮计划，并保存结果快照。"""
    _setup_logger()
    try:
        outcome = _run_game(
            plan_game(user, game, list(actors), snapshot_id),
            command="plan",
            user=user,
            game=game,
        )
    except LookupError as exc:
        raise click.ClickException(str(exc)) from exc
    except OfflinePassFailed as exc:
        raise click.ClickException(f"pass 失败，已回滚到本次执行前快照: {exc}") from exc

    for actor_name in outcome.actors:
        click.echo(f"planned:   {actor_name}")
    click.echo(f"snapshot:  {outcome.snapshot_id}")


###############################################################################
def _parse_cell(raw: str) -> tuple[int, int]:
    """``3,2`` → (3, 2)；写错就按用法错误报，而不是猜。"""
    parts = raw.split(",")
    if len(parts) != 2:
        raise click.BadParameter("坐标要写成 x,y，例如 3,2")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise click.BadParameter("坐标必须是整数，例如 3,2") from exc


###############################################################################
@main.command("act")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--game", required=True, help="游戏名称")
@click.option("--actor", required=True, help="要接管的角色名")
@click.option("--speak", "speak", default=None, help="说话：要说的内容")
@click.option("--travel", "travel", default=None, help="大地图移动：目标格 x,y")
@click.option("--enter", "enter_site", default=None, help="进入地点：地点名")
@click.option("--exit", "exit_site", is_flag=True, help="离开地点：回到地点所在的格")
@click.option(
    "--move-within", "move_within", default=None, help="区域内移动：目标区域名"
)
@click.option("--wait", "wait_action", is_flag=True, help="原地不动")
@click.option(
    "--force",
    is_flag=True,
    help="跳过绑定校验（开发期直接驱动没有绑定过的角色）",
)
@click.option("--snapshot-id", type=int, default=None, help="指定快照 id；缺省用最新")
def act(
    user: str,
    game: str,
    actor: str,
    speak: str | None,
    travel: str | None,
    enter_site: str | None,
    exit_site: bool,
    move_within: str | None,
    wait_action: bool,
    force: bool,
    snapshot_id: int | None,
) -> None:
    """接管一个角色：直接下一条命令，跑一次 pass。"""
    action = _build_action(
        speak=speak,
        travel=travel,
        enter_site=enter_site,
        exit_site=exit_site,
        move_within=move_within,
        wait_action=wait_action,
    )
    _setup_logger()
    try:
        outcome = _run_game(
            command_actor_game(
                user, game, actor, action, force=force, snapshot_id=snapshot_id
            ),
            command="act",
            user=user,
            game=game,
        )
    except LookupError as exc:
        raise click.ClickException(str(exc)) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except OfflinePassFailed as exc:
        raise click.ClickException(f"pass 失败，已回滚到本次执行前快照: {exc}") from exc

    click.echo(f"actor:     {outcome.actor_name}")
    click.echo(f"action:    {outcome.command}")
    click.echo(f"where:     {outcome.location}")
    click.echo(f"snapshot:  {outcome.snapshot_id}")


###############################################################################
def _build_action(
    *,
    speak: str | None,
    travel: str | None,
    enter_site: str | None,
    exit_site: bool,
    move_within: str | None,
    wait_action: bool,
) -> "Component":
    """六个动词里只能选一个；选不出来就按用法错误报。"""
    chosen = [
        ("speak", speak is not None),
        ("travel", travel is not None),
        ("enter", enter_site is not None),
        ("exit", exit_site),
        ("move-within", move_within is not None),
        ("wait", wait_action),
    ]
    picked = [name for name, used in chosen if used]
    if len(picked) != 1:
        raise click.UsageError(
            " ".join(
                [
                    f"一次只能下一个动作，收到 {picked or '一个都没有'}：",
                    "用 --speak / --travel / --enter / --exit / --move-within / --wait 之一",
                ]
            )
        )
    if speak is not None:
        return SpeakAction(content=speak)
    if travel is not None:
        x, y = _parse_cell(travel)
        return TravelAction(x=x, y=y)
    if enter_site is not None:
        return EnterSiteAction(site=enter_site)
    if exit_site:
        return ExitSiteAction()
    if move_within is not None:
        return MoveWithinSiteAction(destination=move_within)
    return WaitAction()


###############################################################################
@main.command("compact-context")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--game", required=True, help="游戏名称")
@click.option("--snapshot-id", type=int, default=None, help="指定快照 id；缺省用最新")
@click.option("--target", required=True, help="要压缩的目标实体名")
@click.option("--summary", default=None, help="压缩后的摘要文本")
def compact_context(
    user: str,
    game: str,
    snapshot_id: int | None,
    target: str,
    summary: str | None,
) -> None:
    """手动压缩指定实体的 LLM 记忆并保存快照。"""
    _setup_logger()
    kwargs = {} if summary is None else {"summary": summary}
    try:
        outcome = _run_game(
            compact_context_game(user, game, target, snapshot_id, **kwargs),
            command="compact-context",
            user=user,
            game=game,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except LookupError as exc:
        raise click.ClickException(str(exc)) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except OfflinePassFailed as exc:
        raise click.ClickException(f"pass 失败，已回滚到本次执行前快照: {exc}") from exc

    click.echo(f"target:    {outcome.entity_name}")
    click.echo(f"messages:  {outcome.before_messages} -> {outcome.after_messages}")
    click.echo(f"context:   {outcome.before_ratio:.2%} -> {outcome.after_ratio:.2%}")
    click.echo(f"snapshot:  {outcome.snapshot_id}")


###############################################################################
@main.command("advance")
@click.option("--user", required=True, help="玩家用户名")
@click.option("--game", required=True, help="游戏名称")
@click.option("--snapshot-id", type=int, default=None, help="指定快照 id；缺省用最新")
def advance(user: str, game: str, snapshot_id: int | None) -> None:
    """执行一次 pass，并在成功后保存结果快照。"""
    _setup_logger()
    try:
        outcome = _run_game(
            advance_game(user, game, snapshot_id),
            command="advance",
            user=user,
            game=game,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    except LookupError as exc:
        raise click.ClickException(str(exc)) from exc
    except OfflinePassFailed as exc:
        raise click.ClickException(f"pass 失败，已回滚到本次执行前快照: {exc}") from exc

    result = outcome.result
    click.echo(f"completed:  {result.completed}")
    click.echo(f"ran:        {', '.join(result.ran) or '-'}")
    click.echo(f"skipped:    {', '.join(result.skipped) or '-'}")
    if result.aborted_by is not None:
        click.echo(f"aborted_by: {result.aborted_by}")
    click.echo(f"snapshot:   {outcome.snapshot_id}")
