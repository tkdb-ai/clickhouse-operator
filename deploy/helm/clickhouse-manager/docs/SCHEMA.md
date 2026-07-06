# Schema-driven form

The ClickHouse Manager form is **generated from the chart's
`values.schema.json`** — the same JSON Schema Helm uses to validate
`values.yaml`. One file is the single source of truth for both *validation* and
the *GUI*, so there is no second list to keep in sync: edit the schema and the
form updates automatically.

- Schema file: `deploy/helm/clickhouse-helm-chart/values.schema.json`
- Consumed by: `app/schema.py` (form model + validation), `app/chart.py`
  (`build_values`), and `app/templates/form.html`.

## How generation works

`app/schema.py` walks the schema's `properties` tree. A property becomes a
**friendly form field** when it carries an `x-form` keyword. `x-form` is not a
standard JSON Schema keyword, so Helm's validator ignores it — it exists purely
to describe the GUI. Everything else about the field comes from standard JSON
Schema keywords.

```
values.schema.json  ──►  schema.load_schema()  ──►  { groups:[…], constants:{…} }
                                                       │
                          form.html renders fields ◄───┘
                          chart.build_values() reads the same paths
```

Nested properties are addressed by a **dotted path** built from the property
keys, e.g. `layout.shardsCount`, `resources.limits.cpu`,
`users.default.password`. Paths are split on `.` only, so keys that contain `/`
(`users.default.networks/ip`) or `-` (`tabix-ui.enabled`) work correctly.

## Standard keywords → form behavior

| JSON Schema keyword | Effect in the form |
|---|---|
| `type: integer` / `number` | number input |
| `type: boolean` | checkbox / switch |
| `type: string` | text input |
| `enum: [...]` | dropdown (`<select>`) |
| `title` | field label (falls back to the last path segment) |
| `description` | help text under the field |
| `default` | value used for new installs and empty fields |

## The `x-form` keyword

Add `x-form` to a property to surface it as a field and control its presentation:

| `x-form` key | Type | Meaning |
|---|---|---|
| `group` | string | Section heading the field appears under (e.g. `Topology`). Defaults to `Other`. |
| `order` | number | Sort order within the group (ascending). Defaults to `999`. |
| `label` | string | Overrides `title` for the field label. |
| `widget` | string | `password` renders a masked input. Otherwise the widget is chosen from `type`/`enum`. |
| `allowEmpty` | bool | `true` = an empty value is submitted as `""` (e.g. auto-generate a password). Otherwise an empty value falls back to `default`. |
| `constant` | bool | `true` = always applied with its `default`, never shown as a field (see [Constants](#constants)). |

Group display order is `Topology → Storage & Resources → Users → Add-ons`, then
any other groups alphabetically. Change the preference list via `GROUP_ORDER` in
`app/schema.py`.

## Add a field (the whole workflow)

To expose `backup.schedule` (the backup cron) as a field:

```json
"backup": {
  "type": "object",
  "properties": {
    "schedule": {
      "type": "string",
      "title": "Backup schedule (cron)",
      "description": "Cron expression, UTC.",
      "x-form": { "group": "Add-ons", "order": 5 }
    }
  }
}
```

That single edit:

1. Makes **Helm validate** `backup.schedule` as a string.
2. Makes the **GUI render** a labelled text field in the Add-ons group.
3. Wires it into **`build_values`** and **edit-prefill** automatically.

No Python or template changes.

## Constants

Some values must always be set but should not be editable — e.g.
`users.default.networks/ip` must be `0.0.0.0/0` for the default user to connect.
Mark them `constant`:

```json
"networks/ip": {
  "type": "string",
  "default": "0.0.0.0/0",
  "x-form": { "constant": true }
}
```

`build_values` applies every constant's `default` on every submit, and they are
hidden from both the form and the Advanced box.

## The Advanced values (YAML) box

Any value **not** annotated with `x-form` can still be set per-installation via
the *Advanced values (YAML)* accordion on the form. Its contents are parsed as
YAML and **deep-merged into the values, with structured fields winning** on any
overlapping path:

```
final values = deep_merge(base = advanced_yaml, override = structured_fields)
                 + constants
                 + derived cleanup (see below)
```

On edit, the box is pre-filled with everything in the stored values that the
schema does *not* manage (schema paths and constants are pruned out), so the two
never duplicate each other.

## Validation

Validation happens in three places, all against the same `values.schema.json`:

- **In the GUI on apply** — `schema.validate(values)` (uses the `jsonschema`
  library) blocks the apply and shows the errors if the built values are invalid.
- **In Helm** — `helm template` / `helm install` validate `values.yaml` natively.
- **On the home page / CLI** — the index banner and `python app/schema.py`
  report a missing schema or a `values.yaml` that violates it.

```bash
python app/schema.py
# OK: values.schema.json valid; 17 form fields across 4 groups, 1 constants.
```

## Derived values

`build_values` injects one thing the user never types: when
`garage.enabled=false`, it sets `podTemplate.extraEnv` and
`podTemplate.extraVolumeMounts` to `null` so ClickHouse pods don't reference the
`garage-backup` secret that won't exist. These derived nulls are hidden from the
Advanced box (`DERIVED_NULL_PATHS` in `app/schema.py`).

## Gotchas

- **Free-form maps** (`settings`, `profiles`, `quotas`, `files`, extra `users`)
  are `type: object` with `additionalProperties: true` and no fixed children —
  they can't be fixed form fields. Manage them via the Advanced box.
- **Arrays** (`storage.data.accessModes`, `podTemplate.sidecars`,
  `coordination.zookeeper.nodes`) are not rendered as fields; use the Advanced
  box.
- **Only leaf scalars** with `x-form` become fields. Putting `x-form` on an
  object node has no effect unless it's a scalar.
- **`additionalProperties`** is left `true` on most objects so the existing
  `values.yaml` (and Advanced-box extras) validate. Tighten selectively if you
  want stricter validation.
