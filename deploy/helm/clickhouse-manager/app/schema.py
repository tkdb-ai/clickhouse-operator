"""Schema-driven form definition, sourced from the chart's values.schema.json.

The chart's `values.schema.json` is the single source of truth: Helm uses it to
validate values.yaml, and this module turns it into the GUI form. Properties
carry an optional `x-form` keyword (ignored by Helm) marking which values become
friendly form fields, their group, order, and widget. Everything else stays
editable via the Advanced YAML box.

Edit values.schema.json in the chart → the GUI updates automatically.
"""
import copy
import json
import os

import yaml

try:  # optional: enables values validation matching Helm
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

CHART_PATH = os.environ.get(
    "CHART_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "clickhouse-helm-chart")),
)
SCHEMA_JSON = os.environ.get("SCHEMA_JSON", os.path.join(CHART_PATH, "values.schema.json"))
CHART_VALUES = os.path.join(CHART_PATH, "values.yaml")

# Preferred display order for groups; unknown groups are appended after these.
GROUP_ORDER = ["Topology", "Storage & Resources", "Users", "Add-ons"]

# Paths build_values sets to null itself (not user input); hidden from the
# Advanced box on edit.
DERIVED_NULL_PATHS = ["podTemplate.extraEnv", "podTemplate.extraVolumeMounts"]

_JSON_TYPE_TO_WIDGET = {
    "integer": "number",
    "number": "number",
    "boolean": "bool",
    "string": "text",
}


def load_json_schema():
    try:
        with open(SCHEMA_JSON) as fh:
            return json.load(fh)
    except OSError:
        return None


def _field_from_property(path, prop):
    """Turn a JSON Schema leaf property (with x-form) into a form field dict."""
    xform = prop.get("x-form", {}) or {}
    jtype = prop.get("type", "string")
    if isinstance(jtype, list):  # e.g. ["string", "null"]
        jtype = next((t for t in jtype if t != "null"), "string")

    if xform.get("widget") == "password":
        ftype = "password"
    elif prop.get("enum"):
        ftype = "select"
    else:
        ftype = _JSON_TYPE_TO_WIDGET.get(jtype, "text")

    return {
        "path": path,
        "label": xform.get("label") or prop.get("title") or path.split(".")[-1],
        "type": ftype,
        "options": prop.get("enum"),
        "default": prop.get("default", "" if ftype != "number" else 0),
        "help": prop.get("description"),
        "allowEmpty": bool(xform.get("allowEmpty")),
        "group": xform.get("group", "Other"),
        "order": xform.get("order", 999),
    }


def _walk(properties, prefix, fields, constants):
    for key, prop in (properties or {}).items():
        if not isinstance(prop, dict):
            continue
        path = f"{prefix}.{key}" if prefix else key
        xform = prop.get("x-form")
        if xform is not None:
            if xform.get("constant"):
                constants[path] = prop.get("default")
            else:
                fields.append(_field_from_property(path, prop))
        elif "properties" in prop:
            _walk(prop["properties"], path, fields, constants)


def load_schema():
    """Synthesize the form model {groups, constants} from values.schema.json.

    Kept in the same shape the templates and chart.build_values already consume,
    so only this function changes when the schema source changes.
    """
    raw = load_json_schema() or {}
    fields, constants = [], {}
    _walk(raw.get("properties", {}), "", fields, constants)

    # bucket fields into groups, ordered
    by_group = {}
    for field in fields:
        by_group.setdefault(field["group"], []).append(field)

    def group_key(name):
        return (GROUP_ORDER.index(name) if name in GROUP_ORDER else len(GROUP_ORDER), name)

    groups = []
    for name in sorted(by_group, key=group_key):
        gfields = sorted(by_group[name], key=lambda f: (f["order"], f["label"]))
        groups.append({"title": name, "fields": gfields})

    return {"groups": groups, "constants": constants}


def all_fields(schema):
    for group in schema.get("groups", []) or []:
        for field in group.get("fields", []) or []:
            yield field


# --- dotted-path helpers (split on "." only) -------------------------------

def split_path(path):
    return path.split(".")


def get_path(data, path, default=None):
    cur = data
    for key in split_path(path):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def set_path(data, path, value):
    keys = split_path(path)
    cur = data
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[keys[-1]] = value


def prune_path(data, path):
    """Remove a leaf at `path` and any parent dicts left empty."""
    keys = split_path(path)
    stack = []
    cur = data
    for key in keys[:-1]:
        if not isinstance(cur, dict) or key not in cur:
            return
        stack.append((cur, key))
        cur = cur[key]
    if isinstance(cur, dict) and keys[-1] in cur:
        del cur[keys[-1]]
    for parent, key in reversed(stack):
        if isinstance(parent.get(key), dict) and not parent[key]:
            del parent[key]


def deep_merge(base, override):
    out = copy.deepcopy(base or {})
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


# --- form <-> values mapping -----------------------------------------------

def field_values(schema, values):
    """Current value for each schema field, for prefilling the form."""
    return {
        field["path"]: get_path(values, field["path"], field.get("default"))
        for field in all_fields(schema)
    }


def extra_yaml(schema, values):
    """Everything in `values` NOT managed by the schema, as a YAML string."""
    rest = copy.deepcopy(values or {})
    for field in all_fields(schema):
        prune_path(rest, field["path"])
    for path in (schema.get("constants") or {}):
        prune_path(rest, path)
    for path in DERIVED_NULL_PATHS:
        if get_path(rest, path, object()) is None:
            prune_path(rest, path)
    return yaml.safe_dump(rest, sort_keys=False) if rest else ""


# --- validation against the JSON schema (matches Helm) ---------------------

def validate(values):
    """Return a list of human-readable validation errors, or [] if valid."""
    raw = load_json_schema()
    if raw is None or jsonschema is None:
        return []
    validator = jsonschema.Draft7Validator(raw)
    errors = []
    for err in sorted(validator.iter_errors(values), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{loc}: {err.message}")
    return errors


def schema_issues():
    """Problems to surface on the home page: missing schema or invalid values.yaml."""
    if load_json_schema() is None:
        return [f"values.schema.json not found at {SCHEMA_JSON} — the form will be empty."]
    try:
        with open(CHART_VALUES) as fh:
            chart_values = yaml.safe_load(fh) or {}
    except OSError:
        return []
    return validate(chart_values)


if __name__ == "__main__":
    issues = schema_issues()
    if issues:
        print("Schema issues:")
        for issue in issues:
            print(f"  - {issue}")
        raise SystemExit(1)
    schema = load_schema()
    n = sum(len(g["fields"]) for g in schema["groups"])
    print(f"OK: values.schema.json valid; {n} form fields across "
          f"{len(schema['groups'])} groups, {len(schema['constants'])} constants.")
