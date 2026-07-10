from __future__ import annotations


def normalize_json_row(row) -> dict:
    data = dict(row)
    for key in tuple(data):
        if key.endswith("__jsonb"):
            data[key.removesuffix("__jsonb")] = data.pop(key)
    return data


def json_value(row, key: str):
    try:
        return row[key]
    except KeyError:
        return row[f"{key}__jsonb"]
