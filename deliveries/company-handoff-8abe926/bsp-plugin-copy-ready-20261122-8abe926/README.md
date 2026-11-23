# Plugin-owned BSP connector package

Copy this complete directory into the plugin Git repository. Do not copy runtime,
SSH keys or settings into Git. `python3 plugin.py help` needs only Python 3.11+.
The plugin install/activate hook calls `python3 plugin.py connect --watch` with
its persistent --home and explicit --project. JSON output is machine-readable;
installation progress goes to stderr. Closing observation does not stop work.

Windows board connector runs directly from the `agent-monitor/` directory in this
package (double-click `board-connector.bat`). `connect export --server HOST --account USER --output NEW_DIR`
copies the same version Windows GUI source directory with its nonsecret bootstrap;
double-click `start-board-connector.bat` once, and later launches reuse the matching
Manager. Initial SSH/key/COM/device mappings remain site prerequisites. Python
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
