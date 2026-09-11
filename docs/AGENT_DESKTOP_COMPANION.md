# Agent desktop companion

## Retired — 2026-09-08

Removed at the user's request. The production build now has only the main window: no companion entrypoint, startup hook, settings, IPC commands, or chat activity bridge. The main-window-only command guard remains. Agent conversations and archives are unchanged. Previous implementation notes below are historical, not current capabilities. Removed sources and touched integration files are recoverable from `toujing-pet-before-removal-20260908.tar.gz` in the sibling workspace's `removal-backups` directory. Existing companion preferences are left untouched but no longer read.

## Historical implementation

The production app now includes the standalone `pet.html` Webview. Its orb visual and drag threshold reuse the earlier desktop-pet prototype; the workflow bridge is adapted to the current Agent.

- Clicking always shows/focuses the main window and resumes `/ask`, preserving its last episode query for the current account. It never creates a chat, sends a question, grants model consent or calls the model.
- The trusted main-window chat store publishes only a fixed phase enum. The pet sees reading/searching/quoting/writing/checking/completed/failed/stopped status, never account IDs, questions, answers or credentials.
- Settings control startup visibility, dragging, bubbles and reduced motion. Preferences and window position are atomically saved to `agent-companion-v1.json` in the application configuration directory. Analysis phases are memory-only and start idle after restart.
- Clicking the main close button while the companion is visible hides the main window (preserving the mounted chat); Quit exits both. Hiding the companion when the main window is hidden restores the main window.
- This does not change the existing chat lifecycle: navigating away during an unfinished answer still stops that turn. Minimize/hide does not unmount the page. Completed account answers keep the existing archive behavior.
- An application-wide invoke guard runs before every registered application command. The pet may only snapshot its preferences/status, open Agent, start native drag, and hide itself. It cannot invoke any current or future financial/runtime/Keychain command. Its core capability only permits listening/unlistening to events.
- No financial engines, Python sidecar, model client, search credentials or account archive formats are changed.

Verification: frontend lifecycle/entry/security-wiring tests, Rust command-matrix/serialization/display-clamp tests, full frontend typecheck and regression, signed bundle and native UI smoke test. Native UI acceptance should cover open from another page, repeated clicks without reset, drag versus click, hide/show, preference persistence and completion/error bubbles. Real model calls are not required to validate this shortcut.
