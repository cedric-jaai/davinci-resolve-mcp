#!/usr/bin/env python3
"""
DaVinci Resolve MCP Object Inspection Tools
Inspect API objects and get help on their methods
"""

from typing import Dict, Any

from src.utils.object_inspection import (
    inspect_object,
    print_object_help,
)

# Allowlist of safe Resolve API methods that can be called via inspect_custom_object.
# Only read-only / getter methods are included. Destructive methods (Delete*, Set*,
# Save*, Import*, Export*, etc.) are intentionally excluded.
ALLOWED_METHODS = {
    # Resolve top-level
    "GetProjectManager",
    "GetMediaStorage",
    "GetProductName",
    "GetVersion",
    "GetVersionString",
    # ProjectManager
    "GetCurrentProject",
    "GetCurrentDatabase",
    "GetDatabaseList",
    # Project
    "GetCurrentTimeline",
    "GetMediaPool",
    "GetGallery",
    "GetName",
    "GetTimelineCount",
    "GetCurrentRenderFormatAndCodec",
    "GetCurrentRenderMode",
    "GetRenderFormats",
    "GetRenderCodecs",
    "GetRenderPresets",
    "GetRenderPresetList",
    "GetRenderJobList",
    "GetRenderJobStatus",
    "GetSetting",
    "GetTimelineByIndex",
    "GetCurrentRenderFormatAndCodec",
    "IsRenderingInProgress",
    # Timeline
    "GetCurrentVideoItem",
    "GetCurrentClipThumbnailImage",
    "GetTrackCount",
    "GetItemListInTrack",
    "GetMarkers",
    "GetStartFrame",
    "GetEndFrame",
    "GetStartTimecode",
    "GetTrackName",
    # MediaPool
    "GetRootFolder",
    "GetCurrentFolder",
    # MediaPool Folder
    "GetClipList",
    "GetSubFolderList",
    "GetIsFolderStale",
    # MediaPool Item / Clip
    "GetClipProperty",
    "GetDuration",
    "GetAudioMapping",
    "GetMetadata",
    "GetUniqueId",
    # MediaStorage
    "GetMountedVolumeList",
    "GetSubFolderList",
    "GetFileList",
    # Gallery
    "GetCurrentStillAlbum",
    "GetGalleryStillAlbums",
    # Timeline Item
    "GetStart",
    "GetEnd",
    "GetLeftOffset",
    "GetRightOffset",
    "GetFusionCompCount",
    "GetFusionCompByIndex",
    "GetFusionCompNameList",
    "GetMediaPoolItem",
    "GetNodeGraph",
}


def register_inspection_tools(mcp, resolve, logger):
    """Register object inspection MCP tools and resources."""

    @mcp.resource("resolve://inspect/resolve")
    def inspect_resolve_object() -> Dict[str, Any]:
        """Inspect the main resolve object and return its methods and properties."""
        if resolve is None:
            return {"error": "Not connected to DaVinci Resolve"}

        return inspect_object(resolve)

    @mcp.resource("resolve://inspect/project-manager")
    def inspect_project_manager_object() -> Dict[str, Any]:
        """Inspect the project manager object and return its methods and properties."""
        if resolve is None:
            return {"error": "Not connected to DaVinci Resolve"}

        project_manager = resolve.GetProjectManager()
        if not project_manager:
            return {"error": "Failed to get Project Manager"}

        return inspect_object(project_manager)

    @mcp.resource("resolve://inspect/current-project")
    def inspect_current_project_object() -> Dict[str, Any]:
        """Inspect the current project object and return its methods and properties."""
        if resolve is None:
            return {"error": "Not connected to DaVinci Resolve"}

        project_manager = resolve.GetProjectManager()
        if not project_manager:
            return {"error": "Failed to get Project Manager"}

        current_project = project_manager.GetCurrentProject()
        if not current_project:
            return {"error": "No project currently open"}

        return inspect_object(current_project)

    @mcp.resource("resolve://inspect/media-pool")
    def inspect_media_pool_object() -> Dict[str, Any]:
        """Inspect the media pool object and return its methods and properties."""
        if resolve is None:
            return {"error": "Not connected to DaVinci Resolve"}

        project_manager = resolve.GetProjectManager()
        if not project_manager:
            return {"error": "Failed to get Project Manager"}

        current_project = project_manager.GetCurrentProject()
        if not current_project:
            return {"error": "No project currently open"}

        media_pool = current_project.GetMediaPool()
        if not media_pool:
            return {"error": "Failed to get Media Pool"}

        return inspect_object(media_pool)

    @mcp.resource("resolve://inspect/current-timeline")
    def inspect_current_timeline_object() -> Dict[str, Any]:
        """Inspect the current timeline object and return its methods and properties."""
        if resolve is None:
            return {"error": "Not connected to DaVinci Resolve"}

        project_manager = resolve.GetProjectManager()
        if not project_manager:
            return {"error": "Failed to get Project Manager"}

        current_project = project_manager.GetCurrentProject()
        if not current_project:
            return {"error": "No project currently open"}

        current_timeline = current_project.GetCurrentTimeline()
        if not current_timeline:
            return {"error": "No timeline currently active"}

        return inspect_object(current_timeline)

    @mcp.tool()
    def object_help(object_type: str) -> str:
        """Get human-readable help for a DaVinci Resolve API object.

        Args:
            object_type: Type of object to get help for ('resolve', 'project_manager',
                         'project', 'media_pool', 'timeline', 'media_storage')
        """
        if resolve is None:
            return "Error: Not connected to DaVinci Resolve"

        obj = None

        if object_type == "resolve":
            obj = resolve
        elif object_type == "project_manager":
            obj = resolve.GetProjectManager()
        elif object_type == "project":
            pm = resolve.GetProjectManager()
            if pm:
                obj = pm.GetCurrentProject()
        elif object_type == "media_pool":
            pm = resolve.GetProjectManager()
            if pm:
                project = pm.GetCurrentProject()
                if project:
                    obj = project.GetMediaPool()
        elif object_type == "timeline":
            pm = resolve.GetProjectManager()
            if pm:
                project = pm.GetCurrentProject()
                if project:
                    obj = project.GetCurrentTimeline()
        elif object_type == "media_storage":
            obj = resolve.GetMediaStorage()
        else:
            return f"Error: Unknown object type '{object_type}'"

        if obj is None:
            return f"Error: Failed to get {object_type} object"

        return print_object_help(obj)

    @mcp.tool()
    def inspect_custom_object(object_path: str) -> Dict[str, Any]:
        """Inspect a custom DaVinci Resolve API object by path.

        Only allowlisted read-only methods can be traversed. Dunder methods
        and destructive operations (Delete, Set, Save, etc.) are blocked.

        Args:
            object_path: Path to the object using dot notation
                         (e.g., 'resolve.GetMediaStorage()')
        """
        if resolve is None:
            return {"error": "Not connected to DaVinci Resolve"}

        try:
            obj = resolve

            parts = object_path.split(".")

            start_index = 1 if parts[0].lower() == "resolve" else 0

            for i in range(start_index, len(parts)):
                part = parts[i]

                if part.endswith("()"):
                    method_name = part[:-2]

                    # Block dunder methods
                    if method_name.startswith("__"):
                        return {"error": f"Access to dunder methods is not allowed: '{method_name}'"}

                    # Check allowlist
                    if method_name not in ALLOWED_METHODS:
                        return {
                            "error": f"Method '{method_name}' is not in the allowed methods list. "
                            "Only read-only Resolve API methods are permitted."
                        }

                    if hasattr(obj, method_name) and callable(
                        getattr(obj, method_name)
                    ):
                        obj = getattr(obj, method_name)()
                    else:
                        return {
                            "error": f"Method '{method_name}' not found or not callable"
                        }
                else:
                    # Block dunder attributes
                    if part.startswith("__"):
                        return {"error": f"Access to dunder attributes is not allowed: '{part}'"}

                    if hasattr(obj, part):
                        obj = getattr(obj, part)
                    else:
                        return {"error": f"Attribute '{part}' not found"}

            return inspect_object(obj)
        except Exception as e:
            return {"error": f"Error inspecting object: {str(e)}"}

    logger.info("Registered inspection tools")
