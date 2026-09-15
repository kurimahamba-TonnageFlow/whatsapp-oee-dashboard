# Pulse HMI — Start Run Integration

No HMI/frontend source exists in this repository (confirmed by scanning the
tree). This note is for whoever maintains the HMI at
https://tonnage-flow-pulse-hmi.kurirai-mahamba.chatgpt.site so it can call
the new endpoint.

## Line / machine / button configuration (new)

```
GET {PULSE_API_BASE_URL}/api/v1/hmi/config
```

No authentication required. Returns only **active** lines → machines →
buttons - never disabled rows, Management data, or credentials:

```json
{
  "lines": [
    {
      "id": 1,
      "name": "Rovema",
      "machines": [
        {
          "id": 5,
          "name": "BV1",
          "buttons": [
            {"id": 20, "name": "Film Jam", "event_type": "unplanned_fault", "ownership": "Production", "fault_category": null},
            {"id": 21, "name": "Film Change", "event_type": "planned_downtime", "ownership": "Production", "fault_category": null}
          ]
        }
      ]
    }
  ]
}
```

`event_type` is `"planned_downtime"` or `"unplanned_fault"`;
`ownership` is `"Production"` or `"Engineering"` (matches the existing
Engineering-access split). The HMI should poll this on load and on
refresh so a button a manager just added in the new Management area
(see `docs/management_integration.md`) appears without republishing
the HMI. **Once this is wired in, remove any hard-coded machine/button
lists from the HMI's browser JavaScript** - they should come from this
endpoint only.

## Endpoint

```
POST {PULSE_API_BASE_URL}/api/v1/runs
Content-Type: application/json
```

Required environment variable on the HMI side:

```
PULSE_API_BASE_URL=https://<wherever-src/api.py-is-deployed>
```

## Request body

```json
{
  "production_line": "Rovema",
  "line_technician": "Liam",
  "shift": "Night",
  "customer": "Asda",
  "product": "Basmati",
  "pack_weight": "1kg",
  "pack_weight_kg": 1.0,
  "packs_per_case": 8,
  "pack_type": "Pillow Pack",
  "target_speed_ppm": 120,
  "cases_per_pallet": 220,
  "pallets_remaining": 38,
  "previous_run_completed": 0
}
```

Field rules:

- `production_line`, `line_technician`, `shift`, `customer`, `product`,
  `pack_weight`, `pack_type` — required, non-blank text.
- `production_line` must be one of the configured lines (currently
  `Rovema`, `GIC`, `Guill`); `line_technician` must be one of the
  technicians configured for that specific line.
  - Valid on `Rovema`, `GIC` and `Guill`: `Marina`, `Mariusz`, `Liam`,
    `Ben`, `Tomasz`, `Sumit`, `Gurpreet`, `Baljeet`, `Pali`, `Diego`,
    `Seb`, `Bupreet`. There are no line-specific restrictions - every
    technician is valid on every line.
  - Names must match this spelling and capitalisation exactly.
- `pack_weight_kg` — number, must be greater than 0.
- `packs_per_case` — integer, must be at least 1.
- `target_speed_ppm` — number, must be greater than 0.
- `cases_per_pallet` — integer, must be at least 1.
- `pallets_remaining`, `previous_run_completed` — integers, cannot be
  negative.

## Success response

`201 Created`

```json
{
  "status": "success",
  "message": "Run started",
  "run_id": 123,
  "production_line": "Rovema",
  "line_technician": "Marina",
  "pallets_remaining": 38
}
```

## Error responses

No response body ever includes database connection strings, credentials,
or raw exception text.

| Status | Meaning | Body |
| --- | --- | --- |
| `422` | A field failed validation (blank, out of range, unknown line/technician). | `{"detail": [...] }` (FastAPI's standard Pydantic validation-error shape) |
| `409` | A duplicate submission: either this line already has an active run, or a Start Run request for this line is already in flight. | `{"detail": "..."}` |
| `503` | The database could not be checked or the run could not be saved. Safe to retry. | `{"detail": "..."}` |

## Example `fetch()` call

```javascript
async function startRun(payload) {
  const response = await fetch(`${PULSE_API_BASE_URL}/api/v1/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const body = await response.json();

  if (!response.ok) {
    // body.detail describes what went wrong; never overwrite the
    // technician's entered form data on failure - let them retry.
    throw new Error(
      typeof body.detail === "string" ? body.detail : "Run could not be started."
    );
  }

  // Only now - after Supabase has confirmed the save - show
  // "✓ RUN STARTED" and store body.run_id.
  return body;
}
```

Recommended HMI button behaviour (per the connection requirements):
show a submitting state and disable the Start Run button for the
duration of the request; keep the entered form values on screen if the
request fails and offer a Retry button; only show "✓ RUN STARTED" after
this call resolves successfully; store the returned `run_id`.

## CORS

The API only allows the exact origin
`https://tonnage-flow-pulse-hmi.kurirai-mahamba.chatgpt.site` (no
wildcard). If the HMI is ever redeployed to a different origin, set the
`HMI_ORIGIN` environment variable on the API side to match, or the
browser will block the request.
