"""`describe`: the commands for an agent, in three sizes.

- `describe`: an index, one line per command, by group (~3 KB, the whole CLI);
- `describe <group>`: each command's options and the names of its output fields;
- `describe <group> <command>`: its options, and each output field with its meaning.

Output fields come from the command's field registry (`api/*_fields.py`), set
with `@returns(...)` above the command: they cannot drift from the code.
"""

from __future__ import annotations

import click

from garmin_mcp.api.fields import FieldSet

_INDEX_HELP_LIMIT = 50


def returns(*field_sets: FieldSet, **sections: FieldSet):
    """Above `@group.command(...)`: the fields of the command's answer.

    Positional: the answer's own fields (or its items'). Keyword: a section of
    the answer (`health snapshot` → `stats=…, sleep=…`).
    """
    def mark(command: click.Command) -> click.Command:
        command.output_fields = [("", fs) for fs in field_sets] + list(sections.items())
        return command
    return mark


def index(group: click.Group, prefix: str = "") -> dict[str, str]:
    """Every command under `group` (its path) and the start of its help."""
    lines = {}
    for name, cmd in sorted(group.commands.items()):
        path = f"{prefix} {name}".strip()
        if isinstance(cmd, click.Group):
            lines.update(index(cmd, path))
        else:
            lines[path] = _gist(cmd)
    return lines


def grouped_index(group: click.Group) -> dict:
    """`index`, by top-level group: `{"activities": {"list": "…", "get": "…"}, "help": "…"}`."""
    out: dict = {}
    for path, gist in index(group).items():
        head, _, rest = path.partition(" ")
        if rest:
            out.setdefault(head, {})[rest] = gist
        else:
            out[head] = gist
    return out


def _gist(cmd: click.Command) -> str:
    """The first sentence of the help, at most `_INDEX_HELP_LIMIT` characters."""
    line = (cmd.help or "").strip().split("\n")[0]
    for sep in (". ",):
        cut = line.find(sep)
        if cut > 15:
            line = line[:cut]
    line = line.rstrip(".")
    if len(line) > _INDEX_HELP_LIMIT:
        line = line[:line.rfind(" ", 0, _INDEX_HELP_LIMIT)] + "…"
    return line


def commands(group: click.Group, prefix: str, *, field_docs: bool) -> list[dict]:
    """Each command under `group`: options, and its output fields (with their meaning if `field_docs`)."""
    entries = []
    for name, cmd in sorted(group.commands.items()):
        path = f"{prefix} {name}".strip()
        if isinstance(cmd, click.Group):
            entries.extend(commands(cmd, path, field_docs=field_docs))
        else:
            entries.append(command(cmd, path, field_docs=field_docs))
    return entries


def command(cmd: click.Command, path: str, *, field_docs: bool) -> dict:
    entry = {"command": path, "help": cmd.get_short_help_str(limit=200)}
    params = [_param(p) for p in cmd.params if not getattr(p, "hidden", False)]
    if params:
        entry["params"] = params
    outputs = getattr(cmd, "output_fields", [])
    if outputs:
        entry["output"] = {_label(section, fs): _fields(fs, field_docs) for section, fs in outputs}
    return entry


def _label(section: str, field_set: FieldSet) -> str:
    """Where the fields are in the answer: `activities[]`, `stats`, or `.` (the answer itself)."""
    if section:
        return section
    return f"{field_set.items_key}[]" if field_set.items_key else "."


def _fields(field_set: FieldSet, docs: bool):
    if not docs:
        return [f.name for f in field_set.fields]
    return {f.name: f.doc for f in field_set.fields}


def _param(p: click.Parameter) -> str:
    """One option or argument in one line: `--by lap|interval|run-walk|km =lap: help`."""
    kind = p.type
    if isinstance(kind, click.Choice):
        value = "|".join(kind.choices)
    else:
        value = f"<{kind.name}>"
    if isinstance(p, click.Argument):
        text = f"{p.human_readable_name} {value}" + ("" if p.required else " (optional)")
    elif getattr(p, "is_flag", False):
        text = p.opts[0]
    else:
        text = f"{p.opts[0]} {value}"
        if p.required:
            text += " (required)"
        elif p.default not in (None, (), False):
            text += f" ={p.default}"
    help_text = getattr(p, "help", None)
    return f"{text}: {help_text}" if help_text else text
