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

## Security Notes

- Keyboard shortcuts are restricted to an allowlist of known-safe Resolve shortcuts
- Desktop-wide screenshot capture requires `ALLOW_DESKTOP_CAPTURE=true` in environment
- All file path parameters are validated against path traversal and sensitive directory access
- The `inspect_custom_object` tool only allows read-only Resolve API methods
