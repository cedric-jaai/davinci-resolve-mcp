#!/usr/bin/env python3
"""
Path validation utility for DaVinci Resolve MCP Server.

Prevents path traversal, access to sensitive locations, and symlink attacks.
"""

import os
import platform
from typing import Optional, Set


# Sensitive directories that should never be accessed.
# On macOS, /etc -> /private/etc, /var -> /private/var, /tmp -> /private/tmp,
# so we include both forms.
_SENSITIVE_UNIX = {
    "/etc",
    "/root",
    "/var",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/sbin",
    "/usr/sbin",
    # macOS symlink targets
    "/private/etc",
    "/private/var",
}

_SENSITIVE_HOME_DIRS = {
    ".ssh",
    ".gnupg",
    ".aws",
    ".config",
    ".local/share/keyrings",
    ".bashrc",
    ".bash_profile",
    ".zshrc",
    ".profile",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".docker",
    ".kube",
}

_SENSITIVE_WINDOWS = {
    "c:\\windows",
    "c:\\windows\\system32",
    "c:\\program files",
    "c:\\program files (x86)",
    "c:\\programdata",
    "c:\\users\\default",
    "c:\\recovery",
}


def validate_path(
    path: str,
    allowed_extensions: Optional[Set[str]] = None,
    must_exist: bool = False,
) -> str:
    """Validate a filesystem path for safety.

    Args:
        path: The path to validate.
        allowed_extensions: If provided, only these file extensions are allowed
                           (e.g., {'.mp4', '.mov', '.mxf'}). Include the dot.
        must_exist: If True, the path must exist on the filesystem.

    Returns:
        The resolved, validated path.

    Raises:
        ValueError: If the path is invalid, dangerous, or disallowed.
    """
    if not path or not isinstance(path, str):
        raise ValueError("Path must be a non-empty string")

    # Resolve to absolute, canonical path (resolves symlinks)
    resolved = os.path.realpath(os.path.expanduser(path))

    # Block path traversal: check if the original path tried to escape
    # via ".." after normalization
    normalized = os.path.normpath(path)
    if ".." in normalized.split(os.sep):
        raise ValueError("Path traversal ('..') is not allowed")

    # Check for sensitive Unix locations.
    # We check both the resolved path and the normalized original path,
    # because on macOS /etc resolves to /private/etc via symlink.
    if platform.system() != "Windows":
        paths_to_check = {resolved.lower(), os.path.abspath(os.path.expanduser(path)).lower()}
        for check_path in paths_to_check:
            for sensitive in _SENSITIVE_UNIX:
                if check_path == sensitive or check_path.startswith(sensitive + "/"):
                    raise ValueError(
                        f"Access to sensitive system directory is not allowed: {sensitive}"
                    )

        # Check home directory sensitive subdirs
        home = os.path.expanduser("~")
        if home:
            for subdir in _SENSITIVE_HOME_DIRS:
                sensitive_path = os.path.join(home, subdir)
                if resolved == sensitive_path or resolved.startswith(
                    sensitive_path + os.sep
                ):
                    raise ValueError(
                        f"Access to sensitive home directory is not allowed: ~/{subdir}"
                    )

    # Check for sensitive Windows locations
    if platform.system() == "Windows" or _is_wsl_path(resolved):
        check_path = resolved.lower().replace("/", "\\")
        for sensitive in _SENSITIVE_WINDOWS:
            if check_path == sensitive or check_path.startswith(sensitive + "\\"):
                raise ValueError(
                    f"Access to sensitive system directory is not allowed"
                )

    # Validate file extension if allowlist provided
    if allowed_extensions is not None:
        _, ext = os.path.splitext(resolved)
        if ext.lower() not in {e.lower() for e in allowed_extensions}:
            raise ValueError(
                f"File extension '{ext}' is not allowed. "
                f"Allowed: {', '.join(sorted(allowed_extensions))}"
            )

    # Check existence if required
    if must_exist and not os.path.exists(resolved):
        raise ValueError(f"Path does not exist: {resolved}")

    return resolved


def _is_wsl_path(path: str) -> bool:
    """Check if a path looks like a WSL-translated Windows path."""
    return path.startswith("/mnt/c/") or path.startswith("/mnt/d/")


# Common media extensions for import validation
MEDIA_EXTENSIONS = {
    # Video
    ".mp4", ".mov", ".avi", ".mkv", ".mxf", ".r3d", ".braw",
    ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".ts",
    ".dng", ".crm", ".ari",
    # Audio
    ".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a", ".aif", ".aiff",
    # Image
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".exr",
    ".dpx", ".cin", ".psd", ".gif", ".webp",
}

# LUT extensions
LUT_EXTENSIONS = {
    ".cube", ".3dl", ".csp", ".lut", ".mga", ".m3d",
    ".cdl", ".cc", ".ccc", ".olut",
}

# Project file extensions
PROJECT_EXTENSIONS = {
    ".drp", ".dra",
}

# Timeline import/export extensions
TIMELINE_EXTENSIONS = {
    ".aaf", ".edl", ".xml", ".fcpxml", ".drt", ".adl", ".otio",
}

# Still/image extensions for gallery operations
STILL_EXTENSIONS = {
    ".dpx", ".cin", ".tif", ".tiff", ".jpg", ".jpeg",
    ".png", ".ppm", ".bmp", ".xpm", ".drx", ".exr",
}

# Layout preset extensions
LAYOUT_EXTENSIONS = {
    ".preset", ".json", ".xml",
}
