# Plugin-owned BSP connector package

Implement the company GUI Test commands and hooks using the
[board connector integration workflow](agent-monitor/docs/agents/BOARD_CONNECTOR_PLUGIN_WORKFLOW.md).
It covers board ownership, flash and test execution, recovery and result reporting.

Copy this complete directory into the plugin Git repository. Do not copy runtime,
SSH keys or settings into Git. `python3 plugin.py help` needs only Python 3.11+.
For the company activation hook, use `monitor ensure --no-provision` with the
approved home, runtime and Monitor port before opening the dashboard. See
[PORT-020](agent-monitor/docs/porting/PORT-020.md) for activation and Windows forwarding.
For shared Linux installations and task-specific Monitor access, follow
[PORT-021](agent-monitor/docs/porting/PORT-021.md).
For manual observation, run `python3 plugin.py --home HOME --project KEY connect --watch --json`.
For opt-in automatic observation, register `agent-monitor/examples/activate-connector-watch.sh`
with the company's child-process supervisor. Pass the same global options. Start it asynchronously
and terminate its owned process handle on shutdown. Both entrypoints share one OS lock per endpoint.

Use [PORT-017](agent-monitor/docs/porting/PORT-017.md) for JSON status and exit codes,
official request schema and examples, prepared request replay, export paths,
module publication, mock acceptance commands/results and independent release verification.
Use [PORT-018](agent-monitor/docs/porting/PORT-018.md) for restricted-network watch,
flash confirmation, project-scoped history and signed delivery verification. The
[CLI contract](agent-monitor/contracts/plugin-cli-v1.json) and
[behavior changes](agent-monitor/contracts/plugin-behavior-changes.json) are machine-readable.
The module inventory example is `agent-monitor/examples/connector-runs/modules.json`.

Save the Windows-reachable Linux SSH endpoint once with
`connect profile --server HOST --account USER [--ssh-port PORT]`. Use the same
runtime and connector port as the activation hook. `connect export --output NEW_DIR`
copies the matching Windows GUI with the saved nonsecret bootstrap. Double-click
`start-board-connector.bat` once, and later launches reuse the matching Manager.
For manual setup, use `agent-monitor/board-connector.bat`. SSH keys and COM/device
mappings remain site prerequisites. Python
and public tools/dependencies are prepared by the existing launcher. No offline
embedded Python, driver installation or company acceptance is claimed.

Keep settings JSON outside both repositories. Use `settings export --file NEW_FILE`
and `settings import --file PATH` for a revision-checked direct settings transfer.
The service DB remains authoritative. For a clean handoff run `verify NEW_DIR --pristine`.
Use `monitor status` to compare this package,
the active installation and the running Monitor, then follow the owner-approved update
procedure if the release differs. Source ownership moves out of the company dashboard Git; map imports/service/UI clients
to this vendor package before removing duplicate source. Keep the same runtime,
service, DB and single Worker. See agent-monitor/docs/porting/PORT-011.md.

For the image flashing settings update, see agent-monitor/docs/porting/PORT-016.md.
It maps the Linux CLI, dashboard bundles and Windows connector files in this
package and describes how to check saved BAT and profile values with test preview --flash.
