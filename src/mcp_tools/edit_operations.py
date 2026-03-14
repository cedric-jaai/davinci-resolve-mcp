#!/usr/bin/env python3
"""
DaVinci Resolve MCP Edit Operation Tools
Split, trim, and cut clips via keyboard shortcuts (cross-platform).
"""

from src.utils.keyboard.edit import (
    edit_cut_at_playhead,
    edit_split_clip,
    edit_trim_start,
    edit_trim_end,
)


def register_edit_operation_tools(mcp, resolve, logger):
    """Register edit operation MCP tools."""

    @mcp.tool()
    def split_clip() -> str:
        """Split/razor the clip at the current playhead position (Ctrl+B / Cmd+B).

        Cuts through all clips at the playhead on the current timeline,
        similar to using the blade/razor tool in the Edit page.
        Requires DaVinci Resolve to be running with an active timeline.
        """
        if resolve is None:
            return "Error: Not connected to DaVinci Resolve"

        result = edit_cut_at_playhead()
        if result.get("success"):
            logger.info("Split clip at playhead")
            return result.get("message", "Split clip at playhead successfully")
        else:
            return f"Error: {result.get('error', 'Failed to split clip')}"

    @mcp.tool()
    def split_clip_at_position() -> str:
        """Split clip at the current playhead position using Ctrl+\\ / Cmd+\\.

        An alternative split method that splits only the selected clip
        at the playhead, rather than cutting through all tracks.
        Requires DaVinci Resolve to be running with an active timeline.
        """
        if resolve is None:
            return "Error: Not connected to DaVinci Resolve"

        result = edit_split_clip()
        if result.get("success"):
            logger.info("Split clip at position")
            return result.get("message", "Split clip at position successfully")
        else:
            return f"Error: {result.get('error', 'Failed to split clip at position')}"

    @mcp.tool()
    def trim_clip_start() -> str:
        """Trim clip start to the current playhead position (Shift+[).

        Trims the in-point of the clip under the playhead so the clip
        starts at the current playhead position.
        Requires DaVinci Resolve to be running with an active timeline.
        """
        if resolve is None:
            return "Error: Not connected to DaVinci Resolve"

        result = edit_trim_start()
        if result.get("success"):
            logger.info("Trimmed clip start to playhead")
            return result.get("message", "Trimmed clip start successfully")
        else:
            return f"Error: {result.get('error', 'Failed to trim clip start')}"

    @mcp.tool()
    def trim_clip_end() -> str:
        """Trim clip end to the current playhead position (Shift+]).

        Trims the out-point of the clip under the playhead so the clip
        ends at the current playhead position.
        Requires DaVinci Resolve to be running with an active timeline.
        """
        if resolve is None:
            return "Error: Not connected to DaVinci Resolve"

        result = edit_trim_end()
        if result.get("success"):
            logger.info("Trimmed clip end to playhead")
            return result.get("message", "Trimmed clip end successfully")
        else:
            return f"Error: {result.get('error', 'Failed to trim clip end')}"

    logger.info("Registered edit operation tools")
