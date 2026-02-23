"""Utility tools for DaVinci Resolve MCP Server."""

from typing import Dict, Any


def register_utility_tools(mcp):
    """Register utility tools with the MCP server."""
    from src.utils.keyboard import send_custom_key, get_keyboard_shortcuts

    @mcp.tool()
    def send_keyboard_shortcut(key: str, description: str = "") -> Dict[str, Any]:
        """
        Send a keyboard shortcut to DaVinci Resolve.

        Only allowlisted shortcuts are accepted. Dangerous combos like
        Alt+F4 (close application) are blocked. The Alt (%) modifier is
        restricted to known Resolve shortcuts (e.g., %s for Add Serial Node).

        Args:
            key: The key in SendKeys format:
                - Regular keys: 'a', 'b', '1', etc.
                - Special keys: {ENTER}, {TAB}, {ESC}, {BACKSPACE}, {DELETE}
                - Arrow keys: {LEFT}, {RIGHT}, {UP}, {DOWN}
                - Function keys: {F1} through {F12}
                - Modifiers: ^ for Ctrl, + for Shift, % for Alt (restricted)
                - Examples: '^s' (Ctrl+S), '+{F10}' (Shift+F10)
            description: Optional description of the action

        Returns:
            Dict with success status and message
        """
        return send_custom_key(key, description)

    @mcp.resource("resolve://keyboard/shortcuts")
    def list_keyboard_shortcuts() -> Dict[str, str]:
        """Get a comprehensive list of DaVinci Resolve keyboard shortcuts."""
        return get_keyboard_shortcuts()
