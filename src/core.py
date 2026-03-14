#!/usr/bin/env python3
"""
DaVinci Resolve MCP Server
A server that connects to DaVinci Resolve via the Model Context Protocol (MCP)

Version: 1.4.0 - Modular Architecture
"""

import os
import sys
import logging

# Add src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Import platform utilities
from src.utils.platform import get_platform, get_resolve_paths

# Setup platform-specific paths and environment variables
paths = get_resolve_paths()
RESOLVE_API_PATH = paths["api_path"]
RESOLVE_LIB_PATH = paths["lib_path"]
RESOLVE_MODULES_PATH = paths["modules_path"]

os.environ["RESOLVE_SCRIPT_API"] = RESOLVE_API_PATH
os.environ["RESOLVE_SCRIPT_LIB"] = RESOLVE_LIB_PATH

# Add the module path to Python's path if it's not already there
if RESOLVE_MODULES_PATH not in sys.path:
    sys.path.append(RESOLVE_MODULES_PATH)

# Import MCP
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("davinci-resolve-mcp")

# Log server version and platform
VERSION = "1.4.0"
logger.info(f"Starting DaVinci Resolve MCP Server v{VERSION}")
logger.info(f"Detected platform: {get_platform()}")
logger.info(f"Using Resolve API path: {RESOLVE_API_PATH}")
logger.info(f"Using Resolve library path: {RESOLVE_LIB_PATH}")

# Create MCP server instance
MCP_INSTRUCTIONS = """
DaVinci Resolve MCP Server — controls DaVinci Resolve via its scripting API and keyboard simulation.

## Prerequisites
Most tools require a project to be open and a timeline to be active. Check state with
read_resolve_resource("resolve://app/state") before starting. Some tools only work on
specific pages (e.g., color tools need the Color page) — use switch_page to navigate first.

## API vs Keyboard Tools
- **API tools** (project, timeline, media, color, delivery) — direct Resolve API calls. Reliable and data-focused. Prefer these.
- **Keyboard tools** (split, trim, playback, transitions) — simulate keystrokes. Require Resolve to be the active window. Work on macOS and Windows/WSL.

## Reading Data
Use read_resolve_resource(uri) to read any resource. Use list_resolve_resources() to discover
all available URIs. Key resources:
- resolve://timeline-items — all clips with ID, name, track, start/end frame, duration
- resolve://current-timeline — current timeline info
- resolve://timeline-clips — all timeline clips with positions
- resolve://app/state — application state and connection info
- resolve://media-pool-clips — all media pool clips
- resolve://color/current-node — current color node info
- resolve://delivery/render-queue/status — render queue status

## Common Workflows
- **Split at specific points:** read_resolve_resource("resolve://timeline-items") → set_playhead_timecode → split_clip
- **Color grade:** switch_page("color") → read_resolve_resource("resolve://color/current-node") → set_color_wheel_param or apply_lut
- **Export:** add_to_render_queue → start_render → read_resolve_resource("resolve://delivery/render-queue/status")
""".strip()

mcp = FastMCP("DaVinciResolveMCP", instructions=MCP_INSTRUCTIONS)

# Initialize DaVinci Resolve connection
resolve = None
try:
    import DaVinciResolveScript as dvr_script

    resolve = dvr_script.scriptapp("Resolve")
    if resolve:
        logger.info("Successfully connected to DaVinci Resolve")
    else:
        logger.warning(
            "DaVinci Resolve is not running or the scripting API is unavailable"
        )
except ImportError as e:
    logger.error(f"Failed to import DaVinciResolveScript: {e}")
except Exception as e:
    logger.error(f"Error connecting to DaVinci Resolve: {e}")

# Bridge fallback: connect via TCP if native IPC failed
if resolve is None:
    try:
        from src.utils.resolve_bridge import ResolveBridge, ResolveProxy

        bridge = ResolveBridge.connect()
        if bridge:
            resolve = ResolveProxy(bridge, 1)
            logger.info("Connected to DaVinci Resolve via TCP bridge")
    except Exception as e:
        logger.debug(f"Bridge fallback not available: {e}")

# Register all MCP tools and resources
from src.mcp_tools import register_all_tools

register_all_tools(mcp, resolve, logger)
logger.info("All MCP tools registered successfully")


# Note: This module should be imported, not run directly.
# Use src/__main__.py as the entry point.
