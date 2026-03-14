#!/usr/bin/env python3
"""
DaVinci Resolve MCP Resource Reader Tools
Exposes MCP resources as callable tools so LLMs can discover and read them.
"""

import json


def register_resource_reader_tools(mcp, resolve, logger):
    """Register resource reader MCP tools."""

    @mcp.tool()
    async def list_resolve_resources() -> str:
        """List all available DaVinci Resolve resources and their URIs.

        Returns a list of resource URIs that can be read with read_resolve_resource.
        Use this to discover what data is available before reading specific resources.
        """
        try:
            resources = await mcp.list_resources()
            result = [
                {"uri": str(r.uri), "name": r.name, "description": r.description or ""}
                for r in resources
            ]
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error listing resources: {str(e)}"

    @mcp.tool()
    async def read_resolve_resource(resource_uri: str) -> str:
        """Read a DaVinci Resolve resource by its URI.

        Use list_resolve_resources to see available URIs, then pass one here.

        Common resources:
        - resolve://timeline-items — all clips with ID, name, track, start/end frame, duration
        - resolve://current-timeline — current timeline info
        - resolve://timeline-clips — all timeline clips
        - resolve://current-project — current project name
        - resolve://app/state — application state and connection info
        - resolve://media-pool-clips — all media pool clips
        - resolve://color/current-node — current color node info
        - resolve://delivery/render-queue/status — render queue status

        Args:
            resource_uri: The resource URI to read (e.g. "resolve://timeline-items")
        """
        try:
            results = await mcp.read_resource(resource_uri)
            contents = []
            for item in results:
                contents.append(item.content if hasattr(item, "content") else str(item))
            combined = "\n".join(str(c) for c in contents)
            return combined
        except Exception as e:
            return f"Error reading resource '{resource_uri}': {str(e)}"

    logger.info("Registered resource reader tools")
