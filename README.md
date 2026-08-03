# BUSY Bar for Microsoft Teams

This local Python app gives a BUSY Bar two complementary signals:

- The next Microsoft Teams calendar meeting is shown as an hours countdown.
- The red **ON CALL** screen follows live Teams presence, so it starts when you
  actually join a call and remains active when a meeting overruns.

`InAMeeting` is intentionally not treated as a call because Teams derives that
state from the calendar. The app uses the live `InACall`, `InAConferenceCall`,
and `Presenting` activities instead. Unscheduled Teams calls are covered too.

## Requirements

- A BUSY Bar reachable over USB (`10.0.4.20`) or Wi-Fi
- BUSY Bar firmware compatible with `busylib` API 25.0.0
- `uv`
- A Microsoft 365 work or school account
- A Microsoft Entra app registration

## 1. Register the Microsoft app

In the [Microsoft Entra admin center](https://entra.microsoft.com/):

1. Create an **App registration** and copy its **Application (client) ID**.
2. Under **Authentication**, enable **Allow public client flows**.
3. Under **API permissions**, add these delegated Microsoft Graph permissions:
   - `Calendars.Read`
   - `Presence.Read`
4. Grant consent if your organization requires admin consent.

Use your directory/tenant ID for a single-tenant registration. The default
tenant value, `organizations`, is convenient for a multi-tenant registration.

## 2. Configure the app

The app first looks for `config.toml` in the current directory, then falls back
to `~/.config/busybar-msteams/config.toml`. Start with
[config.example.toml](config.example.toml):

```bash
cp config.example.toml config.toml
```

For a user-level configuration that works from any directory instead:

```bash
mkdir -p ~/.config/busybar-msteams
cp config.example.toml ~/.config/busybar-msteams/config.toml
```

At minimum, replace `microsoft.client_id`. For example:

```toml
[microsoft]
client_id = "your-application-client-id"
tenant_id = "your-tenant-id"

[busybar]
# Omit this to select the only discovered bar automatically.
name = "Office BUSY Bar"

[polling]
presence_seconds = 20.0
calendar_seconds = 300.0
lookahead_days = 7
```

Use a different file with `--config ./config.toml` or the
`BUSYBAR_MSTEAMS_CONFIG` environment variable. Precedence is command-line
option, environment variable, config file, then built-in default. Unknown TOML
sections and keys are rejected so configuration typos are visible.

The BUSY Bar PIN can be written as `busybar.token`, but `BUSYBAR_TOKEN` is
recommended so the PIN is not stored as plain text.

## 3. Install and run with uv

```bash
uv sync
uv run busybar-msteams
```

The app uses `BusyBarDevices.discover()` to find the bar. It automatically uses
the only discovered device; when it finds several, it displays a selection
menu. For an unattended launch with several bars, select one by its configured
name:

```bash
export BUSYBAR_NAME="Office BUSY Bar"
```

Wi-Fi is preferred when a discovered device has both addresses. If mDNS finds
nothing, the app tries the well-known USB address `10.0.4.20`, because some
shipped firmware versions do not advertise the BUSY Bar service yet. You can
always bypass discovery with `BUSYBAR_HOST` or `--device`.

The first run prints a Microsoft device-login URL and code. After sign-in, MSAL
stores a refresh-token cache at
`~/.local/state/busybar-msteams/msal-token-cache.json` with mode `0600`.
Subsequent starts are unattended.

If the BUSY Bar is on Wi-Fi and has an access PIN, also set:

```bash
export BUSYBAR_TOKEN="1234"
```

If the selected bar requires a PIN and none is configured, the app securely
prompts for it at startup. The value is used for that run only and is not saved.

## Screen behavior

| Teams state | Front display | Meaning |
| --- | --- | --- |
| Live call or presenting | `ON CALL` in red | Do not disturb |
| Calendar meeting underway, not in a call | `JOIN?` in amber | Scheduled, but not connected |
| Future Teams meeting | `NEXT 1.3h` in blue | Hours until start |
| No Teams meetings in the next 7 days | `NO CALLS` | Idle |

Presence is checked every 20 seconds and the calendar every five minutes. A
transient Graph failure never clears an existing on-call state; the app waits
for a positive non-call presence update. Microsoft Graph `429` responses honor
the service's `Retry-After` value.

Useful commands:

```bash
# Authenticate and preview the exact device payload without touching BUSY Bar
uv run busybar-msteams --dry-run

# Draw once, useful while testing a physical device
uv run busybar-msteams --once

# See all device, polling, cache, and logging options
uv run busybar-msteams --help
```

By default, stopping with Ctrl+C clears only this app's BUSY Bar display. Pass
`--no-clear` to leave its last screen visible.

## Development

```bash
uv run pytest
uv run ruff check .
```

No Microsoft or BUSY Bar credentials are required for the unit tests.
