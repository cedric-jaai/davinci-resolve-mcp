# DaVinci Resolve MCP Server

An MCP (Model Context Protocol) server for controlling DaVinci Resolve via its scripting API and keyboard simulation.

## Project Structure

- `src/` - Main source code
  - `api/` - DaVinci Resolve API wrappers
  - `mcp_tools/` - MCP tool registration modules
  - `tools/` - Tool registration and keyboard/capture tools
  - `utils/` - Utilities (keyboard control, capture, path validation)
- `tests/` - Test suite
- `requirements.txt` - Production dependencies (pinned)
- `requirements-dev.txt` - Development/testing dependencies

## Tooling

- Use `uv` for all Python package management (install, run, sync). Do NOT use pip.
- Run tests with: `uv run pytest`
- Install deps with: `uv pip install -r requirements.txt` or `uv sync`

## TCP Bridge

When native IPC is blocked (e.g. by endpoint security on managed macOS), the server falls back to a TCP bridge:
- Lua server: `src/utils/resolve_bridge_server.lua` — run via `dofile()` in Resolve's Fusion Console
- Python client: `src/utils/resolve_bridge.py` — `ResolveBridge` (TCP client) + `ResolveProxy` (transparent proxy)
- Fallback logic in `src/core.py` (lines 73-83): tries bridge when `scriptapp()` returns `None`
- Protocol: localhost:9876, 4-byte BE length-prefixed JSON, object registry with ID-based references

## Security Notes

- Keyboard shortcuts are restricted to an allowlist of known-safe Resolve shortcuts
- Desktop-wide screenshot capture requires `ALLOW_DESKTOP_CAPTURE=true` in environment
- All file path parameters are validated against path traversal and sensitive directory access
- The `inspect_custom_object` tool only allows read-only Resolve API methods
