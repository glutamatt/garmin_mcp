"""Suggestions for an unknown command: `steps` → `history daily`, `health stats`.

An agent that guesses a command name (`steps get`, `history stats`) gets the
commands it most likely meant in the error, instead of a bare "No such command".
"""

from __future__ import annotations

import difflib

import click

# Words agents use for data whose command has another name. Seen in prod: `steps get`.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "steps": ("history daily", "health stats"),
    "stats": ("health stats", "history daily"),
    "floors": ("history daily", "health stats"),
    "intensity": ("history daily", "health stats"),
    "weight": ("body weigh-ins",),
    "laps": ("activities splits",),
    "fit": ("activities download",),
}

_MAX_SUGGESTIONS = 4


def _leaves(group: click.Group, prefix: str = "") -> list[str]:
    """Every command path under `group`: `activities list`, `geographic history query`…"""
    paths = []
    for name, cmd in sorted(group.commands.items()):
        path = f"{prefix} {name}".strip()
        if isinstance(cmd, click.Group):
            paths.extend(_leaves(cmd, path))
        else:
            paths.append(path)
    return paths


def suggestions(root: click.Group, group_path: str, word: str) -> list[str]:
    """Commands close to `word`, typed where `group_path` expects a subcommand.

    In order: the synonyms; commands of the same group with a close name;
    commands anywhere whose last word is close (`sleep` → `health sleep`, `history sleep`).
    """
    group = root
    for part in group_path.split():
        group = group.commands[part]
    lowered = word.lower()
    found = list(SYNONYMS.get(lowered, ()))
    found += [f"{group_path} {name}".strip()
              for name in difflib.get_close_matches(lowered, list(group.commands), n=3, cutoff=0.6)]
    leaves = _leaves(root)
    close_leaves = set(difflib.get_close_matches(lowered, [p.split()[-1] for p in leaves], n=5, cutoff=0.75))
    found += [p for p in leaves if p.split()[-1] in close_leaves]
    return list(dict.fromkeys(found))[:_MAX_SUGGESTIONS]


def unknown_command(root: click.Group, group_path: str, word: str) -> str:
    """The error for an unknown command, with the commands close to it."""
    close = suggestions(root, group_path, word)
    where = f" in '{group_path}'" if group_path else ""
    message = f"No such command '{word}'{where}."
    if close:
        message += f" Did you mean: {', '.join(close)}?"
    return message + " All commands: `help`."


class SuggestingGroup(click.Group):
    """A command group that suggests close commands for an unknown name. Its subgroups are too."""

    group_class = type  # `@group.group()` makes a SuggestingGroup

    def resolve_command(self, ctx: click.Context, args: list[str]):
        name = args[0] if args else ""
        if name and not name.startswith("-") and not ctx.resilient_parsing \
                and self.get_command(ctx, name) is None:
            root = ctx.find_root().command
            group_path = " ".join(ctx.command_path.split()[1:])
            ctx.fail(unknown_command(root, group_path, name))
        return super().resolve_command(ctx, args)
