"""
Screenshot Capture Utilities for DaVinci Resolve MCP Server.

Provides portable screenshot functionality for AI agents to "see" DaVinci Resolve.
Optimized for WSL-to-Windows capture. Lightweight, standalone implementation.
"""

import os
import sys
import subprocess
import base64
from datetime import datetime
from typing import Optional, Dict, Any

# Default output directory
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.scitex/capture")


def is_wsl() -> bool:
    """Check if running in WSL."""
    return sys.platform == "linux" and "microsoft" in os.uname().release.lower()


def is_windows() -> bool:
    """Check if running on Windows (native or via WSL bridge)."""
    return sys.platform == "win32"


def is_macos() -> bool:
    """Check if running on macOS."""
    return sys.platform == "darwin"


def find_powershell() -> Optional[str]:
    """Find PowerShell executable."""
    if is_windows():
        # On Windows, PowerShell is in PATH
        ps_paths = [
            "powershell.exe",
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        ]
    else:
        # On WSL, use the Windows paths via /mnt/c
        ps_paths = [
            "powershell.exe",
            "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "/mnt/c/Windows/SysWOW64/WindowsPowerShell/v1.0/powershell.exe",
        ]

    for path in ps_paths:
        try:
            result = subprocess.run(
                [path, "-Command", "echo test"],
                capture_output=True,
                timeout=2,
            )
            if result.returncode == 0:
                return path
        except Exception:
            continue
    return None


def _run_powershell(script: str, timeout: int = 10) -> tuple:
    """Run PowerShell script and return (success, output, error)."""
    ps_exe = find_powershell()
    if not ps_exe:
        return False, None, "PowerShell not found"

    try:
        result = subprocess.run(
            [ps_exe, "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, result.stdout.strip(), None
        return False, None, result.stderr or "Command failed"
    except subprocess.TimeoutExpired:
        return False, None, "Timeout"
    except Exception as e:
        return False, None, str(e)


def _save_image(png_data: bytes, output_path: str, quality: int) -> str:
    """Save PNG data to file, converting to JPEG if PIL available."""
    try:
        import io
        from PIL import Image

        img = Image.open(io.BytesIO(png_data))
        if img.mode == "RGBA":
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[3])
            img = rgb_img
        img.save(output_path, "JPEG", quality=quality, optimize=True)
        return output_path
    except ImportError:
        output_path = output_path.replace(".jpg", ".png")
        with open(output_path, "wb") as f:
            f.write(png_data)
        return output_path


def _run_swift(script: str, timeout: int = 15) -> tuple:
    """Run a Swift script and return (success, output, error)."""
    try:
        result = subprocess.run(
            ["swift", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, result.stdout.strip(), None
        return False, None, result.stderr.strip() or "Command failed"
    except subprocess.TimeoutExpired:
        return False, None, "Timeout"
    except FileNotFoundError:
        return False, None, "Swift not found"
    except Exception as e:
        return False, None, str(e)


def _macos_list_windows() -> Dict[str, Any]:
    """List visible windows on macOS using CoreGraphics via Swift."""
    swift_script = """
import CoreGraphics
import Foundation

let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
guard let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
    print("[]")
    exit(0)
}

var results: [[String: Any]] = []
for window in windowList {
    let ownerName = window[kCGWindowOwnerName as String] as? String ?? ""
    let windowName = window[kCGWindowName as String] as? String ?? ""
    let windowNumber = window[kCGWindowNumber as String] as? Int ?? 0
    let ownerPID = window[kCGWindowOwnerPID as String] as? Int ?? 0
    let layer = window[kCGWindowLayer as String] as? Int ?? 0
    if layer == 0 && (ownerName.count > 0 || windowName.count > 0) {
        results.append([
            "Handle": windowNumber,
            "Title": windowName,
            "ProcessName": ownerName,
            "PID": ownerPID
        ])
    }
}

if let data = try? JSONSerialization.data(withJSONObject: results, options: []),
   let json = String(data: data, encoding: .utf8) {
    print(json)
}
"""
    success, output, error = _run_swift(swift_script)
    if not success:
        # Fallback: use pgrep to at least detect running processes
        return _macos_list_windows_fallback()

    import json

    try:
        windows = json.loads(output)
    except json.JSONDecodeError:
        return _macos_list_windows_fallback()

    if isinstance(windows, dict):
        windows = [windows]
    return {"success": True, "windows": windows}


def _macos_list_windows_fallback() -> Dict[str, Any]:
    """Fallback window listing using pgrep when CoreGraphics is unavailable."""
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of every process whose visible is true'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            names = [n.strip() for n in result.stdout.strip().split(",")]
            windows = [{"Handle": 0, "Title": "", "ProcessName": n} for n in names]
            return {"success": True, "windows": windows}
    except Exception:
        pass
    return {"success": False, "error": "Could not list windows on macOS"}


def _macos_capture_window(
    window_id: int,
    output_path: str = None,
    quality: int = 85,
    return_base64: bool = False,
) -> Dict[str, Any]:
    """Capture a specific window on macOS using screencapture."""
    import tempfile

    if window_id == 0:
        return {
            "success": False,
            "error": "Window ID unavailable. Grant Screen Recording permission in "
                     "System Settings > Privacy & Security > Screen Recording for the "
                     "app running this MCP server, then restart it.",
        }

    tmp_path = None
    try:
        if return_base64:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_path = tmp.name
            tmp.close()
            capture_path = tmp_path
        else:
            if output_path is None:
                os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"{DEFAULT_OUTPUT_DIR}/window_{window_id}_{timestamp}.png"
            capture_path = output_path

        result = subprocess.run(
            ["screencapture", "-l", str(window_id), "-x", "-o", capture_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else ""
            if "could not create image" in error_msg.lower() or not error_msg:
                return {
                    "success": False,
                    "error": "Screen capture failed. Grant Screen Recording permission in "
                             "System Settings > Privacy & Security > Screen Recording for the "
                             "app running this MCP server, then restart it.",
                }
            return {"success": False, "error": error_msg}

        # Verify the file was actually created with content
        if not os.path.exists(capture_path) or os.path.getsize(capture_path) == 0:
            return {
                "success": False,
                "error": "Screen capture produced empty output. Grant Screen Recording permission in "
                         "System Settings > Privacy & Security > Screen Recording for the "
                         "app running this MCP server, then restart it.",
            }

        if return_base64:
            with open(capture_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            return {"success": True, "base64": data, "format": "png"}

        return {"success": True, "path": output_path}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path) and return_base64:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _macos_capture_screenshot(
    output_path: str = None,
    quality: int = 85,
    monitor_id: int = 0,
    capture_all: bool = False,
    return_base64: bool = False,
) -> Dict[str, Any]:
    """Take a screenshot on macOS using screencapture."""
    import tempfile

    tmp_path = None
    try:
        if return_base64:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_path = tmp.name
            tmp.close()
            capture_path = tmp_path
        else:
            if output_path is None:
                os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"{DEFAULT_OUTPUT_DIR}/screenshot_{timestamp}.png"
            capture_path = output_path

        cmd = ["screencapture", "-x"]
        if not capture_all:
            # -D flag selects display (1-based index on macOS)
            cmd.extend(["-D", str(monitor_id + 1)])
        cmd.append(capture_path)

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else ""
            if "could not create image" in error_msg.lower() or not error_msg:
                return {
                    "success": False,
                    "error": "Screen capture failed. Grant Screen Recording permission in "
                             "System Settings > Privacy & Security > Screen Recording for the "
                             "app running this MCP server, then restart it.",
                }
            return {"success": False, "error": error_msg}

        if not os.path.exists(capture_path) or os.path.getsize(capture_path) == 0:
            return {
                "success": False,
                "error": "Screen capture produced empty output. Grant Screen Recording permission in "
                         "System Settings > Privacy & Security > Screen Recording for the "
                         "app running this MCP server, then restart it.",
            }

        if return_base64:
            with open(capture_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            return {"success": True, "base64": data, "format": "png"}

        return {"success": True, "path": output_path}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path) and return_base64:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _macos_get_monitor_info() -> Dict[str, Any]:
    """Get monitor info on macOS via JXA."""
    script = """
ObjC.import('Cocoa');
var screens = $.NSScreen.screens;
var monitors = [];
for (var i = 0; i < screens.count; i++) {
    var s = screens.objectAtIndex(i);
    var frame = s.frame;
    monitors.push({
        Index: i,
        DeviceName: ObjC.unwrap(s.localizedName),
        Primary: i === 0,
        Width: frame.size.width,
        Height: frame.size.height,
        X: frame.origin.x,
        Y: frame.origin.y
    });
}
JSON.stringify({Monitors: monitors, Count: monitors.length});
"""
    success, output, error = _run_osascript_jxa(script)
    if not success:
        return {"success": False, "error": error}

    import json

    return {"success": True, **json.loads(output)}


def capture_screenshot(
    output_path: str = None,
    quality: int = 85,
    monitor_id: int = 0,
    capture_all: bool = False,
    return_base64: bool = False,
) -> Dict[str, Any]:
    """
    Take a screenshot of the Windows desktop from WSL.

    Args:
        output_path: Path to save screenshot (auto-generated if None)
        quality: JPEG quality (1-100)
        monitor_id: Monitor index (0-based)
        capture_all: Capture all monitors combined
        return_base64: Return image as base64 string instead of saving

    Returns:
        Dict with 'success', 'path' or 'base64', and optional 'error'
    """
    if is_macos():
        return _macos_capture_screenshot(output_path, quality, monitor_id, capture_all, return_base64)

    if not (is_wsl() or is_windows()):
        return {"success": False, "error": "Not running on Windows, WSL, or macOS"}

    # Build capture script
    ps_script = """
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Add-Type @'
    using System;
    using System.Runtime.InteropServices;
    public class User32 { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }
'@
    $null = [User32]::SetProcessDPIAware()
    $screens = [System.Windows.Forms.Screen]::AllScreens
    """

    if capture_all:
        ps_script += """
    $minX = ($screens | ForEach-Object { $_.Bounds.X } | Measure-Object -Minimum).Minimum
    $minY = ($screens | ForEach-Object { $_.Bounds.Y } | Measure-Object -Minimum).Minimum
    $maxX = ($screens | ForEach-Object { $_.Bounds.X + $_.Bounds.Width } | Measure-Object -Maximum).Maximum
    $maxY = ($screens | ForEach-Object { $_.Bounds.Y + $_.Bounds.Height } | Measure-Object -Maximum).Maximum
    $bitmap = New-Object System.Drawing.Bitmap ($maxX - $minX), ($maxY - $minY)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($minX, $minY, 0, 0, [System.Drawing.Size]::new(($maxX - $minX), ($maxY - $minY)))
    """
    else:
        ps_script += f"""
    $idx = {monitor_id}; if ($idx -ge $screens.Count) {{ $idx = 0 }}
    $screen = $screens[$idx]
    $bitmap = New-Object System.Drawing.Bitmap $screen.Bounds.Width, $screen.Bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($screen.Bounds.X, $screen.Bounds.Y, 0, 0, $bitmap.Size)
    """

    ps_script += """
    $stream = New-Object System.IO.MemoryStream
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    [Convert]::ToBase64String($stream.ToArray())
    $graphics.Dispose(); $bitmap.Dispose(); $stream.Dispose()
    """

    success, output, error = _run_powershell(ps_script)
    if not success:
        return {"success": False, "error": error}

    if return_base64:
        return {"success": True, "base64": output, "format": "png"}

    png_data = base64.b64decode(output)

    if output_path is None:
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{DEFAULT_OUTPUT_DIR}/screenshot_{timestamp}.jpg"

    saved_path = _save_image(png_data, output_path, quality)
    return {"success": True, "path": saved_path}


def list_windows() -> Dict[str, Any]:
    """List all visible windows with their handles."""
    if is_macos():
        return _macos_list_windows()

    if not (is_wsl() or is_windows()):
        return {"success": False, "error": "Not running on Windows, WSL, or macOS"}

    ps_script = """
    Add-Type @'
    using System; using System.Runtime.InteropServices; using System.Text; using System.Collections.Generic;
    public class WinEnum {
        [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
        [DllImport("user32.dll")] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
        [DllImport("user32.dll")] static extern int GetWindowTextLength(IntPtr h);
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
        public delegate bool EnumProc(IntPtr h, IntPtr l);
        [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc e, IntPtr l);
        public static List<object[]> Get() {
            var w = new List<object[]>();
            EnumWindows((h, l) => {
                if (IsWindowVisible(h)) { int len = GetWindowTextLength(h);
                    if (len > 0) { var sb = new StringBuilder(len + 1); GetWindowText(h, sb, sb.Capacity);
                        uint p; GetWindowThreadProcessId(h, out p); w.Add(new object[] { h.ToInt64(), sb.ToString(), p }); }
                } return true; }, IntPtr.Zero);
            return w; } }
'@
    $r = @(); foreach ($w in [WinEnum]::Get()) {
        $p = Get-Process -Id $w[2] -ErrorAction SilentlyContinue
        $r += @{ Handle = $w[0]; Title = $w[1]; ProcessName = if ($p) { $p.ProcessName } else { "Unknown" } }
    }; $r | ConvertTo-Json -Compress
    """

    success, output, error = _run_powershell(ps_script)
    if not success:
        return {"success": False, "error": error}

    import json

    windows = json.loads(output)
    if isinstance(windows, dict):
        windows = [windows]
    return {"success": True, "windows": windows}


def capture_window(
    window_handle: int,
    output_path: str = None,
    quality: int = 85,
    return_base64: bool = False,
) -> Dict[str, Any]:
    """Capture a specific window by its handle."""
    if is_macos():
        return _macos_capture_window(window_handle, output_path, quality, return_base64)

    if not (is_wsl() or is_windows()):
        return {"success": False, "error": "Not running on Windows, WSL, or macOS"}

    ps_script = f"""
    Add-Type -AssemblyName System.Drawing
    Add-Type -ReferencedAssemblies System.Drawing @'
    using System; using System.Drawing; using System.Runtime.InteropServices;
    public class WinCap {{
        [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
        [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
        [StructLayout(LayoutKind.Sequential)] public struct RECT {{ public int L, T, R, B; }}
        public static Bitmap Cap(IntPtr h) {{ SetProcessDPIAware(); RECT r; GetWindowRect(h, out r);
            int w = r.R - r.L, ht = r.B - r.T; if (w <= 0 || ht <= 0) return null;
            var b = new Bitmap(w, ht); using (var g = Graphics.FromImage(b)) {{ g.CopyFromScreen(r.L, r.T, 0, 0, new Size(w, ht)); }}
            return b; }} }}
'@
    $b = [WinCap]::Cap([IntPtr]{window_handle}); if ($b -eq $null) {{ exit 1 }}
    $s = New-Object System.IO.MemoryStream; $b.Save($s, [System.Drawing.Imaging.ImageFormat]::Png)
    [Convert]::ToBase64String($s.ToArray()); $b.Dispose(); $s.Dispose()
    """

    success, output, error = _run_powershell(ps_script)
    if not success:
        return {"success": False, "error": error or "Window capture failed"}

    if return_base64:
        return {"success": True, "base64": output, "format": "png"}

    png_data = base64.b64decode(output)

    if output_path is None:
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{DEFAULT_OUTPUT_DIR}/window_{window_handle}_{timestamp}.jpg"

    saved_path = _save_image(png_data, output_path, quality)
    return {"success": True, "path": saved_path}


def find_resolve_window() -> Optional[Dict[str, Any]]:
    """Find DaVinci Resolve window handle."""
    result = list_windows()
    if not result.get("success"):
        return None

    # First pass: match by process name (most reliable)
    for window in result.get("windows", []):
        process = window.get("ProcessName", "").lower()
        if process == "resolve" or "davinci resolve" in process:
            return window

    # Second pass: match by window title (fallback)
    for window in result.get("windows", []):
        title = window.get("Title", "").lower()
        process = window.get("ProcessName", "").lower()
        # Only match title if the process isn't a browser or other unrelated app
        if "davinci resolve" in title and process not in (
            "firefox", "chrome", "safari", "edge", "opera", "brave",
            "msedge", "googlechronehelper",
        ):
            return window
    return None


def capture_resolve_window(output_path: str = None, quality: int = 85, return_base64: bool = False) -> Dict[str, Any]:
    """Capture the DaVinci Resolve window."""
    window = find_resolve_window()
    if not window:
        return {"success": False, "error": "DaVinci Resolve window not found"}

    result = capture_window(window["Handle"], output_path, quality, return_base64)
    if result.get("success"):
        result["window_title"] = window.get("Title")
    return result


def get_monitor_info() -> Dict[str, Any]:
    """Get information about all monitors."""
    if is_macos():
        return _macos_get_monitor_info()

    if not (is_wsl() or is_windows()):
        return {"success": False, "error": "Not running on Windows, WSL, or macOS"}

    ps_script = """
    Add-Type -AssemblyName System.Windows.Forms
    $m = @(); $i = 0; foreach ($s in [System.Windows.Forms.Screen]::AllScreens) {
        $m += @{ Index = $i; DeviceName = $s.DeviceName; Primary = $s.Primary;
            Width = $s.Bounds.Width; Height = $s.Bounds.Height; X = $s.Bounds.X; Y = $s.Bounds.Y }; $i++ }
    @{ Monitors = $m; Count = $m.Count } | ConvertTo-Json -Compress
    """

    success, output, error = _run_powershell(ps_script)
    if not success:
        return {"success": False, "error": error}

    import json

    return {"success": True, **json.loads(output)}
