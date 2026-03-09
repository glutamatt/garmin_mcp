"""Output formatting: field filtering + JSON/table rendering."""

import json
from garmin_mcp.utils import format_duration, format_distance, format_pace


def find_missing_fields(data, fields: list[str]) -> list[str]:
    """Return requested fields not present in the data's first item."""
    sample = None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        sample = data[0]
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                sample = v[0]
                break
        if sample is None and data:
            sample = data
    if not sample or not isinstance(sample, dict):
        return []
    return [f for f in fields if f not in sample]


# Always included in --fields output regardless of user selection
_ALWAYS_FIELDS = {"type"}


def filter_fields(data, fields: list[str]):
    """Filter data to only include specified fields.

    Heuristic:
    - List of dicts → filter each item's keys
    - Dict with list-of-dicts values → filter list items, keep scalar metadata
    - Flat dict → filter keys directly
    """
    fields = list(set(fields) | _ALWAYS_FIELDS)
    if isinstance(data, list):
        return [_filter_dict(item, fields) for item in data if isinstance(item, dict)]

    if not isinstance(data, dict):
        return data

    has_data_list = any(
        isinstance(v, list) and v and isinstance(v[0], dict)
        for v in data.values()
    )

    if has_data_list:
        result = {}
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                result[k] = [_filter_dict(item, fields) for item in v]
            else:
                result[k] = v  # keep metadata (count, date_range, etc.)
        return result
    else:
        return _filter_dict(data, fields)


def _filter_dict(d: dict, fields: list[str]) -> dict:
    return {k: v for k, v in d.items() if k in fields}


def format_output(data, fmt: str = "json") -> str:
    if fmt == "table":
        return _format_table(data)
    return json.dumps(data, indent=2, ensure_ascii=False)


def _format_table(data) -> str:
    """Format data as a human-readable table."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"

    items = None
    header_info = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                items = v
            else:
                header_info.append(f"{k}: {v}")

    lines = []
    if header_info:
        lines.extend(header_info)
        lines.append("")

    if items is not None:
        if not items:
            lines.append("(empty)")
        else:
            keys = list(items[0].keys())
            widths = {k: len(k) for k in keys}
            str_rows = []
            for item in items:
                row = {}
                for k in keys:
                    s = _format_value(k, item.get(k, ""))
                    row[k] = s
                    widths[k] = max(widths[k], len(s))
                str_rows.append(row)

            lines.append("  ".join(k.ljust(widths[k]) for k in keys))
            lines.append("  ".join("-" * widths[k] for k in keys))
            for row in str_rows:
                lines.append("  ".join(row.get(k, "").ljust(widths[k]) for k in keys))
    elif isinstance(data, dict):
        max_key_len = max(len(k) for k in data.keys()) if data else 0
        for k, v in data.items():
            lines.append(f"{k.ljust(max_key_len)}  {_format_value(k, v)}")

    return "\n".join(lines)


def _format_value(key: str, value) -> str:
    """Format a value for table display with smart formatting for known fields."""
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    if "duration" in key and "seconds" in key and isinstance(value, (int, float)):
        return format_duration(value)
    if "distance" in key and "meters" in key and isinstance(value, (int, float)):
        return format_distance(value)
    if "speed" in key and "mps" in key and isinstance(value, (int, float)):
        p = format_pace(value)
        return p if p else str(value)

    return str(value)
