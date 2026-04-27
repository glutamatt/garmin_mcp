"""Garmin Connect CLI — bash-style interface to Garmin data.

Architecture: CLI layer wraps the existing api/* pure functions.
Same data, less tokens, filesystem as clipboard.

Usage:
    garmin [--format json|table] [--fields f1,f2,...] [--output path] <group> <command> [args]
    garmin help
    garmin <group> --help
"""

import json
import os
from datetime import date as _date, timedelta as _timedelta

import click


def _today():
    return _date.today().isoformat()

from garmin_mcp.client_factory import create_client_from_tokens
from garmin_mcp.cli.output import (
    filter_fields,
    find_missing_fields,
    format_output,
    write_csv_file,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _client(ctx):
    """Get Garmin client from click context (lazy creation)."""
    c = ctx.obj.get("client")
    if not c:
        token = ctx.obj.get("_token")
        if not token:
            raise click.ClickException(
                "No auth token. Pass --token or set GARMIN_TOKEN."
            )
        c = create_client_from_tokens(token, ctx.obj.get("_display_name"))
        ctx.obj["client"] = c
    return c


SANDBOX_DIR = "/tmp/garmin"


def _session_sandbox(ctx) -> str:
    """Per-session sandbox from tmp_dir (set by frontend). Falls back to SANDBOX_DIR."""
    tmp_dir = (ctx.obj or {}).get("_tmp_dir")
    if tmp_dir and tmp_dir.startswith("/tmp/"):
        return tmp_dir
    return SANDBOX_DIR


def _sanitize_path(raw_path: str, sandbox: str = SANDBOX_DIR) -> str:
    """Sandbox output path to given sandbox dir. Reject traversals."""
    # Resolve to absolute, collapse ..'s
    resolved = os.path.realpath(raw_path)
    # If not already under sandbox, treat as relative filename inside it
    if not resolved.startswith(sandbox):
        basename = os.path.basename(resolved)
        if not basename:
            raise click.ClickException(f"Invalid path: {raw_path}")
        resolved = os.path.join(sandbox, basename)
    return resolved


def _read_input_file(ctx, path: str) -> dict:
    """Read and parse a JSON file from the session sandbox."""
    sandbox = _session_sandbox(ctx)
    safe_path = _sanitize_path(path, sandbox)
    if not os.path.isfile(safe_path):
        raise click.ClickException(f"File not found: {path}")
    with open(safe_path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise click.ClickException(f"Invalid JSON in {path}: {e}")


def _describe_shape(data) -> str:
    """Return a short structural preview of data for --output messages.

    Examples: '{"count": 5, "activities": [...5 items]}', '[...3 items]'
    """
    if isinstance(data, list):
        return f"[...{len(data)} items]"
    if isinstance(data, dict):
        parts = []
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                parts.append(f'"{k}": [...{len(v)} items]')
            elif isinstance(v, (int, float, bool)):
                parts.append(f'"{k}": {v}')
            elif isinstance(v, str) and len(v) <= 30:
                parts.append(f'"{k}": "{v}"')
            else:
                parts.append(f'"{k}": ...')
        return "{" + ", ".join(parts) + "}"
    return str(type(data).__name__)


def _out(ctx, data):
    """Apply field filtering, format, and output."""
    fields = ctx.obj.get("fields")
    fmt = ctx.obj.get("format", "json")
    output_path = ctx.obj.get("output")

    if fields:
        missing = find_missing_fields(data, fields)
        if missing:
            click.echo(f"Warning: unknown fields ignored: {', '.join(missing)}", err=True)
        data = filter_fields(data, fields)

    text = format_output(data, fmt)

    if output_path:
        sandbox = _session_sandbox(ctx)
        safe_path = _sanitize_path(output_path, sandbox)
        os.makedirs(os.path.dirname(safe_path) or sandbox, exist_ok=True)
        with open(safe_path, "w") as f:
            f.write(text)
        click.echo(f"{_describe_shape(data)} written to {os.path.basename(safe_path)}")
    else:
        click.echo(text)


def _run(ctx, fn, *, dry_run_preview: dict | None = None):
    """Execute fn(), handle errors, output result.

    If --dry-run is active AND dry_run_preview is provided, skip execution
    and output the preview instead. Read-only commands pass no preview.
    """
    if ctx.obj.get("dry_run") and dry_run_preview is not None:
        _out(ctx, {"dry_run": True, **dry_run_preview})
        return
    try:
        data = fn()
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))
    _out(ctx, data)


# ── Main group ───────────────────────────────────────────────────────────────


@click.group()
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "table"]),
    default="json",
    help="Output format",
)
@click.option("--fields", default=None, help="Comma-separated fields to include")
@click.option("--output", "output_path", default=None, help="Write to file (auto-sandboxed to session dir)")
@click.option("--dry-run", is_flag=True, default=False, help="Validate without calling API (mutations only)")
@click.option(
    "--token",
    envvar="GARMIN_TOKEN",
    default=None,
    hidden=True,
    help="Base64 garth token",
)
@click.option(
    "--display-name",
    envvar="GARMIN_DISPLAY_NAME",
    default=None,
    hidden=True,
)
@click.option(
    "--tmp-dir",
    default=None,
    hidden=True,
    help="Session-scoped tmp directory for file I/O isolation",
)
@click.pass_context
def garmin(ctx, fmt, fields, output_path, dry_run, token, display_name, tmp_dir):
    """Garmin Connect CLI — query athlete data.

    \b
    Global flags (before command):
      --fields f1,f2   Only include these fields (reduces output)
      --format table   Human-readable table instead of JSON
      --output PATH    Write to file (auto-sandboxed)
      --dry-run        Validate mutation without calling API

    \b
    Date format: YYYY-MM-DD everywhere.
    """
    ctx.ensure_object(dict)
    ctx.obj.setdefault("format", fmt)
    ctx.obj.setdefault("output", output_path)
    ctx.obj.setdefault("dry_run", dry_run)
    if fields and "fields" not in ctx.obj:
        ctx.obj["fields"] = [f.strip() for f in fields.split(",")]
    if token:
        ctx.obj.setdefault("_token", token)
        ctx.obj.setdefault("_display_name", display_name)
    if tmp_dir:
        ctx.obj.setdefault("_tmp_dir", tmp_dir)


# ── Describe (schema introspection for agents) ──────────────────────────────


def _collect_commands(group, prefix=""):
    """Recursively collect all commands with their params."""
    result = []
    for name, cmd in sorted(group.commands.items()):
        full_name = f"{prefix} {name}".strip() if prefix else name
        if isinstance(cmd, click.Group):
            result.extend(_collect_commands(cmd, full_name))
        else:
            params = []
            for p in cmd.params:
                if isinstance(p, click.Option):
                    if p.hidden:
                        continue
                    params.append({
                        "name": p.opts[0],
                        "type": p.type.name if hasattr(p.type, "name") else str(p.type),
                        "required": p.required,
                        **({"default": p.default} if p.default is not None and not p.required else {}),
                        **({"help": p.help} if p.help else {}),
                    })
                elif isinstance(p, click.Argument):
                    params.append({
                        "name": p.name,
                        "type": p.type.name if hasattr(p.type, "name") else str(p.type),
                        "kind": "argument",
                        "required": p.required,
                    })
            entry = {"command": full_name, "help": cmd.get_short_help_str(limit=120)}
            if params:
                entry["params"] = params
            result.append(entry)
    return result


@garmin.command("describe")
@click.argument("command_path", required=False, default=None)
@click.pass_context
def describe(ctx, command_path):
    """Describe available commands and parameters (for agent introspection).

    \b
    garmin describe              List all commands
    garmin describe activities   List commands in a group
    """
    target = garmin
    prefix = ""
    if command_path:
        for part in command_path.split():
            if isinstance(target, click.Group) and part in target.commands:
                target = target.commands[part]
                prefix = f"{prefix} {part}".strip() if prefix else part
            else:
                raise click.ClickException(f"Unknown command: {command_path}")

    if isinstance(target, click.Group):
        commands = _collect_commands(target, prefix)
    else:
        commands = _collect_commands(garmin)
        commands = [c for c in commands if c["command"] == command_path]

    _out(ctx, {"commands": commands})


@garmin.command("help")
@click.argument("command_path", nargs=-1)
@click.pass_context
def help_cmd(ctx, command_path):
    """Show human-readable help for a command (alias for `<cmd> --help`).

    \b
    garmin help                        Root help (same as `garmin --help`)
    garmin help history                Group help (same as `garmin history --help`)
    garmin help history sleep          Command help (same as `garmin history sleep --help`)

    \b
    Use `describe` instead when you want structured JSON for programmatic
    introspection; use `help` for human-readable text.
    """
    # Walk down from root, building a parent ctx chain so the Usage line
    # shows the full command path (e.g. "garmin history sleep"), not "help sleep".
    parent = click.Context(garmin, info_name="garmin")
    current = garmin
    for part in command_path:
        if not (isinstance(current, click.Group) and part in current.commands):
            raise click.ClickException(f"Unknown command: {' '.join(command_path)}")
        current = current.commands[part]
        parent = click.Context(current, info_name=part, parent=parent)
    # `parent` is now the ctx of the target itself; print its help
    click.echo(current.get_help(parent))


# ── Activities ───────────────────────────────────────────────────────────────


@garmin.group()
@click.pass_context
def activities(ctx):
    """Activity data: list, detail, splits, HR zones, types."""
    pass


@activities.command("list")
@click.option("--from", "start_date", default=None, help="Start date YYYY-MM-DD")
@click.option("--to", "end_date", default=None, help="End date YYYY-MM-DD")
@click.option("--type", "activity_type", default="", help="Filter: running, cycling...")
@click.option("--start", default=0, type=int, help="Pagination offset")
@click.option("--limit", default=20, type=int, help="Max results (max 100)")
@click.pass_context
def activities_list(ctx, start_date, end_date, activity_type, start, limit):
    """List activities by date range or pagination."""
    from garmin_mcp.api import activities as api

    fields = ctx.obj.get("fields")
    _run(ctx, lambda: api.get_activities(
        _client(ctx), start_date, end_date, activity_type, start, limit,
        fields=fields,
    ))


@activities.command("get")
@click.argument("activity_id", type=int)
@click.pass_context
def activities_get(ctx, activity_id):
    """Get detailed activity info."""
    from garmin_mcp.api import activities as api

    _run(ctx, lambda: api.get_activity(_client(ctx), activity_id))


@activities.command("splits")
@click.argument("activity_id", type=int)
@click.pass_context
def activities_splits(ctx, activity_id):
    """Get per-lap splits for an activity."""
    from garmin_mcp.api import activities as api

    _run(ctx, lambda: api.get_activity_splits(_client(ctx), activity_id))


@activities.command("hr-zones")
@click.argument("activity_id", type=int)
@click.pass_context
def activities_hr_zones(ctx, activity_id):
    """Get HR zone distribution for an activity."""
    from garmin_mcp.api import activities as api

    _run(ctx, lambda: api.get_activity_hr_in_timezones(_client(ctx), activity_id))


@activities.command("types")
@click.pass_context
def activities_types(ctx):
    """List all available activity types."""
    from garmin_mcp.api import activities as api

    _run(ctx, lambda: api.get_activity_types(_client(ctx)))


@activities.command("download")
@click.argument("activity_id", type=int)
@click.pass_context
def activities_download(ctx, activity_id):
    """Download activity as preprocessed CSV (pandas-ready).

    \b
    Downloads the original FIT recording, parses second-by-second data,
    fixes all gotchas, and writes a clean CSV. Ready for pd.read_csv().

    Columns (when available):
      timestamp, elapsed_s, distance_m, heart_rate, cadence_spm,
      speed_ms, pace_min_km, altitude_m, lat, lon, temperature_c,
      vertical_oscillation_mm, ground_contact_time_ms, step_length_cm,
      vertical_ratio_pct, power_w

    Preprocessing applied:
      - cadence: RPM×2 → steps/min
      - speed: enhanced_speed (m/s), not deprecated field
      - pace: computed min/km
      - GPS: semicircles → degrees
      - columns with all-null values dropped

    Load skill 'fit-analysis' for analysis patterns.

    \b
    Examples:
        activities download 12345
    """
    from garmin_mcp.api import activities as api

    _run(ctx, lambda: api.download_activity(
        _client(ctx), activity_id, "fit", _session_sandbox(ctx),
    ))


# ── Geographic ───────────────────────────────────────────────────────────────


@garmin.group()
@click.pass_context
def geographic(ctx):
    """Geographic narrative: parcours, terrain, environnement traversé."""
    pass


@geographic.command("activity")
@click.argument("activity_id", type=int)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["llm", "tsv", "json"]),
    default="llm",
    help="Output format (default llm)",
)
@click.pass_context
def geographic_activity(ctx, activity_id, fmt):
    """Geographic narrative of a Garmin activity (parcours, terrain).

    \b
    Pipeline (transparent to the agent):
      1. download the activity's FIT from Garmin Connect (in-memory)
      2. POST it as multipart to geo-runner /api/analyze
      3. return the narrative in the requested format

    \b
    Output formats:
      llm   - coach-preset narrative, m:ss/h:mm:ss compact (default)
      tsv   - tab-separated, pandas + Sheets/Excel friendly
      json  - full DTO with summary + trace + spans + timings

    \b
    Examples:
      geographic activity 22627191073
      geographic activity 22627191073 --format tsv --output run.tsv
      geographic activity 22627191073 --format json
    """
    from garmin_mcp.api import geographic as api

    # Bypass `_run`/`_out` — the body returned by geo-runner is already in
    # the right text shape for the chosen format. No JSON re-encoding, no
    # field filtering. We still need the same exception-to-ClickException
    # bridge that `_run` provides.
    try:
        text = api.analyze_activity(_client(ctx), activity_id, fmt)
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))

    output_path = ctx.obj.get("output")
    if output_path:
        sandbox = _session_sandbox(ctx)
        safe_path = _sanitize_path(output_path, sandbox)
        os.makedirs(os.path.dirname(safe_path) or sandbox, exist_ok=True)
        with open(safe_path, "w") as f:
            f.write(text)
        kb = round(len(text.encode("utf-8")) / 1024, 1)
        click.echo(
            f"{fmt} narrative ({kb} KB) written to {os.path.basename(safe_path)}"
        )
    else:
        click.echo(text, nl=False)


# ── Health ───────────────────────────────────────────────────────────────────


@garmin.group()
@click.pass_context
def health(ctx):
    """Daily health: sleep, stress, HR, body battery, SpO2, readiness."""
    pass


@health.command("snapshot")
@click.argument("date", default=None)
@click.pass_context
def health_snapshot(ctx, date):
    """Daily coaching overview: stats + sleep + readiness + body battery + HRV."""
    from garmin_mcp.api import health as api

    _run(ctx, lambda: api.get_coaching_snapshot(_client(ctx), date or _today()))


@health.command("stats")
@click.argument("date", default=None)
@click.pass_context
def health_stats(ctx, date):
    """Daily activity stats: steps, calories, HR, stress."""
    from garmin_mcp.api import health as api

    _run(ctx, lambda: api.get_stats(_client(ctx), date or _today()))


@health.command("sleep")
@click.argument("date", default=None)
@click.pass_context
def health_sleep(ctx, date):
    """Sleep summary: score, phases, SpO2, respiration, HRV."""
    from garmin_mcp.api import health as api

    _run(ctx, lambda: api.get_sleep(_client(ctx), date or _today()))


@health.command("stress")
@click.argument("date", default=None)
@click.pass_context
def health_stress(ctx, date):
    """Stress summary: avg/max levels, distribution."""
    from garmin_mcp.api import health as api

    _run(ctx, lambda: api.get_stress(_client(ctx), date or _today()))


@health.command("heart-rate")
@click.argument("date", default=None)
@click.pass_context
def health_heart_rate(ctx, date):
    """HR summary: resting, min, max, avg, 7-day trend."""
    from garmin_mcp.api import health as api

    _run(ctx, lambda: api.get_heart_rate(_client(ctx), date or _today()))


@health.command("respiration")
@click.argument("date", default=None)
@click.pass_context
def health_respiration(ctx, date):
    """Respiration: avg/min/max breaths per minute."""
    from garmin_mcp.api import health as api

    _run(ctx, lambda: api.get_respiration(_client(ctx), date or _today()))


@health.command("body-battery")
@click.option("--from", "start_date", required=True, help="Start date YYYY-MM-DD")
@click.option("--to", "end_date", required=True, help="End date YYYY-MM-DD")
@click.pass_context
def health_body_battery(ctx, start_date, end_date):
    """Body battery: charge/drain per day with activity events."""
    from garmin_mcp.api import health as api

    _run(ctx, lambda: api.get_body_battery(_client(ctx), start_date, end_date))


@health.command("spo2")
@click.argument("date", default=None)
@click.pass_context
def health_spo2(ctx, date):
    """SpO2: avg, lowest, latest, sleep avg."""
    from garmin_mcp.api import health as api

    _run(ctx, lambda: api.get_spo2(_client(ctx), date or _today()))


@health.command("training-readiness")
@click.argument("date", default=None)
@click.pass_context
def health_training_readiness(ctx, date):
    """Training readiness: score, contributing factors."""
    from garmin_mcp.api import health as api

    _run(ctx, lambda: api.get_training_readiness(_client(ctx), date or _today()))


# ── Training ─────────────────────────────────────────────────────────────────


@garmin.group()
@click.pass_context
def training(ctx):
    """Performance metrics: VO2max, HRV, training status, race predictions."""
    pass


@training.command("max-metrics")
@click.argument("date", default=None)
@click.pass_context
def training_max_metrics(ctx, date):
    """VO2max, fitness age, lactate threshold."""
    from garmin_mcp.api import training as api

    _run(ctx, lambda: api.get_max_metrics(_client(ctx), date or _today()))


@training.command("hrv")
@click.argument("date", default=None)
@click.pass_context
def training_hrv(ctx, date):
    """HRV overnight: last night avg, weekly avg, baseline, status."""
    from garmin_mcp.api import training as api

    _run(ctx, lambda: api.get_hrv_data(_client(ctx), date or _today()))


@training.command("status")
@click.argument("date", default=None)
@click.pass_context
def training_status(ctx, date):
    """Training status: productive/maintaining/detraining, ACWR, load balance."""
    from garmin_mcp.api import training as api

    _run(ctx, lambda: api.get_training_status(_client(ctx), date or _today()))


@training.command("progress")
@click.option("--from", "start_date", required=True, help="Start date YYYY-MM-DD")
@click.option("--to", "end_date", required=True, help="End date YYYY-MM-DD")
@click.option(
    "--metric",
    required=True,
    type=click.Choice(["distance", "duration", "elevationGain", "movingDuration"]),
    help="Metric to summarize",
)
@click.pass_context
def training_progress(ctx, start_date, end_date, metric):
    """Progress summary for a metric between dates."""
    from garmin_mcp.api import training as api

    _run(ctx, lambda: api.get_progress_summary(
        _client(ctx), start_date, end_date, metric
    ))


@training.command("race-predictions")
@click.pass_context
def training_race_predictions(ctx):
    """Race time predictions (5K, 10K, half, marathon)."""
    from garmin_mcp.api import training as api

    _run(ctx, lambda: api.get_race_predictions(_client(ctx)))


@training.command("goals")
@click.option(
    "--type",
    "goal_type",
    default="active",
    type=click.Choice(["active", "future", "past"]),
)
@click.pass_context
def training_goals(ctx, goal_type):
    """Garmin Connect goals."""
    from garmin_mcp.api import training as api

    _run(ctx, lambda: api.get_goals(_client(ctx), goal_type))


@training.command("personal-records")
@click.pass_context
def training_personal_records(ctx):
    """Personal records across all activities."""
    from garmin_mcp.api import training as api

    _run(ctx, lambda: api.get_personal_record(_client(ctx)))


# ── History (long-term time-series) ──────────────────────────────────────────


@garmin.group("history")
@click.pass_context
def history(ctx):
    """Long-term history (365d default) → CSV on disk for pandas analysis.

    \b
    Time-series commands: each writes max-precision, max-fields CSV to the
    session sandbox and prints the filename. No inline data in stdout —
    read the file with `pd.read_csv()` and group/filter in pandas.

    \b
    When to use `history` vs `health`/`training`:
      - `health sleep [date]` / `training hrv [date]`  → single-day snapshot
      - `history sleep` / `history heart-rate`          → multi-day trend (CSV)

    \b
    Keep multiple runs: use global `--output <name>.csv` to avoid overwriting
    the default filename. Default names include --agg when applicable, so
    `history running --agg weekly` and `--agg monthly` don't clash.

    \b
    Empty periods are omitted (Garmin's server doesn't return zero-activity weeks).
    To fill gaps for plotting:
      df = pd.read_csv("history_running_weekly.csv", parse_dates=["date"])
      df = df.set_index("date").reindex(pd.date_range(df.index.min(), df.index.max(), freq="W"))

    \b
    Subcommands: running, cycling, sleep, heart-rate, vo2max, race-predictions
    (HRV columns live in `history sleep` — avgOvernightHrv, hrv7dAverage, hrvStatus.)
    """
    pass


def _history_window(days: int, end: str | None) -> tuple[str, str]:
    """Compute (start, end) for a history command. Default: 365 days ending today."""
    from garmin_mcp.api.history import default_window

    if end is None:
        return default_window(days)
    end_d = _date.fromisoformat(end)
    start_d = end_d - _timedelta(days=days)
    return start_d.isoformat(), end_d.isoformat()


def _write_history_csv(
    ctx,
    fn,
    default_name_base: str,
    window: tuple[str, str],
    *,
    agg: str | None = None,
    units: str | None = None,
):
    """Run `fn()` to get rows, write CSV in session sandbox, echo filename + stats.

    Default filename = `{default_name_base}.csv` or `{base}_{agg}.csv` when agg
    is given — so weekly and monthly runs of the same command don't overwrite
    each other. Override with global `--output`.

    Echoes unit legend when provided so Apex sees Garmin's internal units
    (cm/ms/kJ/etc.) at the same moment as the filename.

    Catches ValueError from pre-flight checks (e.g. race-predictions 365d cap)
    and re-raises as ClickException for clean CLI error messages.
    """
    try:
        rows = fn()
    except ValueError as e:
        raise click.ClickException(str(e))

    sandbox = _session_sandbox(ctx)
    default_name = (
        f"{default_name_base}_{agg}.csv" if agg else f"{default_name_base}.csv"
    )
    output_name = ctx.obj.get("output") or default_name
    safe_path = _sanitize_path(output_name, sandbox)
    os.makedirs(os.path.dirname(safe_path) or sandbox, exist_ok=True)
    meta = write_csv_file(safe_path, rows)
    rel = os.path.relpath(safe_path, sandbox)
    start, end = window

    parts = [
        f"{rel} — {meta['rows']} rows × {meta['columns']} columns",
        f"[{start} → {end}]",
    ]
    if meta.get("dropped"):
        parts.append(f"({meta['dropped']} empty columns dropped)")
    if units:
        parts.append(f"[units: {units}]")
    click.echo(" ".join(parts))


_AGGREGATIONS = ("daily", "weekly", "monthly", "yearly", "lifetime")


# Per-command unit legends — echoed in stdout to keep Apex from tripping on
# Garmin's internal units (see SKILL.md and reference memory for details).
_UNITS_SPORT = "distance=cm, duration=ms, calories=kJ, speed=m/s×0.1, elevation=cm"
_UNITS_SLEEP = "phases=s, sleepNeed=min, HRV=ms, bedtime=epoch_ms"
_UNITS_HR = "HR=bpm"
_UNITS_VO2 = "vo2=ml/kg/min"
_UNITS_RACE = "time=s"


@history.command("running")
@click.option("--days", default=365, type=int, help="Days back from end (default 365)")
@click.option("--end", default=None, help="End date YYYY-MM-DD (default today)")
@click.option(
    "--agg",
    default="weekly",
    type=click.Choice(_AGGREGATIONS),
    help="Bucket size (daily/weekly/monthly/yearly/lifetime). Default weekly matches Garmin UI.",
)
@click.pass_context
def history_running(ctx, days, end, agg):
    """Running "Reports" — aggregated metrics per period.

    \b
    One row per period. Columns: countOfActivities + each metric flattened
    to _count/_min/_max/_avg/_sum (distance_sum, avgHr_avg, avgRunCadence_avg…).
    Units are Garmin-internal: distance/elevation in cm, duration in ms, speed in m/s×0.1.
    Empty metric columns (e.g. maxWheelchairCadence in run data) dropped automatically.

    \b
    Default filename: history_running_{agg}.csv (weekly+monthly don't overwrite).
    Override with global `--output path.csv` to pick a custom name.
    """
    from garmin_mcp.api import history as api

    window = _history_window(days, end)
    _write_history_csv(
        ctx,
        lambda: api.get_sport_stats(_client(ctx), "running", *window, aggregation=agg),
        "history_running",
        window,
        agg=agg,
        units=_UNITS_SPORT,
    )


@history.command("cycling")
@click.option("--days", default=365, type=int, help="Days back from end (default 365)")
@click.option("--end", default=None, help="End date YYYY-MM-DD (default today)")
@click.option(
    "--agg",
    default="weekly",
    type=click.Choice(_AGGREGATIONS),
    help="Bucket size (daily/weekly/monthly/yearly/lifetime). Default weekly matches Garmin UI.",
)
@click.pass_context
def history_cycling(ctx, days, end, agg):
    """Cycling "Reports" — aggregated metrics per period.

    \b
    One row per period. Columns: countOfActivities + each metric flattened
    to _count/_min/_max/_avg/_sum (distance_sum, avgHr_avg, avgBikeCadence_avg,
    avgPower_avg…). Units are Garmin-internal (see `history running`).
    Empty metric columns dropped automatically.

    \b
    Default filename: history_cycling_{agg}.csv. Override with global `--output`.
    """
    from garmin_mcp.api import history as api

    window = _history_window(days, end)
    _write_history_csv(
        ctx,
        lambda: api.get_sport_stats(_client(ctx), "cycling", *window, aggregation=agg),
        "history_cycling",
        window,
        agg=agg,
        units=_UNITS_SPORT,
    )


@history.command("sleep")
@click.option("--days", default=365, type=int, help="Days back from end (default 365)")
@click.option("--end", default=None, help="End date YYYY-MM-DD (default today)")
@click.pass_context
def history_sleep(ctx, days, end):
    """Daily sleep: score, phases, RHR, HRV, SpO2, respiration, bedtime, wake time.

    \b
    Granularity is daily only (Garmin's weekly sleep endpoint omits HRV/HR/SpO2,
    so we don't expose it). No `--agg` flag — resample in pandas if needed.

    \b
    Default filename: history_sleep.csv. Override with global `--output`.
    """
    from garmin_mcp.api import history as api

    window = _history_window(days, end)
    _write_history_csv(
        ctx,
        lambda: api.get_sleep(_client(ctx), *window),
        "history_sleep",
        window,
        units=_UNITS_SLEEP,
    )


@history.command("heart-rate")
@click.option("--days", default=365, type=int, help="Days back from end (default 365)")
@click.option("--end", default=None, help="End date YYYY-MM-DD (default today)")
@click.option(
    "--agg",
    default="daily",
    type=click.Choice(["daily", "weekly"]),
    help="Bucket size — only daily and weekly supported (no monthly from server).",
)
@click.pass_context
def history_heart_rate(ctx, days, end, agg):
    """Heart rate trend — resting HR + wellness min/max.

    \b
    Daily rows: date, restingHR, wellnessMaxAvgHR, wellnessMinAvgHR.
    Weekly rows: date (week start), avgRestingHR, wellnessMaxAvgHR, wellnessMinAvgHR.
    Canonical columns are always present (filled with null if server omits them).
    All values in bpm.

    \b
    Default filename: history_heart_rate_{agg}.csv. Override with global `--output`.
    """
    from garmin_mcp.api import history as api

    window = _history_window(days, end)
    _write_history_csv(
        ctx,
        lambda: api.get_heart_rate(_client(ctx), *window, aggregation=agg),
        "history_heart_rate",
        window,
        agg=agg,
        units=_UNITS_HR,
    )


@history.command("vo2max")
@click.option("--days", default=365, type=int, help="Days back from end (default 365)")
@click.option("--end", default=None, help="End date YYYY-MM-DD (default today)")
@click.option(
    "--agg",
    default="daily",
    type=click.Choice(["daily", "weekly", "monthly"]),
    help="Bucket size — daily/weekly/monthly supported (no yearly from server).",
)
@click.pass_context
def history_vo2max(ctx, days, end, agg):
    """VO2max trend for running + cycling.

    \b
    One row per period per sport (rows only present when that sport had data).
    Fields: date, sport, vo2MaxValue, vo2MaxPreciseValue, fitnessAge,
    fitnessAgeDescription, maxMetCategory. 2 API calls (one per sport).

    \b
    Default filename: history_vo2max_{agg}.csv. Override with global `--output`.
    """
    from garmin_mcp.api import history as api

    window = _history_window(days, end)
    _write_history_csv(
        ctx,
        lambda: api.get_vo2max(_client(ctx), *window, aggregation=agg),
        "history_vo2max",
        window,
        agg=agg,
        units=_UNITS_VO2,
    )


@history.command("race-predictions")
@click.option("--days", default=365, type=int, help="Days back from end (default 365)")
@click.option("--end", default=None, help="End date YYYY-MM-DD (default today)")
@click.pass_context
def history_race_predictions(ctx, days, end):
    """Daily race time predictions: 5K / 10K / half / marathon.

    \b
    Garmin caps this endpoint at 365 days — larger windows fail fast with a
    clear error (not a silent 400). No `--agg` flag (daily only from server).

    \b
    Default filename: history_race_predictions.csv. Override with global `--output`.
    """
    from garmin_mcp.api import history as api

    window = _history_window(days, end)
    _write_history_csv(
        ctx,
        lambda: api.get_race_predictions(_client(ctx), *window),
        "history_race_predictions",
        window,
        units=_UNITS_RACE,
    )


# ── Workouts ─────────────────────────────────────────────────────────────────


@garmin.group()
@click.pass_context
def workouts(ctx):
    """Workout library: list, create, schedule, delete."""
    pass


@workouts.command("list")
@click.pass_context
def workouts_list(ctx):
    """List all workouts in the library."""
    from garmin_mcp.api import workouts as api

    _run(ctx, lambda: api.get_workouts(_client(ctx)))


@workouts.command("get")
@click.argument("workout_id", type=int)
@click.pass_context
def workouts_get(ctx, workout_id):
    """Get detailed workout definition."""
    from garmin_mcp.api import workouts as api

    _run(ctx, lambda: api.get_workout_by_id(_client(ctx), workout_id))


@workouts.command("scheduled")
@click.option("--from", "start_date", required=True, help="Start date YYYY-MM-DD")
@click.option("--to", "end_date", required=True, help="End date YYYY-MM-DD")
@click.pass_context
def workouts_scheduled(ctx, start_date, end_date):
    """List workouts scheduled on the calendar."""
    from garmin_mcp.api import workouts as api

    _run(ctx, lambda: api.get_scheduled_workouts(_client(ctx), start_date, end_date))


@workouts.command("create")
@click.option("--json", "workout_json", default=None, help="Workout JSON definition (inline string)")
@click.option("--input", "input_file", default=None, help="Read workout JSON from file (sandboxed)")
@click.option("--date", default=None, help="Schedule date YYYY-MM-DD (optional)")
@click.pass_context
def workouts_create(ctx, workout_json, input_file, date):
    """Create a workout (and optionally schedule it).

    \b
    Provide workout data via --json (inline) or --input (file):
      garmin workouts create --json '{"workoutName":"Easy 5K",...}'
      garmin workouts create --input workout.json
      garmin workouts create --input workout.json --date 2026-03-20
    """
    from garmin_mcp.api import workouts as api

    if input_file and workout_json:
        raise click.ClickException("Use --json or --input, not both")
    if not input_file and not workout_json:
        raise click.ClickException("Provide --json or --input")

    workout_data = _read_input_file(ctx, input_file) if input_file else json.loads(workout_json)
    warnings = api.validate_workout_keys(workout_data)
    preview = {"action": "create_workout", "name": workout_data.get("workoutName"), "date": date}
    if warnings:
        preview["warnings"] = warnings
    _run(ctx, lambda: api.create_workout(_client(ctx), workout_data, date), dry_run_preview=preview)


@workouts.command("update")
@click.argument("workout_id", type=int)
@click.option("--json", "workout_json", default=None, help="New workout JSON definition (inline string)")
@click.option("--input", "input_file", default=None, help="Read workout JSON from file (sandboxed)")
@click.pass_context
def workouts_update(ctx, workout_id, workout_json, input_file):
    """Replace an existing workout's definition.

    \b
    Provide workout data via --json (inline) or --input (file):
      garmin workouts update 123 --json '{"workoutName":"Updated",...}'
      garmin workouts update 123 --input workout.json
    """
    from garmin_mcp.api import workouts as api

    if input_file and workout_json:
        raise click.ClickException("Use --json or --input, not both")
    if not input_file and not workout_json:
        raise click.ClickException("Provide --json or --input")

    workout_data = _read_input_file(ctx, input_file) if input_file else json.loads(workout_json)
    warnings = api.validate_workout_keys(workout_data)
    preview = {"action": "update_workout", "workout_id": workout_id, "name": workout_data.get("workoutName")}
    if warnings:
        preview["warnings"] = warnings
    _run(ctx, lambda: api.update_workout(_client(ctx), workout_id, workout_data), dry_run_preview=preview)


@workouts.command("delete")
@click.argument("workout_id", type=int)
@click.pass_context
def workouts_delete(ctx, workout_id):
    """Delete a workout from the library."""
    from garmin_mcp.api import workouts as api

    preview = {"action": "delete_workout", "workout_id": workout_id}
    _run(ctx, lambda: api.delete_workout(_client(ctx), workout_id), dry_run_preview=preview)


@workouts.command("unschedule")
@click.argument("schedule_id", type=int)
@click.pass_context
def workouts_unschedule(ctx, schedule_id):
    """Remove a scheduled workout from the calendar."""
    from garmin_mcp.api import workouts as api

    preview = {"action": "unschedule_workout", "schedule_id": schedule_id}
    _run(ctx, lambda: api.unschedule_workout(_client(ctx), schedule_id), dry_run_preview=preview)


@workouts.command("reschedule")
@click.argument("schedule_id", type=int)
@click.option("--date", required=True, help="New date YYYY-MM-DD")
@click.pass_context
def workouts_reschedule(ctx, schedule_id, date):
    """Move a scheduled workout to a different date."""
    from garmin_mcp.api import workouts as api

    preview = {"action": "reschedule_workout", "schedule_id": schedule_id, "new_date": date}
    _run(ctx, lambda: api.reschedule_workout(_client(ctx), schedule_id, date), dry_run_preview=preview)


@workouts.command("schedule")
@click.argument("workout_id", type=int)
@click.option("--date", required=True, help="Schedule date YYYY-MM-DD")
@click.pass_context
def workouts_schedule(ctx, workout_id, date):
    """Schedule an existing workout from the library onto a calendar date."""
    from garmin_mcp.api import workouts as api

    preview = {"action": "schedule_workout", "workout_id": workout_id, "date": date}
    _run(ctx, lambda: api.schedule_workout(_client(ctx), workout_id, date), dry_run_preview=preview)


# ── Profile ──────────────────────────────────────────────────────────────────


@garmin.group()
@click.pass_context
def profile(ctx):
    """User profile, settings, devices."""
    pass


@profile.command("name")
@click.pass_context
def profile_name(ctx):
    """Get user's display name."""
    from garmin_mcp.api import profile as api

    name = api.get_full_name(_client(ctx))
    click.echo(name)


@profile.command("info")
@click.pass_context
def profile_info(ctx):
    """User profile: settings (weight, height, VO2max, lactate threshold), unit system."""
    from garmin_mcp.api import profile as api

    _run(ctx, lambda: api.get_user_profile(_client(ctx)))


@profile.command("hr-zones")
@click.pass_context
def profile_hr_zones(ctx):
    """HR and power zone boundaries (from latest activity)."""
    from garmin_mcp.api import profile as api

    _run(ctx, lambda: api.get_hr_zones(_client(ctx)))


@profile.command("devices")
@click.pass_context
def profile_devices(ctx):
    """List connected devices."""
    from garmin_mcp.api import profile as api

    _run(ctx, lambda: api.get_devices(_client(ctx)))


# ── Gear ─────────────────────────────────────────────────────────────────────


@garmin.group()
@click.pass_context
def gear(ctx):
    """Gear: shoes, bikes, accessories."""
    pass


@gear.command("list")
@click.argument("user_profile_id")
@click.pass_context
def gear_list(ctx, user_profile_id):
    """List all gear with usage stats."""
    from garmin_mcp.utils import clean_nones

    client = _client(ctx)
    gear_data = client.get_gear(user_profile_id)
    if not gear_data:
        _out(ctx, {"error": "No gear found."})
        return
    curated = {
        "count": len(gear_data),
        "gear": [
            clean_nones({
                "uuid": g.get("uuid"),
                "display_name": g.get("displayName"),
                "model_name": g.get("modelName"),
                "brand_name": g.get("brandName"),
                "gear_type": g.get("gearTypePk"),
                "maximum_distance_meters": g.get("maximumDistanceMeter"),
                "current_distance_meters": (
                    g.get("gearStatusDTOList", [{}])[0].get("totalDistanceInMeters")
                    if g.get("gearStatusDTOList")
                    else None
                ),
                "date_begun": g.get("dateBegun"),
                "date_retired": g.get("dateRetired"),
            })
            for g in gear_data
        ],
    }
    _out(ctx, curated)


@gear.command("add")
@click.argument("activity_id", type=int)
@click.argument("gear_uuid")
@click.pass_context
def gear_add(ctx, activity_id, gear_uuid):
    """Associate gear with an activity."""
    def _do():
        _client(ctx).add_gear_to_activity(gear_uuid, activity_id)
        return {"status": "success", "activity_id": activity_id, "gear_uuid": gear_uuid}
    preview = {"action": "add_gear", "activity_id": activity_id, "gear_uuid": gear_uuid}
    _run(ctx, _do, dry_run_preview=preview)


@gear.command("remove")
@click.argument("activity_id", type=int)
@click.argument("gear_uuid")
@click.pass_context
def gear_remove(ctx, activity_id, gear_uuid):
    """Remove gear from an activity."""
    def _do():
        _client(ctx).remove_gear_from_activity(gear_uuid, activity_id)
        return {"status": "success", "activity_id": activity_id, "gear_uuid": gear_uuid}
    preview = {"action": "remove_gear", "activity_id": activity_id, "gear_uuid": gear_uuid}
    _run(ctx, _do, dry_run_preview=preview)


# ── Body ─────────────────────────────────────────────────────────────────────


@garmin.group()
@click.pass_context
def body(ctx):
    """Body data: weight measurements."""
    pass


@body.command("weigh-ins")
@click.option("--from", "start_date", required=True, help="Start date YYYY-MM-DD")
@click.option("--to", "end_date", required=True, help="End date YYYY-MM-DD")
@click.pass_context
def body_weigh_ins(ctx, start_date, end_date):
    """Get weight measurements between dates."""
    client = _client(ctx)
    raw = client.get_weigh_ins(start_date, end_date)
    if not raw:
        _out(ctx, {"error": f"No weight data between {start_date} and {end_date}"})
        return

    entries = []
    if isinstance(raw, dict):
        for day in raw.get("dailyWeightSummaries", []):
            entries.extend(day.get("allWeightMetrics", []))
        if not entries and "weight" in raw:
            entries = [raw]
    elif isinstance(raw, list):
        entries = raw

    if not entries:
        _out(ctx, {"error": f"No weight data between {start_date} and {end_date}"})
        return

    from garmin_mcp.utils import clean_nones

    curated = {
        "count": len(entries),
        "date_range": {"start": start_date, "end": end_date},
        "measurements": [
            clean_nones({
                "date": w.get("date") or w.get("calendarDate"),
                "weight_grams": w.get("weight"),
                "bmi": w.get("bmi"),
                "body_fat_percent": w.get("bodyFat"),
                "body_water_percent": w.get("bodyWater"),
                "bone_mass_grams": w.get("boneMass"),
                "muscle_mass_grams": w.get("muscleMass"),
                "source_type": w.get("sourceType"),
            })
            for w in entries
        ],
    }
    _out(ctx, curated)


@body.command("add-weight")
@click.argument("weight", type=float)
@click.option("--unit", default="kg", type=click.Choice(["kg", "lb"]))
@click.option("--date-timestamp", default=None, help="Local timestamp YYYY-MM-DDThh:mm:ss")
@click.option("--gmt-timestamp", default=None, help="GMT timestamp YYYY-MM-DDThh:mm:ss")
@click.pass_context
def body_add_weight(ctx, weight, unit, date_timestamp, gmt_timestamp):
    """Add a weight measurement."""
    def _do():
        client = _client(ctx)
        if date_timestamp and gmt_timestamp:
            client.add_weigh_in_with_timestamps(
                weight=weight,
                unitKey=unit,
                dateTimestamp=date_timestamp,
                gmtTimestamp=gmt_timestamp,
            )
        else:
            client.add_weigh_in(weight=weight, unitKey=unit)
        result = {"status": "success", "weight": weight, "unit": unit}
        if date_timestamp:
            result["timestamp_local"] = date_timestamp
        return result
    preview = {"action": "add_weight", "weight": weight, "unit": unit}
    _run(ctx, _do, dry_run_preview=preview)


@body.command("delete-weight")
@click.argument("date")
@click.option("--all/--no-all", "delete_all", default=True)
@click.pass_context
def body_delete_weight(ctx, date, delete_all):
    """Delete weight measurements for a date."""
    def _do():
        _client(ctx).delete_weigh_ins(date, delete_all=delete_all)
        return {"status": "success", "date": date}
    preview = {"action": "delete_weight", "date": date, "delete_all": delete_all}
    _run(ctx, _do, dry_run_preview=preview)


# ── Calendar ─────────────────────────────────────────────────────────────────


@garmin.group()
@click.pass_context
def calendar(ctx):
    """Calendar: month overview, race events."""
    pass


@calendar.command("month")
@click.argument("year", type=int)
@click.argument("month", type=int)
@click.pass_context
def calendar_month(ctx, year, month):
    """Month overview: activities, workouts, events, rest days."""
    from garmin_mcp.utils import clean_nones

    client = _client(ctx)
    raw = client.get_calendar_month(year, month)
    if not raw:
        _out(ctx, {"error": f"No calendar data for {year}-{month:02d}"})
        return

    items = []
    for item in raw.get("calendarItems", []):
        curated = clean_nones({
            "date": item.get("date"),
            "type": item.get("itemType"),
            "title": item.get("title"),
            "activity_type_id": item.get("activityTypeId"),
            "distance_meters": item.get("distance"),
            "duration_seconds": item.get("duration"),
            "event_type": item.get("eventType"),
        })
        items.append(curated)

    _out(ctx, {"year": year, "month": month, "items": items})


@calendar.command("events")
@click.option("--from", "start_date", required=True, help="Start date YYYY-MM-DD")
@click.option("--to", "end_date", required=True, help="End date YYYY-MM-DD")
@click.option("--limit", default=20, type=int)
@click.pass_context
def calendar_events(ctx, start_date, end_date, limit):
    """Race events within a date range."""
    client = _client(ctx)
    url = "/calendar-service/events"
    params = {
        "startDate": start_date,
        "endDate": end_date,
        "limit": limit,
        "pageIndex": 1,
        "sortOrder": "eventDate_asc",
    }
    raw = client.garth.connectapi(url, params=params)
    if not raw:
        _out(ctx, {"error": f"No events between {start_date} and {end_date}"})
        return
    _out(ctx, _curate_events(raw))


@calendar.command("upcoming")
@click.option("--days", default=7, type=int, help="Days forward to look")
@click.pass_context
def calendar_upcoming(ctx, days):
    """Upcoming calendar items: workouts, activities, events, rest days."""
    from datetime import date, timedelta
    from garmin_mcp.utils import clean_nones

    client = _client(ctx)
    start = date.today().strftime("%Y-%m-%d")
    end = (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")
    items = client.get_calendar_items_for_range(start, end)
    if not items:
        _out(ctx, {"error": f"No calendar items in the next {days} days"})
        return
    curated = []
    for item in items:
        curated.append(clean_nones({
            "date": item.get("date"),
            "type": item.get("itemType"),
            "title": item.get("title"),
            "activity_type_id": item.get("activityTypeId"),
            "distance_meters": item.get("distance"),
            "duration_seconds": item.get("duration"),
            "event_type": item.get("eventType"),
        }))
    _out(ctx, {"from": start, "to": end, "items": curated})


def _curate_events(events_data):
    """Curate events API response."""
    from garmin_mcp.utils import clean_nones

    events_list = events_data
    if isinstance(events_data, dict):
        events_list = events_data.get("events", events_data.get("items", [events_data]))
    if not isinstance(events_list, list):
        return events_data

    return [
        clean_nones({
            "event_id": e.get("uuid") or e.get("id"),
            "name": e.get("eventName") or e.get("name") or e.get("title"),
            "date": e.get("eventDate") or e.get("date"),
            "event_type": e.get("eventType") or e.get("sportType"),
            "distance_meters": e.get("distance"),
            "location": e.get("location"),
            "goal_time_seconds": e.get("goalTime"),
            "url": e.get("url"),
        })
        for e in events_list
    ]


# ── Execute helper (for HTTP handler / programmatic use) ────────────────────


def _validate_command(command: str) -> str:
    """Validate and sanitize command input. Reject control chars and shell tricks."""
    if not command or not command.strip():
        raise ValueError("Empty command")
    # Reject control characters (below ASCII 0x20 except space, tab, newline)
    for ch in command:
        if ord(ch) < 0x20 and ch not in (" ", "\t", "\n"):
            raise ValueError(f"Control character U+{ord(ch):04X} rejected")
    # Reject shell metacharacters — this is a CLI, not a shell
    for dangerous in (";", "&&", "||", "|", "`", "$(", "${", ">", "<"):
        if dangerous in command:
            raise ValueError(f"Shell metacharacter '{dangerous}' rejected")
    return command.strip()


# Global flags that belong to the root garmin group.
# AI agents often place these after the subcommand (e.g. "activities list --fields id,name")
# but Click requires them before the subcommand. We hoist them automatically.
_GLOBAL_FLAGS_WITH_VALUE = ("--format", "--fields", "--output")
_GLOBAL_FLAGS_BOOLEAN = ("--dry-run",)


def _hoist_global_flags(args: list[str]) -> list[str]:
    """Move global flags from anywhere in args to the front.

    Click requires group-level options before the subcommand.
    AI agents consistently put them after. This fixes it transparently.
    """
    global_args = []
    rest = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in _GLOBAL_FLAGS_WITH_VALUE:
            global_args.append(arg)
            if i + 1 < len(args):
                global_args.append(args[i + 1])
                i += 2
            else:
                i += 1
        elif arg in _GLOBAL_FLAGS_BOOLEAN:
            global_args.append(arg)
            i += 1
        elif any(arg.startswith(f + "=") for f in _GLOBAL_FLAGS_WITH_VALUE):
            # Handle --fields=id,name style
            global_args.append(arg)
            i += 1
        else:
            rest.append(arg)
            i += 1
    return global_args + rest


def execute(command: str, token: str, display_name: str = None, tmp_dir: str = None) -> dict:
    """Execute a CLI command string, return {stdout, stderr, exit_code, refreshed_token?}.

    Used by the /cli HTTP endpoint and tests.

    Input is validated: control characters and shell metacharacters are rejected.
    Commands are parsed by Click, not by a shell — no shell expansion occurs.
    Global flags (--fields, --format, --output, --dry-run) are hoisted to the front
    regardless of where the AI places them in the command.

    If garth refreshed the OAuth2 token during execution, `refreshed_token` is set
    to the new base64-encoded token blob. The caller (server.py) should propagate
    this back to the client so it can update its stored JWT.
    """
    import shlex
    import inspect
    from click.testing import CliRunner

    try:
        command = _validate_command(command)
    except ValueError as e:
        return {"stdout": "", "stderr": str(e), "exit_code": 2}

    # Click 8.3+ removed mix_stderr (stderr is separated by default)
    kwargs = {}
    if "mix_stderr" in inspect.signature(CliRunner).parameters:
        kwargs["mix_stderr"] = False
    runner = CliRunner(**kwargs)
    args = ["--token", token]
    if display_name:
        args += ["--display-name", display_name]
    if tmp_dir:
        args += ["--tmp-dir", tmp_dir]

    # Pre-create the garth client so we hold a local reference for token
    # comparison after execution. _client(ctx) will find it in ctx.obj["client"]
    # and skip lazy creation. This avoids a module-level global (race condition).
    # May fail with invalid tokens (e.g. --dry-run with fake token) — that's fine,
    # _client(ctx) will create it lazily if needed.
    try:
        client = create_client_from_tokens(token, display_name)
    except Exception:
        client = None

    # Extract --json value BEFORE shlex.split — shlex strips quotes from JSON,
    # turning {"key":"val"} into {key:val} which is invalid.
    json_value = None
    import re
    json_match = re.search(r'--json\s+(.+)', command)
    if json_match:
        raw_json = json_match.group(1).strip()
        # Find the JSON object boundaries (handle nested braces)
        if raw_json.startswith('{') or raw_json.startswith('['):
            depth = 0
            in_string = False
            escape = False
            end = 0
            for ci, ch in enumerate(raw_json):
                if escape:
                    escape = False
                    continue
                if ch == '\\':
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch in ('{', '['):
                    depth += 1
                elif ch in ('}', ']'):
                    depth -= 1
                    if depth == 0:
                        end = ci + 1
                        break
            if end > 0:
                json_value = raw_json[:end]
                # Remove --json <value> from command before shlex.split
                command = command[:json_match.start()] + command[json_match.start() + len('--json ') + len(raw_json[:end]):]
        elif raw_json.startswith("'") or raw_json.startswith('"'):
            # Quoted JSON — let shlex handle it
            pass

    cmd_args = shlex.split(command)
    cmd_args = _hoist_global_flags(cmd_args)
    # Re-inject --json with the preserved value
    if json_value is not None:
        cmd_args += ["--json", json_value]
    args += cmd_args

    # Pass pre-created client via obj so _client(ctx) reuses it
    obj = {"client": client} if client else {}
    result = runner.invoke(garmin, args, obj=obj, catch_exceptions=True)
    stdout = result.output or ""
    stderr = ""
    if hasattr(result, "stderr") and result.stderr:
        stderr = result.stderr

    # Click 8.3+ mixes err=True output into both stdout and stderr — strip duplicates
    if stderr and stdout:
        for line in stderr.strip().splitlines():
            stdout = stdout.replace(line + "\n", "", 1)

    # Detect if garth refreshed tokens during execution (thread-safe: local ref)
    refreshed_token = None
    if client:
        try:
            new_token = client.garth.dumps()
            if new_token != token:
                refreshed_token = new_token
        except Exception:
            pass

    resp = {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": result.exit_code,
    }
    if refreshed_token:
        resp["refreshed_token"] = refreshed_token

    return resp
