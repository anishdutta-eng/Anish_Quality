'''
This tool was created with the basic aim to understand wireless network field performance.
Author: Anish Dutta
Version: 3.0.0 - RSSI Coverage Heatmap & MCS Distance Mapping
Release date: February 10, 2026
New Features: Real-time RSSI coverage heatmap, coverage zone classification, MCS-at-distance scatter plot
'''
#!/usr/bin/env python3
import os, sys
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
import subprocess
import platform
import time
import threading
import contextlib
try:
    import speedtest
    _HAVE_SPEEDTEST = True
except ImportError:
    speedtest = None
    _HAVE_SPEEDTEST = False
import json
import urllib.error
import re
import socket
import ssl
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from collections import Counter
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from scipy.interpolate import griddata
from matplotlib.colors import ListedColormap, BoundaryNorm
import matplotlib.patches as mpatches

# eero product database (model normalization + expected capabilities)
try:
    import eero_devices
    _HAVE_EERO_DB = True
except ImportError:
    eero_devices = None
    _HAVE_EERO_DB = False

# ===== SIGNAL QUALITY COLOR MAP (Ekahau-style) =====
# Vivid survey-tool gradient anchored to real RSSI (dBm) thresholds:
#   bright green (best) -> lime -> yellow -> orange -> red (worst).
# Saturated so coverage zones are instantly readable.
from matplotlib.colors import LinearSegmentedColormap, Normalize
_SIGNAL_VMIN = -80.0   # -80 dBm and below = deep red (dead zone)
_SIGNAL_VMAX = -45.0   # -45 dBm and above = bright green (excellent)

def _rssi_pos(dbm):
    """Normalize an RSSI value (dBm) to 0..1 for the signal colormap."""
    return max(0.0, min(1.0, (dbm - _SIGNAL_VMIN) / (_SIGNAL_VMAX - _SIGNAL_VMIN)))

# Control points placed at meaningful RSSI levels for a vivid, intuitive ramp.
SIGNAL_CMAP = LinearSegmentedColormap.from_list('signal_quality', [
    (0.00,            '#B00000'),  # -80 dBm  dead zone — deep red
    (_rssi_pos(-76),  '#FF2A00'),  # -76 dBm  very poor — red
    (_rssi_pos(-70),  '#FF7A00'),  # -70 dBm  poor — orange
    (_rssi_pos(-65),  '#FFD400'),  # -65 dBm  medium — yellow
    (_rssi_pos(-58),  '#C8E000'),  # -58 dBm  fair — lime
    (_rssi_pos(-52),  '#46C300'),  # -52 dBm  good — green
    (1.00,            '#00A300'),  # -45 dBm  excellent — bright green
])
SIGNAL_NORM = Normalize(vmin=_SIGNAL_VMIN, vmax=_SIGNAL_VMAX)

def _calibrated_ref_power(rssis, dists, path_loss_exp=2.7):
    """
    Fit the path-loss reference power (RSSI at 1m) to ACTUAL measurements.

    The old code hard-coded -30 dBm at the AP, so the model always painted the
    full red->green rainbow regardless of what was measured. Anchoring the
    reference to real data means a session spent entirely in strong signal
    renders a mostly-green map, and a weak session renders mostly amber/red.
    """
    try:
        rssis = np.asarray(rssis, dtype=float)
        dists = np.maximum(np.asarray(dists, dtype=float), 0.1)
        p0 = np.mean(rssis + 10.0 * path_loss_exp * np.log10(dists))
        return float(np.clip(p0, -45.0, -15.0))
    except Exception:
        return -30.0


# ===== COMPOSITE NETWORK PERFORMANCE SCORE (0-100) =====
# A single "real-world performance" number blended from the five core link
# metrics, so a heat map can be colored green (great) -> red (bad).
#
# Design rationale (from WiFi RF fundamentals + industry thresholds):
#   - SNR is the strongest predictor of achievable rate/stability, so it gets
#     the largest weight. (>=40 dB excellent, 25 good, <15 unreliable.)
#   - RSSI captures raw signal strength / coverage. (>=-45 excellent, -67
#     usable, <-80 poor.)
#   - MCS is the modulation the link actually negotiated — a direct outcome of
#     real RF quality. (11ax tops out at MCS 11.)
#   - Tx rate (negotiated PHY data rate the radio reports) and the theoretical
#     PHY rate are throughput outcomes; they partly derive from the above, so
#     each carries a smaller weight to avoid double-counting.
#
# Each metric is mapped to a 0..1 sub-score via a piecewise-linear ramp between
# a "poor" anchor (0) and an "excellent" anchor (1), then combined with weights.
# Missing metrics are dropped and the remaining weights renormalized.

_SCORE_WEIGHTS = {
    "snr":  0.30,
    "rssi": 0.22,
    "mcs":  0.25,
    "tx":   0.13,
    "phy":  0.10,
}

# (poor_anchor, excellent_anchor) for each metric. Linear ramp, clamped 0..1.
_SCORE_ANCHORS = {
    "rssi": (-82.0, -45.0),   # dBm
    "snr":  (15.0,  35.0),    # dB — 35 dB = max usable (1024-QAM plateau)
    "mcs":  (2.0,   11.0),    # 802.11ax index
    "tx":   (50.0,  1200.0),  # Mbps (negotiated)
    "phy":  (50.0,  1400.0),  # Mbps (theoretical)
}

def _ramp(value, lo, hi):
    """Linear 0..1 ramp between lo (poor) and hi (excellent), clamped."""
    if value is None:
        return None
    if hi == lo:
        return 0.0
    return float(max(0.0, min(1.0, (value - lo) / (hi - lo))))

def compute_network_score(rssi=None, snr=None, mcs=None, tx_rate=None, phy_rate=None):
    """
    Blend the five core WiFi metrics into a single 0-100 performance score.

    Returns (score_0_100, breakdown) where breakdown maps each available
    metric to its 0-100 sub-score. Missing metrics are skipped and the
    remaining weights are renormalized so the score is always on a 0-100 scale.

    Higher is better -> use directly to drive a green(100)->red(0) colormap.
    """
    subs = {
        "rssi": _ramp(rssi,     *_SCORE_ANCHORS["rssi"]),
        "snr":  _ramp(snr,      *_SCORE_ANCHORS["snr"]),
        "mcs":  _ramp(mcs,      *_SCORE_ANCHORS["mcs"]),
        "tx":   _ramp(tx_rate,  *_SCORE_ANCHORS["tx"]),
        "phy":  _ramp(phy_rate, *_SCORE_ANCHORS["phy"]),
    }
    avail = {k: v for k, v in subs.items() if v is not None}
    if not avail:
        return None, {}
    total_w = sum(_SCORE_WEIGHTS[k] for k in avail)
    score = sum(_SCORE_WEIGHTS[k] * v for k, v in avail.items()) / total_w
    breakdown = {k: round(v * 100, 1) for k, v in avail.items()}
    return round(score * 100, 1), breakdown

# Score colormap (0-100): vivid red -> orange -> yellow -> green (Ekahau-style)
SCORE_CMAP = LinearSegmentedColormap.from_list('network_score', [
    (0.00, '#B00000'),  # 0   — critical (red)
    (0.20, '#FF2A00'),  # 20  — poor
    (0.40, '#FF7A00'),  # 40  — weak (orange)
    (0.55, '#FFD400'),  # 55  — fair (yellow)
    (0.70, '#C8E000'),  # 70  — good (lime)
    (0.85, '#46C300'),  # 85  — very good (green)
    (1.00, '#00A300'),  # 100 — excellent (bright green)
])
SCORE_NORM = Normalize(vmin=0, vmax=100)



# ANSI Color Codes - Softer colors for white background
class Colors:
    # Darker, more muted colors that work well on white backgrounds
    HEADER = '\033[38;5;93m'      # Dark purple
    OKBLUE = '\033[38;5;25m'      # Dark blue
    OKCYAN = '\033[38;5;30m'      # Dark cyan/teal
    OKGREEN = '\033[38;5;28m'     # Dark green
    WARNING = '\033[38;5;136m'    # Dark yellow/gold
    FAIL = '\033[38;5;124m'       # Dark red
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
    # Custom darker colors
    PURPLE = '\033[38;5;93m'      # Medium purple
    VIOLET = '\033[38;5;99m'      # Light purple
    YELLOW = '\033[38;5;136m'     # Muted yellow
    RED = '\033[38;5;124m'        # Dark red
    GREEN = '\033[38;5;28m'       # Dark green
    BLUE = '\033[38;5;25m'        # Dark blue
    CYAN = '\033[38;5;30m'        # Dark cyan
    TEAL = '\033[38;5;37m'        # Teal
    GRAY = '\033[38;5;240m'       # Medium gray
    ORANGE = '\033[38;5;166m'     # Muted orange

def print_header(text):
    """Print a beautiful header"""
    print(f"\n{Colors.BOLD}{Colors.PURPLE}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text:^80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.PURPLE}{'='*80}{Colors.ENDC}\n")

def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")

def print_warning(text):
    """Print warning message"""
    print(f"{Colors.ORANGE}⚠ {text}{Colors.ENDC}")

def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")

def print_info(text):
    """Print info message"""
    print(f"{Colors.TEAL}ℹ {text}{Colors.ENDC}")

def print_metric(label, value, unit="", color=Colors.CYAN):
    """Print a metric with color"""
    print(f"{Colors.BOLD}{label}:{Colors.ENDC} {color}{value}{unit}{Colors.ENDC}")

def prompt_ap_model(prompt_label):
    """
    Prompt for an AP model, validate against the eero device database, and
    return the canonical, brand-corrected model name.

    If the entry matches a known eero product, prints a confirmation with the
    device's expected capabilities. Otherwise falls back to brand-corrected
    free text (so non-eero APs are still accepted).
    """
    raw = input(f"{Colors.BOLD}{Colors.PURPLE}{prompt_label}{Colors.ENDC}").strip()
    if not raw:
        return "Not specified"

    if _HAVE_EERO_DB:
        dev = eero_devices.lookup(raw)
        if dev:
            print_success(f"Recognized: {dev.model} ({dev.wifi_standard})")
            print_info(f"  {eero_devices.describe(dev.model)}")
            return dev.model
        # Not a known eero product - keep brand-corrected free text
        normalized = eero_devices.normalize_model_name(raw)
        if normalized.lower() != raw.lower():
            print_info(f"  Using: {normalized}")
        else:
            print_warning("  Not in eero database - recorded as entered")
        return normalized

    # Fallback when database module unavailable: brand-correct "eero"
    return re.sub(r'(?i)\beero\b', 'eero', raw)

def get_rssi_color(rssi):
    """Get color based on RSSI value"""
    if rssi is None:
        return Colors.GRAY
    if rssi > -50:
        return Colors.GREEN
    elif rssi > -65:
        return Colors.TEAL
    elif rssi > -75:
        return Colors.ORANGE
    else:
        return Colors.RED

def get_snr_color(snr):
    """Get color based on SNR value"""
    if snr is None:
        return Colors.GRAY
    if snr > 35:
        return Colors.GREEN
    elif snr > 25:
        return Colors.TEAL
    elif snr > 15:
        return Colors.ORANGE
    else:
        return Colors.RED

def get_health_color(health):
    """Get color based on health status"""
    if health == "Excellent":
        return Colors.GREEN
    elif health == "Good":
        return Colors.TEAL
    else:
        return Colors.ORANGE

try:
    import CoreWLAN
except ImportError:
    print("Install PyObjC to enable live scanning:\n    pip install pyobjc")
    sys.exit(1)

# Save original directory (root folder)
original_dir = os.getcwd()
# Global file path variables 
log_file_path = None
plot_file_path = None
complete_diag_file = None
pdf_report_file = None
# Global exit flag
exit_requested = False
csv_data = []
roaming_events = []
interference_log = []
bssid_history = []
cached_ssid = ""
cached_chan = ""
ap_model = ""
user_provided_ssid = ""
sanity_check_passed = False
iteration_summaries = []  # Store summaries every 10 iterations

# Floor plan configuration
floorplan_config = {
    'image_path': None,          # Path to floor plan PNG/JPG
    'width_m': 40.0,             # Floor plan width in meters
    'height_m': 50.0,            # Floor plan height in meters
    'ap_x_m': 33.0,             # AP X position from left (meters)
    'ap_y_m': 25.0,             # AP Y position from top (meters)
    'enabled': False,            # Whether floor plan overlay is active
}

# Default floor plan: eero office at 16780 Lark Ave, Los Gatos
# AP location: 2nd table from right, next to CENTO 5
_DEFAULT_FLOORPLAN = 'default_floorplan.png'
_DEFAULT_FP_WIDTH = 30.0
_DEFAULT_FP_HEIGHT = 30.3
_DEFAULT_AP_X = 19.5
_DEFAULT_AP_Y = 14.7

# Predefined walk paths for the eero Los Gatos office floor plan
# Coordinates are (x_meters_from_left, y_meters_from_top)
# Paths are loops — when iterations exceed waypoints, they wrap around
WALK_PATHS = {
    1: {
        'name': 'North Perimeter Loop',
        'description': 'AP → CENTO 5 → VEGA 4 → PICCINO 2 → TRESTLE 8 → FIREFLY 7 → AP',
        'waypoints': [
            (19.5, 14.7, 'AP (Start)'),
            (21.6, 14.7, 'CENTO 5'),
            (21.6, 9.5,  'VEGA 4'),
            (21.6, 6.7,  'UNICO 3'),
            (21.6, 6.0,  'PICCINO 2'),
            (18.8, 6.0,  'JUPITER 1'),
            (13.4, 6.1,  'RECEPTION'),
            (9.2,  6.1,  'SAARINEN 9'),
            (9.2,  8.0,  'TRESTLE 8'),
            (9.2,  10.6, 'Near MEN/WOMEN'),
            (9.2,  13.5, 'FIREFLY 7'),
            (11.3, 15.6, 'Open Office West'),
            (15.7, 15.2, 'Open Office Center'),
            (19.5, 14.7, 'AP (Return)'),
        ]
    },
    2: {
        'name': 'South Perimeter Loop',
        'description': 'AP → TENT 1 → TENT 3 → South Door → MOTHER\'S ROOM → ANDYTOWN → AP',
        'waypoints': [
            (19.5, 14.7, 'AP (Start)'),
            (21.6, 17.5, 'Near TENT 1'),
            (21.6, 20.5, 'TENT 2'),
            (21.6, 23.5, 'TENT 3'),
            (19.0, 25.0, 'SCREEN ROOM area'),
            (14.0, 25.0, 'South corridor'),
            (11.0, 24.0, 'RACKS area'),
            (8.5,  23.0, 'SERVER / WORK ROOM'),
            (6.0,  23.0, 'MOTHER\'S ROOM'),
            (5.5,  20.0, 'ANDYTOWN'),
            (9.2,  16.5, 'Near FIREFLY 7'),
            (11.3, 15.6, 'Open Office SW'),
            (15.7, 15.2, 'Open Office Center'),
            (19.5, 14.7, 'AP (Return)'),
        ]
    },
    3: {
        'name': 'Stationary (No Movement)',
        'description': 'Stay at AP location — all measurements at same position',
        'waypoints': [
            (19.5, 14.7, 'AP (Stationary)'),
        ]
    }
}

# Active walk path state
_walk_path_config = {
    'path_id': None,           # Selected path ID (1, 2, 3, or None)
    'waypoints': [],           # List of (x, y, label) tuples
    'enabled': False,
}

def get_walk_position(iteration):
    """
    Get the (x, y) floor plan position for a given iteration number.
    
    Maps iterations to waypoints along the selected walk path.
    When iterations exceed the number of waypoints, wraps around (loop).
    Interpolates between waypoints for smooth positioning.
    
    Returns (x_m, y_m, label) or None if walk path not enabled.
    """
    wpc = _walk_path_config
    if not wpc['enabled'] or not wpc['waypoints']:
        return None
    
    wps = wpc['waypoints']
    n = len(wps)
    
    if n == 1:
        # Stationary — always return the single point
        return wps[0]
    
    # Map iteration to position along the path (loop with modulo)
    # Each segment between waypoints gets ~1 iteration
    # For smooth interpolation, use fractional position
    pos = (iteration - 1) % n
    return wps[pos]


# Comparative testing mode globals
comparative_mode = False
kgu_data = None  # Stores KGU test results
dut_data = None  # Stores DUT test results

@contextlib.contextmanager
def suppress_stderr():
    saved = sys.stderr
    sys.stderr = open(os.devnull, "w")
    try:
        yield
    finally:
        sys.stderr.close()
        sys.stderr = saved

def check_for_exit(exit_key='q'):
    global exit_requested
    while True:
        user_input = sys.stdin.readline().strip().lower()
        if user_input == exit_key:
            exit_requested = True
            print(f"Exit requested by user (pressed '{exit_key}').")
            break

def log_to_file(data):
    with open(log_file_path, "a") as f:
        f.write(data + "\n")

def get_ssid():
    """Get SSID with multiple fallback methods to handle macOS privacy restrictions"""
    global user_provided_ssid
    
    # If user provided SSID at start, use that instead of querying system
    if user_provided_ssid:
        return user_provided_ssid
    
    try:
        # Method 1: networksetup (works on macOS 14.5+)
        wireless_port = subprocess.check_output(
            "networksetup -listallhardwareports | awk '/Wi-Fi|AirPort/{getline; print $NF}' 2>/dev/null",
            shell=True, universal_newlines=True, timeout=5, stderr=subprocess.DEVNULL
        ).strip()
        
        if wireless_port:
            ssid = subprocess.check_output(
                f"networksetup -getairportnetwork {wireless_port} 2>/dev/null",
                shell=True, universal_newlines=True, timeout=5, stderr=subprocess.DEVNULL
            ).strip()
            
            # Extract SSID from "Current Wi-Fi Network: NetworkName"
            if "Current Wi-Fi Network:" in ssid:
                ssid = ssid.split("Current Wi-Fi Network:")[-1].strip()
                if ssid and ssid != "<redacted>":
                    return ssid
        
        # Method 2: ipconfig getsummary (works on some macOS versions)
        try:
            result = subprocess.check_output(
                f"ipconfig getsummary {wireless_port} 2>/dev/null | grep 'SSID :' | awk -F': ' '{{print $2}}'",
                shell=True, universal_newlines=True, timeout=5, stderr=subprocess.DEVNULL
            ).strip()
            if result and result != "<redacted>":
                return result
        except:
            pass
        
        # Method 3: system_profiler (fallback)
        ssid = subprocess.check_output(
            "system_profiler SPAirPortDataType 2>/dev/null | awk '/Current Network/ {getline;$1=$1;print $0 | \"tr -d ':'\";exit}'",
            shell=True, universal_newlines=True, timeout=5, stderr=subprocess.DEVNULL
        ).strip()
        if ssid and ssid != "<redacted>":
            return ssid
        
        # Method 4: CoreWLAN via Python (if available)
        try:
            import CoreWLAN
            iface = CoreWLAN.CWInterface.interface()
            if iface and iface.ssid():
                return iface.ssid()
        except:
            pass
        
        return "SSID Not Available (Privacy Restricted)"
        
    except Exception as e:
        return "SSID Not Available"

# ===== wdutil info cache =====
# `sudo wdutil info` is expensive: it spawns sudo and queries the wireless
# driver, taking a noticeable fraction of a second each call. The live sampling
# loop used to invoke it 8-9 times PER ITERATION (a separate shell pipeline per
# metric: RSSI, Tx, MCS, Noise, Channel, PHY, NSS, CCA, BSSID, Guard Interval).
# That subprocess storm is what made the machine hang. We now run it ONCE per
# iteration and parse every field from the cached text.
_wdutil_cache = {"text": "", "ts": 0.0}
# How long a single `wdutil info` snapshot may be reused. Short enough that each
# new survey point / loop iteration gets fresh data, long enough that the ~10
# metric reads taken at one moment all share a single subprocess.
_WDUTIL_TTL = 1.0

def refresh_wdutil_info():
    """Force a fresh `sudo wdutil info` read and cache the full output.

    Called at the top of each sampling iteration (live loop) and before each
    sample (survey mode); every get_* helper below then parses the cached text
    instead of shelling out again.
    """
    try:
        _wdutil_cache["text"] = subprocess.check_output(
            "sudo wdutil info",
            shell=True, universal_newlines=True, timeout=8,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        _wdutil_cache["text"] = ""
    _wdutil_cache["ts"] = time.time()
    return _wdutil_cache["text"]

def _wdutil_text():
    """Return cached wdutil output, auto-refreshing when empty or stale.

    The TTL keeps every metric read taken at one moment on a single snapshot
    (one subprocess) while still giving each new survey point or loop iteration
    fresh data — so callers outside the live loop (e.g. wl_survey) stay correct
    without having to manage the cache themselves.
    """
    if (not _wdutil_cache["text"]
            or (time.time() - _wdutil_cache["ts"]) > _WDUTIL_TTL):
        return refresh_wdutil_info()
    return _wdutil_cache["text"]

def _wdutil_field(needle):
    """Value after the first ':' on the first line containing `needle`.

    Mirrors the old `grep '<needle>' | cut -d ':' -f2` pipelines.
    """
    for line in _wdutil_text().splitlines():
        if needle in line:
            parts = line.split(":", 1)
            return parts[1].strip() if len(parts) > 1 else ""
    return ""

def get_bssid():
    """Get current AP BSSID (MAC address) for roaming detection."""
    try:
        # Primary: parse the cached `wdutil info` output (BSSID line, 3rd token).
        for line in _wdutil_text().splitlines():
            if "BSSID" in line:
                toks = line.split()
                if len(toks) >= 3:
                    bssid = toks[2].strip()
                    if bssid and bssid != "<redacted>" and len(bssid) > 5:
                        return bssid
                break

        # Fallback: CoreWLAN (no subprocess).
        try:
            import CoreWLAN
            iface = CoreWLAN.CWInterface.interface()
            if iface and iface.bssid():
                return iface.bssid()
        except Exception:
            pass

        return "Unknown"
    except Exception:
        return "Unknown"

def get_noise_floor():
    """Get noise floor (dBm) to calculate SNR.

    A valid WiFi noise floor is roughly -110..-45 dBm. wdutil can emit a stale,
    zero, positive, or otherwise implausible value (or grep may grab a digit from
    the wrong field), which then produces wildly wrong SNR. Reject those.
    """
    try:
        val = extract_value(_wdutil_field("Noise"))
        if val is None:
            return None
        # Noise floor must be negative and within a physically sane range.
        if val < -110 or val > -45:
            return None
        return val
    except Exception:
        return None

def get_wifi_channel():
    try:
        channel = _wdutil_field("Channel")
        return str(channel)[:9] if channel else "Unknown"
    except Exception:
        return "Unknown"

def extract_value(value):
    m = re.search(r"[-+]?\d+", value)
    return int(m.group(0)) if m else None

def get_mcs_index():
    try:
        m = re.search(r"\d+", _wdutil_field("MCS Index"))
        return int(m.group(0)) if m else None
    except Exception:
        return None

def get_wifi_stats():
    try:
        return {
            "RSSI": extract_value(_wdutil_field("RSSI")),
            "Tx Rate": extract_value(_wdutil_field("Tx")),
            "MCS Index": get_mcs_index()
        }
    except Exception as e:
        return {"Error": str(e)}

def run_ping_test():
    try:
        # Two quick pings keep the per-iteration latency probe under ~1-2s
        # instead of the ~5s that `ping -c 5` cost on every single sample.
        out = subprocess.check_output(
            "ping -c 2 -t 3 google.com",
            shell=True, universal_newlines=True, timeout=5
        )
        for line in out.splitlines():
            if "rtt" in line or "round-trip" in line:
                parts = line.split("=")
                vals = parts[1].split("/")[1]
                return float(vals)
        return None
    except Exception as e:
        print(f"Ping test error: {e}")
        return None

def get_phy():
    try:
        phy = _wdutil_field("PHY ")
        return phy or "Unknown"
    except Exception:
        return "Unknown"

def get_nss():
    try:
        nss = _wdutil_field("NSS")
        return nss or "Unknown"
    except Exception:
        return "Unknown"

def get_channel_utilization():
    try:
        utilization = _wdutil_field("CCA")
        match = re.search(r"(\d+)%", utilization)
        return int(match.group(1)) if match else utilization
    except Exception as e:
        return "Unknown"


# ===== RETRANSMISSION & PACKET LOSS MEASUREMENT =====

_retx_prev = {
    'tcp_retx': 0, 'if_opkts': 0, 'if_oerrs': 0,
    'if_ipkts': 0, 'if_ierrs': 0, 'initialized': False
}

def _parse_interface_stats():
    """Parse netstat -I en0 -b for packet/error counters."""
    try:
        out = subprocess.check_output(
            "netstat -I en0 -b", shell=True, universal_newlines=True, timeout=3)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 10 and parts[0] == 'en0' and '<Link' in parts[2]:
                return int(parts[4]), int(parts[5]), int(parts[7]), int(parts[8])
    except Exception:
        pass
    return None

def _parse_tcp_retransmissions():
    """Parse netstat -s -p tcp for cumulative TCP retransmission count."""
    try:
        out = subprocess.check_output(
            "netstat -s -p tcp", shell=True, universal_newlines=True, timeout=3)
        for line in out.splitlines():
            if 'retransmitted' in line.lower():
                m = re.search(r'(\d+)\s+data packet', line)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return 0

def get_retransmission_stats():
    """
    Measure retransmission rate between consecutive calls.
    Returns dict with tcp_retx_delta, if_err_rate (%), pkt_out_delta, status.
    """
    global _retx_prev
    result = {'tcp_retx_delta': 0, 'if_err_rate': 0.0, 'pkt_out_delta': 0, 'status': 'N/A'}
    
    if_stats = _parse_interface_stats()
    tcp_retx = _parse_tcp_retransmissions()
    if if_stats is None:
        return result
    
    ipkts, ierrs, opkts, oerrs = if_stats
    
    if not _retx_prev['initialized']:
        _retx_prev.update({'tcp_retx': tcp_retx, 'if_opkts': opkts, 'if_oerrs': oerrs,
                           'if_ipkts': ipkts, 'if_ierrs': ierrs, 'initialized': True})
        return result
    
    tcp_delta = max(0, tcp_retx - _retx_prev['tcp_retx'])
    opkts_delta = max(0, opkts - _retx_prev['if_opkts'])
    oerrs_delta = max(0, oerrs - _retx_prev['if_oerrs'])
    
    _retx_prev.update({'tcp_retx': tcp_retx, 'if_opkts': opkts, 'if_oerrs': oerrs,
                       'if_ipkts': ipkts, 'if_ierrs': ierrs})
    
    err_rate = (oerrs_delta / opkts_delta * 100) if opkts_delta > 0 else 0.0
    total_issues = tcp_delta + oerrs_delta
    combined_rate = (total_issues / max(opkts_delta, 1)) * 100
    
    status = 'Good' if combined_rate < 1 else ('Fair' if combined_rate < 5 else 'Poor')
    
    result.update({'tcp_retx_delta': tcp_delta, 'if_err_rate': round(err_rate, 2),
                   'pkt_out_delta': opkts_delta, 'status': status})
    return result

def get_ping_packet_loss():
    """
    Run ping -c 10 and extract packet loss % and jitter (stddev).
    Returns (avg_latency_ms, packet_loss_pct, jitter_ms).
    """
    try:
        out = subprocess.check_output(
            "ping -c 10 -q google.com", shell=True, universal_newlines=True, timeout=15)
        loss_pct = avg_lat = jitter = None
        for line in out.splitlines():
            if 'packet loss' in line:
                m = re.search(r'([\d.]+)%\s+packet loss', line)
                if m: loss_pct = float(m.group(1))
            if 'round-trip' in line or 'rtt' in line:
                m = re.search(r'=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', line)
                if m: avg_lat = float(m.group(2)); jitter = float(m.group(4))
        return avg_lat, loss_pct, jitter
    except Exception:
        return None, None, None


# ===== REAL THROUGHPUT MEASUREMENT (netstat byte counters) =====

_throughput_prev = {
    'ibytes': 0, 'obytes': 0, 'timestamp': 0, 'initialized': False
}

def _get_interface_bytes():
    """Parse netstat -I en0 -b for cumulative byte counters."""
    try:
        out = subprocess.check_output(
            "netstat -I en0 -b", shell=True, universal_newlines=True, timeout=3)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 10 and parts[0] == 'en0' and '<Link' in parts[2]:
                return int(parts[6]), int(parts[9])  # ibytes, obytes
    except Exception:
        pass
    return None, None

def get_real_throughput():
    """
    Measure actual WiFi throughput by sampling interface byte counters.
    
    Unlike Tx Rate (PHY rate reported by the driver), this measures real
    bytes flowing through the WiFi interface per second — the actual
    throughput the user experiences.
    
    Returns dict with:
    - rx_mbps: Download throughput (Mbps)
    - tx_mbps: Upload throughput (Mbps)  
    - total_mbps: Combined throughput (Mbps)
    - interval_s: Measurement interval (seconds)
    - efficiency: (total_mbps / phy_tx_rate * 100) if phy rate available
    
    First call initializes baseline and returns zeros.
    """
    global _throughput_prev
    
    result = {'rx_mbps': 0.0, 'tx_mbps': 0.0, 'total_mbps': 0.0, 'interval_s': 0.0}
    
    ib, ob = _get_interface_bytes()
    now = time.time()
    
    if ib is None or ob is None:
        return result
    
    if not _throughput_prev['initialized']:
        _throughput_prev.update({'ibytes': ib, 'obytes': ob, 'timestamp': now, 'initialized': True})
        return result
    
    dt = now - _throughput_prev['timestamp']
    if dt < 0.1:  # Avoid division by near-zero
        return result
    
    rx_delta = max(0, ib - _throughput_prev['ibytes'])
    tx_delta = max(0, ob - _throughput_prev['obytes'])
    
    _throughput_prev.update({'ibytes': ib, 'obytes': ob, 'timestamp': now})
    
    rx_mbps = (rx_delta * 8) / (dt * 1_000_000)
    tx_mbps = (tx_delta * 8) / (dt * 1_000_000)
    
    result.update({
        'rx_mbps': round(rx_mbps, 2),
        'tx_mbps': round(tx_mbps, 2),
        'total_mbps': round(rx_mbps + tx_mbps, 2),
        'interval_s': round(dt, 2)
    })
    return result


def get_guard_interval():
    """Get the current 802.11ax Guard Interval in nanoseconds from wdutil."""
    try:
        m = re.search(r'\d+', _wdutil_field("Guard Interval"))
        return int(m.group(0)) if m else 800
    except Exception:
        return 800  # Default to 0.8µs


def calculate_80211ax_phy_rate(mcs, nss, bw_mhz, gi_ns=800):
    """
    Calculate the IEEE 802.11ax (Wi-Fi 6) theoretical PHY data rate.
    
    Based on the standard formula:
        Rate = (N_SD × N_BPSCS × R × NSS) / T_SYMBOL
    where:
        N_SD   = Number of data subcarriers (depends on bandwidth)
        N_BPSCS = Bits per subcarrier per symbol (depends on modulation)
        R      = Coding rate
        NSS    = Number of spatial streams
        T_SYMBOL = T_DFT + T_GI (OFDM symbol duration)
        T_DFT  = 12.8 µs (fixed for 802.11ax HE)
        T_GI   = 0.8, 1.6, or 3.2 µs
    
    Parameters:
        mcs:    MCS index (0-11)
        nss:    Number of spatial streams (1-8)
        bw_mhz: Channel bandwidth in MHz (20, 40, 80, 160)
        gi_ns:  Guard interval in nanoseconds (800, 1600, 3200)
    
    Returns dict with:
        phy_rate_mbps: Theoretical PHY rate in Mbps
        modulation: Modulation scheme name
        coding_rate: Coding rate as string
        n_sd: Number of data subcarriers
        n_bpscs: Bits per subcarrier
        explanation: Human-readable breakdown
    
    Reference: IEEE 802.11ax-2021, Table 27-64 through 27-68
    Content rephrased for compliance with licensing restrictions.
    """
    # Data subcarriers per bandwidth (802.11ax HE)
    n_sd_table = {20: 234, 40: 468, 80: 980, 160: 1960}
    
    # MCS table: (modulation_name, bits_per_subcarrier, coding_rate_numerator, coding_rate_denominator)
    mcs_table = {
        0:  ('BPSK',     1, 1, 2),
        1:  ('QPSK',     2, 1, 2),
        2:  ('QPSK',     2, 3, 4),
        3:  ('16-QAM',   4, 1, 2),
        4:  ('16-QAM',   4, 3, 4),
        5:  ('64-QAM',   6, 2, 3),
        6:  ('64-QAM',   6, 3, 4),
        7:  ('64-QAM',   6, 5, 6),
        8:  ('256-QAM',  8, 3, 4),
        9:  ('256-QAM',  8, 5, 6),
        10: ('1024-QAM', 10, 3, 4),
        11: ('1024-QAM', 10, 5, 6),
    }
    
    result = {
        'phy_rate_mbps': 0, 'modulation': 'Unknown', 'coding_rate': 'N/A',
        'n_sd': 0, 'n_bpscs': 0, 'explanation': 'N/A'
    }
    
    if mcs is None or mcs not in mcs_table:
        return result
    if nss is None or nss < 1:
        nss = 1
    if bw_mhz not in n_sd_table:
        bw_mhz = 80  # Default assumption
    
    n_sd = n_sd_table[bw_mhz]
    mod_name, n_bpscs, r_num, r_den = mcs_table[mcs]
    coding_rate = r_num / r_den
    
    # OFDM symbol duration: T_DFT = 12.8µs for 802.11ax HE
    t_dft_us = 12.8
    t_gi_us = gi_ns / 1000.0  # Convert ns to µs
    t_symbol_us = t_dft_us + t_gi_us
    
    # PHY rate in Mbps
    phy_rate = (n_sd * n_bpscs * coding_rate * nss) / t_symbol_us
    
    # Estimated application throughput (~65% of PHY rate for TCP, accounting for
    # MAC overhead, IP headers, ACKs, and inter-frame spacing)
    est_throughput = phy_rate * 0.65
    
    result.update({
        'phy_rate_mbps': round(phy_rate, 1),
        'est_throughput_mbps': round(est_throughput, 1),
        'modulation': mod_name,
        'coding_rate': f"{r_num}/{r_den}",
        'n_sd': n_sd,
        'n_bpscs': n_bpscs,
        'explanation': (
            f"MCS {mcs} ({mod_name} {r_num}/{r_den}) × {nss}SS × {bw_mhz}MHz × GI {gi_ns}ns "
            f"= {n_sd}×{n_bpscs}×{coding_rate:.3f}×{nss} / {t_symbol_us}µs "
            f"= {phy_rate:.1f} Mbps PHY → ~{est_throughput:.0f} Mbps est. throughput"
        )
    })
    return result


# ===== HOME / 4K-STREAMING PERFORMANCE MODEL =====
# A practical "good home WiFi" yardstick anchored to 4K (UHD) streaming, which
# needs a sustained ~25 Mbps (Netflix 4K recommendation; industry "4K floor").
#
# Crucially, a link cannot sustain its momentarily-reported PHY rate when the RF
# is weak. This model is grounded in published RF limits:
#   * Each MCS requires a minimum SNR to be decoded reliably; you cannot hold a
#     modulation your SNR doesn't support (Revolution-WiFi / mcsindex tables).
#   * Each extra MIMO spatial stream needs substantially higher SNR (~+8-10 dB),
#     so weak links collapse to a single stream.
#   * Reliable streaming video needs RSSI >= -67 dBm; below -80 dBm links suffer
#     heavy retransmission / packet loss (MetaGeek, NetSpot, IEEE 802.11ax data).
# Content rephrased for compliance with licensing restrictions.
FOURK_MIN_MBPS = 25.0       # sustained throughput needed for smooth 4K (UHD)
HOME_TARGET_MBPS = 150.0    # headroom target that maps to a top score / "excellent"

# Reliable-streaming gates (a link must clear these to be called 4K-capable).
STREAM_MIN_RSSI = -67.0     # dBm — minimum for dependable streaming video
STREAM_MIN_SNR = 25.0       # dB  — needed to hold the higher MCS that give 4K headroom

# Approximate minimum SNR (dB) required to *sustain* each 802.11ax MCS.
# (Commonly published values; used to cap the reported MCS to what the measured
# SNR can actually support.)
_REQUIRED_SNR_FOR_MCS = {
    0: 5, 1: 8, 2: 11, 3: 13, 4: 17, 5: 20,
    6: 22, 7: 25, 8: 29, 9: 31, 10: 35, 11: 37,
}

def max_mcs_for_snr(snr):
    """Highest 802.11ax MCS the given SNR (dB) can reliably sustain (0..11).

    Returns -1 if SNR is too low to hold even MCS0 (no usable link).
    """
    if snr is None:
        return 11  # unknown SNR: don't cap on this axis (RSSI gate still applies)
    best = -1
    for m, req in _REQUIRED_SNR_FOR_MCS.items():
        if snr >= req:
            best = max(best, m)
    return best

def _sustainable_nss(nss, snr):
    """Spatial streams the link can actually carry given SNR.

    MIMO spatial multiplexing needs strong SNR: a 2nd stream ~>=25 dB, a 3rd/4th
    ~>=32 dB. Weak links fall back to a single stream.
    """
    nss = int(nss) if (nss and nss >= 1) else 1
    if snr is None:
        return nss
    if snr >= 32:
        return nss
    if snr >= 25:
        return min(nss, 2)
    return 1

def estimate_achievable_throughput(rssi, snr, mcs, nss, bw_mhz=80, gi_ns=800):
    """Estimate realistic sustained TCP throughput (Mbps) from link metrics.

    Steps (physically grounded, conservative):
      1. Cap the reported MCS to what the measured SNR can sustain.
      2. Cap spatial streams (NSS) to what the SNR supports (MIMO needs high SNR).
      3. Compute the 802.11ax PHY rate from the *effective* MCS/NSS/BW/GI.
      4. Apply MAC/TCP efficiency (~0.65) for goodput.
      5. Derate for packet loss/retransmission driven by RSSI, plus a small
         penalty when SNR only marginally clears the modulation's requirement.

    Returns estimated Mbps (float), or None when inputs are insufficient.
    """
    if mcs is None or rssi is None:
        return None

    reported_mcs = int(round(mcs))
    eff_mcs = min(reported_mcs, max_mcs_for_snr(snr))
    if eff_mcs < 0:
        return 0.0  # SNR too low to hold any modulation
    eff_nss = _sustainable_nss(nss, snr)

    calc = calculate_80211ax_phy_rate(eff_mcs, eff_nss, bw_mhz, gi_ns)
    phy = calc.get('phy_rate_mbps') or 0.0
    if phy <= 0:
        return 0.0

    efficiency = 0.65

    # RSSI -> packet-delivery reliability (retransmissions rise sharply as signal
    # weakens). >=-65 dBm clean; -80 dBm barely usable; below that almost nothing.
    if rssi >= -65:
        rssi_factor = 1.0
    elif rssi >= -72:
        rssi_factor = 0.5 + 0.5 * (rssi - (-72)) / 7.0          # -72..-65 -> 0.5..1.0
    elif rssi >= -80:
        rssi_factor = 0.1 + 0.4 * (rssi - (-80)) / 8.0          # -80..-72 -> 0.1..0.5
    else:
        rssi_factor = 0.05

    # Small extra penalty if SNR only just clears the (already-capped) MCS need.
    req = _REQUIRED_SNR_FOR_MCS.get(eff_mcs, 0)
    margin = (snr - req) if snr is not None else 10.0
    snr_margin_factor = max(0.5, min(1.0, 0.5 + 0.05 * margin))  # +10 dB margin -> 1.0

    reliability = rssi_factor * snr_margin_factor
    return round(phy * efficiency * reliability, 1)


def home_performance(rssi, snr, mcs, nss, bw_mhz=80, gi_ns=800):
    """Grade a measurement for 'best home performance', anchored to 4K streaming.

    A point is only called 4K-capable when it BOTH delivers >=25 Mbps of realistic
    sustained throughput AND meets the reliable-streaming RF gates (RSSI/SNR),
    because steady 4K needs dependable delivery, not just a peak rate.

    Returns a dict:
      throughput_mbps : estimated realistic sustained TCP throughput
      score           : 0-100 (60 == exactly the 25 Mbps 4K floor)
      streams_4k      : simultaneous 25 Mbps 4K streams it can sustain
      capable_4k      : bool — clears the throughput AND RF reliability gates
      label           : short human-readable verdict
    """
    tput = estimate_achievable_throughput(rssi, snr, mcs, nss, bw_mhz, gi_ns)
    if tput is None:
        return {"throughput_mbps": None, "score": None, "streams_4k": None,
                "capable_4k": None, "label": "no data"}

    # RF reliability gate for dependable streaming.
    rssi_ok = (rssi is not None and rssi >= STREAM_MIN_RSSI)
    snr_ok = (snr is None or snr >= STREAM_MIN_SNR)
    rf_reliable = rssi_ok and snr_ok

    capable = (tput >= FOURK_MIN_MBPS) and rf_reliable
    streams = tput / FOURK_MIN_MBPS

    if tput <= 0:
        score = 0.0
    elif tput < FOURK_MIN_MBPS:
        score = 60.0 * (tput / FOURK_MIN_MBPS)
    else:
        head = (tput - FOURK_MIN_MBPS) / (HOME_TARGET_MBPS - FOURK_MIN_MBPS)
        score = 60.0 + 40.0 * max(0.0, min(1.0, head))
    # If throughput looks fine but the RF is too weak for reliable streaming,
    # cap the score below the 4K-pass line so the map doesn't over-promise.
    if not rf_reliable:
        score = min(score, 55.0)

    if tput >= FOURK_MIN_MBPS and not rf_reliable:
        label = "Marginal (weak signal)"
    elif not capable:
        label = "Below 4K"
    elif streams >= 4:
        label = "Excellent (multi-4K)"
    elif streams >= 2:
        label = "Great (2+ 4K)"
    else:
        label = "4K-ready"

    return {"throughput_mbps": tput, "score": round(score, 1),
            "streams_4k": round(streams, 1), "capable_4k": capable, "label": label}


def get_speedtest():
    """Enhanced speedtest with better error handling and SSL fix"""
    attempts, max_attempts = 0, 3
    
    # Create SSL context that doesn't verify certificates (for speedtest)
    if not _HAVE_SPEEDTEST:
        print_warning("speedtest module not installed — skipping speed test.")
        print_info("Install it with: pip3 install speedtest-cli")
        return None, None, None
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
    except AttributeError:
        pass  # Python version doesn't support this
    
    while attempts < max_attempts:
        try:
            print_info(f"Running speedtest (attempt {attempts + 1}/{max_attempts})...")
            
            # Create speedtest object with timeout and secure=False
            st = speedtest.Speedtest(secure=False)
            st.timeout = 10  # 10 second timeout
            
            # Get best server with error handling
            try:
                print_info("Finding best server...")
                servers = st.get_servers()
                st.get_best_server()
                server = st.results.server
                print_success(f"Connected to: {server['sponsor']} ({server['name']}, {server['country']})")
            except (socket.gaierror, socket.timeout, ConnectionError, ssl.SSLError) as e:
                error_msg = str(e)[:80]
                if 'SSL' in error_msg or 'CERTIFICATE' in error_msg:
                    print_warning(f"SSL certificate error - trying alternative method...")
                else:
                    print_warning(f"Server connection failed: {error_msg}")
                attempts += 1
                time.sleep(2)
                continue
            
            # Download test
            print_info("Testing download speed...")
            try:
                dl = st.download(threads=4) / 1e6  # Use 4 threads for faster test
                print_success(f"Download: {dl:.2f} Mbps")
            except Exception as e:
                print_warning(f"Download test failed: {str(e)[:50]}")
                dl = None
            
            # Upload test
            print_info("Testing upload speed...")
            try:
                ul = st.upload(threads=4) / 1e6  # Use 4 threads
                print_success(f"Upload: {ul:.2f} Mbps")
            except Exception as e:
                print_warning(f"Upload test failed: {str(e)[:50]}")
                ul = None
            
            # Ping
            ping = st.results.ping if hasattr(st.results, 'ping') else None
            
            # Additional metrics
            if dl and ul:
                jitter = getattr(st.results, 'jitter', None)
                packet_loss = getattr(st.results, 'packet_loss', None)
                
                print_metric("  Ping", f"{ping:.1f}" if ping else "N/A", " ms", Colors.PURPLE)
                if jitter:
                    print_metric("  Jitter", f"{jitter:.1f}", " ms", Colors.PURPLE)
                if packet_loss:
                    print_metric("  Packet Loss", f"{packet_loss:.1f}", "%", Colors.ORANGE if packet_loss > 1 else Colors.GREEN)
                
                # Calculate quality score
                if ping and dl and ul:
                    quality = "Excellent" if ping < 30 and dl > 50 else "Good" if ping < 50 and dl > 25 else "Fair"
                    color = Colors.GREEN if quality == "Excellent" else Colors.TEAL if quality == "Good" else Colors.ORANGE
                    print_metric("  Connection Quality", quality, "", color)
            
            if dl is not None and ul is not None:
                return ping, dl, ul
            
            attempts += 1
            
        except urllib.error.HTTPError as e:
            if e.code == 403:
                print_error("Speedtest HTTP 403 - Rate limited by server")
                return None, None, None
            print_warning(f"HTTP Error {e.code}: {str(e)[:50]}")
            attempts += 1
            
        except urllib.error.URLError as e:
            error_msg = str(e)
            if 'SSL' in error_msg or 'CERTIFICATE' in error_msg:
                print_error("SSL Certificate Error - Your Python installation may need certificate updates")
                print_info("Try: pip3 install --upgrade certifi")
                print_info("Or run: /Applications/Python*/Install\\ Certificates.command")
                return None, None, None
            print_warning(f"URL Error: {str(e)[:80]}")
            attempts += 1
            
        except socket.gaierror as e:
            print_error(f"DNS resolution failed: {str(e)[:50]}")
            print_info("This usually means no internet connection or DNS issues")
            return None, None, None
            
        except socket.timeout:
            print_warning("Speedtest timed out")
            attempts += 1
            
        except ssl.SSLError as e:
            print_error(f"SSL Error: {str(e)[:80]}")
            print_info("Your Python may need SSL certificate updates")
            return None, None, None
            
        except Exception as e:
            print_warning(f"Speedtest error: {str(e)[:80]}")
            attempts += 1
        
        if attempts < max_attempts:
            print_info(f"Retrying in 3 seconds...")
            time.sleep(3)
    
    print_error("Speedtest failed after all attempts - continuing without speedtest data")
    return None, None, None 

def parse_speed(val):
    try:
        return float(val.split()[0])
    except Exception:
        return None

def complete_wifi_diagnostics():
    try:
        out = subprocess.check_output(
            "wdutil diagnose -q",
            shell=True, universal_newlines=True, timeout=60
        )
        with open(complete_diag_file, "w") as f:
            f.write(out)
        print(f"Complete diagnostics logged to {complete_diag_file}")
    except Exception as e:
        print(f"Complete diagnostics error: {e}")

def generate_pdf_report():
    """Generate comprehensive IEEE 802.11 technical diagnostic report"""
    global ap_model, user_provided_ssid, sanity_check_passed, iteration_summaries
    
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import statistics as _stats
    
    doc = SimpleDocTemplate(pdf_report_file, pagesize=letter,
                           rightMargin=0.6*inch, leftMargin=0.6*inch,
                           topMargin=0.6*inch, bottomMargin=0.6*inch)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'],
        fontSize=22, textColor=colors.HexColor('#1A1A2E'),
        spaceAfter=6, alignment=TA_CENTER
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#7F8C8D'),
        spaceAfter=20, alignment=TA_CENTER
    )
    heading_style = ParagraphStyle(
        'CustomHeading', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#1A1A2E'),
        spaceAfter=8, spaceBefore=14
    )
    subheading_style = ParagraphStyle(
        'SubHeading', parent=styles['Heading3'],
        fontSize=11, textColor=colors.HexColor('#34495E'),
        spaceAfter=6, spaceBefore=10
    )
    body_style = ParagraphStyle(
        'BodyText2', parent=styles['Normal'],
        fontSize=9, leading=13, spaceAfter=6
    )
    small_style = ParagraphStyle(
        'SmallText', parent=styles['Normal'],
        fontSize=8, leading=11, textColor=colors.HexColor('#555555')
    )
    
    # ===== Helper: styled table =====
    def make_table(data, col_widths=None, header_color='#1A1A2E'):
        t = Table(data, colWidths=col_widths)
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(header_color)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9FA')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F8F9FA'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DEE2E6')),
        ]
        t.setStyle(TableStyle(style_cmds))
        return t
    
    # ===== Precompute statistics =====
    rssi_vals = [row[1] for row in csv_data if row[1] is not None]
    snr_vals_pdf = [row[7] for row in csv_data if row[7] is not None]
    tx_vals = [row[2] for row in csv_data if row[2] is not None]
    lat_vals = [row[3] for row in csv_data if row[3] is not None]
    mcs_vals_pdf = [row[4] for row in csv_data if row[4] is not None]
    cu_vals = [row[5] for row in csv_data if isinstance(row[5], int)]
    noise_vals = [row[6] for row in csv_data if row[6] is not None]
    
    def safe_avg(lst): return sum(lst)/len(lst) if lst else 0
    def safe_med(lst): return _stats.median(lst) if lst else 0
    def safe_std(lst): return _stats.stdev(lst) if len(lst) > 1 else 0
    def pct(lst, p):
        if not lst: return 0
        s = sorted(lst)
        k = int(len(s) * p / 100)
        return s[min(k, len(s)-1)]
    
    # ===== 802.11ax MCS reference table =====
    mcs_ref = {
        0:  ('BPSK',   '1/2', 8.6,   17.2,  36.0,  72.1),
        1:  ('QPSK',   '1/2', 17.2,  34.4,  72.1,  144.1),
        2:  ('QPSK',   '3/4', 25.8,  51.6,  108.1, 216.2),
        3:  ('16-QAM', '1/2', 34.4,  68.8,  144.1, 288.2),
        4:  ('16-QAM', '3/4', 51.6,  103.2, 216.2, 432.4),
        5:  ('64-QAM', '2/3', 68.8,  137.6, 288.2, 576.5),
        6:  ('64-QAM', '3/4', 77.4,  154.9, 324.3, 648.5),
        7:  ('64-QAM', '5/6', 86.0,  172.1, 360.3, 720.6),
        8:  ('256-QAM','3/4', 103.2, 206.5, 432.4, 864.7),
        9:  ('256-QAM','5/6', 114.7, 229.4, 480.4, 960.7),
        10: ('1024-QAM','3/4',129.0, 258.1, 540.4, 1080.9),
        11: ('1024-QAM','5/6',143.4, 286.8, 600.5, 1201.0),
    }
    
    # ===== PAGE 1: Title & Executive Summary =====
    story.append(Paragraph("IEEE 802.11 Wireless Diagnostic Report", title_style))
    story.append(Spacer(1, 0.1*inch))
    
    # Subtitle with test metadata
    ssid_display = user_provided_ssid if user_provided_ssid else cached_ssid
    # Get channel from csv_data (more reliable than cached_chan which may be empty)
    chan_display = "Unknown"
    if csv_data and len(csv_data[0]) > 12:
        chan_raw = str(csv_data[0][12]).strip().replace('\n','').replace('\r','')
        if chan_raw and chan_raw != "N/A":
            chan_display = chan_raw
    if chan_display == "Unknown" and cached_chan:
        chan_display = str(cached_chan).strip().replace('\n','').replace('\r','')
    story.append(Paragraph(
        f"SSID: {ssid_display} &nbsp;|&nbsp; Channel: {chan_display} &nbsp;|&nbsp; AP: {ap_model or 'N/A'}",
        subtitle_style))
    
    # ---- Test Configuration ----
    story.append(Paragraph("1. Test Configuration", heading_style))
    
    # Determine PHY mode and bandwidth
    phy_display, bw_display, band_display = "Unknown", "Unknown", "Unknown"
    if csv_data and len(csv_data[0]) > 9:
        phy_raw = str(csv_data[0][9]).strip() if csv_data[0][9] else ""
        if 'ax' in phy_raw.lower(): phy_display = "802.11ax (Wi-Fi 6)"
        elif 'ac' in phy_raw.lower(): phy_display = "802.11ac (Wi-Fi 5)"
        elif 'n' in phy_raw.lower() or 'ht' in phy_raw.lower(): phy_display = "802.11n (Wi-Fi 4)"
    if chan_display and chan_display != "Unknown":
        if '160' in chan_display: bw_display = "160 MHz"
        elif '80' in chan_display: bw_display = "80 MHz"
        elif '40' in chan_display: bw_display = "40 MHz"
        else: bw_display = "20 MHz"
        chan_lower = chan_display.lower()
        if chan_lower.startswith('6g') or '6g' in chan_lower: band_display = "6 GHz (Wi-Fi 6E)"
        elif chan_lower.startswith('5g') or '5g' in chan_lower: band_display = "5 GHz (UNII-1/2/3)"
        else:
            # Try to parse channel number
            try:
                ch_num = int(chan_display.split('/')[0].replace('g','').replace('G',''))
                if ch_num > 165: band_display = "6 GHz (Wi-Fi 6E)"
                elif ch_num > 14: band_display = "5 GHz (UNII-1/2/3)"
                else: band_display = "2.4 GHz (ISM)"
            except (ValueError, IndexError):
                band_display = "Unknown"
    nss_display = "Unknown"
    if csv_data and len(csv_data[0]) > 10:
        nss_raw = str(csv_data[0][10]).strip()
        import re as _re
        nss_m = _re.search(r'\d+', nss_raw)
        if nss_m: nss_display = f"{nss_m.group(0)} Spatial Streams"
    
    test_info = [["Parameter", "Value"],
        ["Test Name", test_name], ["Date/Time", time.strftime("%Y-%m-%d %H:%M:%S")],
        ["AP Model", ap_model or "N/A"], ["SSID", ssid_display or "Unknown"],
        ["Channel", chan_display], ["Band", band_display], ["Bandwidth", bw_display],
        ["PHY Mode", phy_display], ["NSS", nss_display],
        ["Iterations", str(len(csv_data))],
        ["Duration", f"{csv_data[-1][0]:.1f} s" if csv_data else "N/A"],
        ["Sanity Check", "PASSED" if sanity_check_passed else "FAILED"]]
    story.append(make_table(test_info, col_widths=[2.2*inch, 4.5*inch]))
    story.append(Spacer(1, 0.2*inch))
    
    # ---- Executive Summary ----
    story.append(Paragraph("2. Executive Summary", heading_style))
    avg_rssi = safe_avg(rssi_vals); avg_snr = safe_avg(snr_vals_pdf)
    avg_tx = safe_avg(tx_vals); avg_mcs = safe_avg(mcs_vals_pdf)
    avg_lat = safe_avg(lat_vals); avg_cu = safe_avg(cu_vals)
    peak_tx = max(tx_vals) if tx_vals else 0
    peak_mcs = max(mcs_vals_pdf) if mcs_vals_pdf else 0
    issues_found = []
    if avg_rssi < -65: issues_found.append("Weak signal strength")
    if avg_snr < 20: issues_found.append("Low SNR")
    if avg_mcs < 5: issues_found.append("Low MCS")
    if avg_cu > 70: issues_found.append("High channel utilization")
    if avg_lat > 50: issues_found.append("Elevated latency")
    if not issues_found:
        verdict = "PASS - Performance meets 802.11ax expectations"
        vc = '#27AE60'
    elif len(issues_found) <= 2:
        verdict = "MARGINAL - Minor issues detected"
        vc = '#F39C12'
    else:
        verdict = "FAIL - Significant wireless issues"
        vc = '#E74C3C'
    story.append(Paragraph(f"<font color='{vc}'><b>{verdict}</b></font>", body_style))
    for iss in issues_found:
        story.append(Paragraph(f"&nbsp;&nbsp;&bull; {iss}", small_style))
    story.append(Spacer(1, 0.15*inch))
    
    # ---- RF Performance ----
    story.append(Paragraph("3. RF Performance Summary", heading_style))
    if csv_data:
        def sc(v, g, f, hib=True):
            if hib: return "Good" if v >= g else ("Fair" if v >= f else "Poor")
            else: return "Good" if v <= g else ("Fair" if v <= f else "Poor")
        pd = [["Metric","Mean","Med","StdDev","Min","Max","5th%","95th%","Status"],
            ["RSSI(dBm)",f"{avg_rssi:.1f}",f"{safe_med(rssi_vals):.1f}",f"{safe_std(rssi_vals):.1f}",
             f"{min(rssi_vals)}",f"{max(rssi_vals)}",f"{pct(rssi_vals,5)}",f"{pct(rssi_vals,95)}",sc(avg_rssi,-50,-65)],
            ["SNR(dB)",f"{avg_snr:.1f}",f"{safe_med(snr_vals_pdf):.1f}",f"{safe_std(snr_vals_pdf):.1f}",
             f"{min(snr_vals_pdf)}" if snr_vals_pdf else "-",f"{max(snr_vals_pdf)}" if snr_vals_pdf else "-",
             f"{pct(snr_vals_pdf,5)}",f"{pct(snr_vals_pdf,95)}",sc(avg_snr,25,15)],
            ["Tx(Mbps)",f"{avg_tx:.0f}",f"{safe_med(tx_vals):.0f}",f"{safe_std(tx_vals):.0f}",
             f"{min(tx_vals)}" if tx_vals else "-",f"{max(tx_vals)}" if tx_vals else "-",
             f"{pct(tx_vals,5):.0f}",f"{pct(tx_vals,95):.0f}",sc(avg_tx,500,100)],
            ["Lat(ms)",f"{avg_lat:.1f}",f"{safe_med(lat_vals):.1f}",f"{safe_std(lat_vals):.1f}",
             f"{min(lat_vals):.1f}" if lat_vals else "-",f"{max(lat_vals):.1f}" if lat_vals else "-",
             f"{pct(lat_vals,5):.1f}",f"{pct(lat_vals,95):.1f}",sc(avg_lat,30,80,False)],
            ["MCS",f"{avg_mcs:.1f}",f"{safe_med(mcs_vals_pdf):.0f}",f"{safe_std(mcs_vals_pdf):.1f}",
             f"{min(mcs_vals_pdf)}" if mcs_vals_pdf else "-",f"{max(mcs_vals_pdf)}" if mcs_vals_pdf else "-",
             f"{pct(mcs_vals_pdf,5)}",f"{pct(mcs_vals_pdf,95)}",sc(avg_mcs,8,4)],
            ["CU(%)",f"{avg_cu:.0f}" if cu_vals else "-",f"{safe_med(cu_vals):.0f}" if cu_vals else "-",
             f"{safe_std(cu_vals):.0f}" if cu_vals else "-",f"{min(cu_vals)}" if cu_vals else "-",
             f"{max(cu_vals)}" if cu_vals else "-",f"{pct(cu_vals,5)}" if cu_vals else "-",
             f"{pct(cu_vals,95)}" if cu_vals else "-",sc(avg_cu,50,80,False) if cu_vals else "-"]]
        cw=[0.8*inch]+[0.55*inch]*7+[0.6*inch]
        story.append(make_table(pd, col_widths=cw))
    story.append(Spacer(1, 0.15*inch))
    
    # ---- MCS Reference ----
    story.append(Paragraph("4. IEEE 802.11ax MCS Reference", heading_style))
    story.append(Paragraph("HE MCS with modulation, coding rate, PHY rates per SS. Rates scale with NSS.", small_style))
    mt = [["MCS","Mod","Code","20MHz","40MHz","80MHz","160MHz","Seen"]]
    obs_mcs = set(mcs_vals_pdf) if mcs_vals_pdf else set()
    for idx in range(12):
        m,c,r2,r4,r8,r16 = mcs_ref[idx]
        mt.append([str(idx),m,c,f"{r2:.1f}",f"{r4:.1f}",f"{r8:.1f}",f"{r16:.1f}","Yes" if idx in obs_mcs else ""])
    mcw=[0.35*inch,0.8*inch,0.45*inch,0.6*inch,0.6*inch,0.6*inch,0.65*inch,0.5*inch]
    story.append(make_table(mt, col_widths=mcw, header_color='#2C3E50'))
    if mcs_vals_pdf:
        pi = mcs_ref.get(peak_mcs, ('?','?',0,0,0,0))
        story.append(Paragraph(f"<b>Peak MCS:</b> {peak_mcs} ({pi[0]}, {pi[1]}) | 160MHz/1SS: {pi[5]:.1f} Mbps | Measured peak: {peak_tx} Mbps", body_style))
    story.append(Spacer(1, 0.15*inch))
    
    # ---- Link Budget ----
    story.append(Paragraph("5. Link Budget & Path Loss", heading_style))
    if rssi_vals and noise_vals:
        an = safe_avg(noise_vals)
        ld = [["Param","Value","Notes"],
            ["Avg RSSI",f"{avg_rssi:.1f} dBm","> -50 Strong | -50 to -65 Medium | < -65 Weak"],
            ["Noise Floor",f"{an:.1f} dBm","Typical: -85 to -95 dBm"],
            ["Avg SNR",f"{avg_snr:.1f} dB","> 25 for MCS 9+, > 35 for MCS 10-11"],
            ["Path Loss",f"{-30-avg_rssi:.1f} dB","From -30 dBm ref at 1m"],
            ["RSSI StdDev",f"{safe_std(rssi_vals):.1f} dB","< 3 stable | > 6 unstable"]]
        story.append(make_table(ld, col_widths=[1.2*inch,1.0*inch,4.3*inch]))
    story.append(Spacer(1, 0.15*inch))
    
    # ---- Roaming ----
    story.append(Paragraph("6. Roaming & Mesh", heading_style))
    ub = len(set(bssid_history)) if bssid_history else 0
    story.append(Paragraph(f"<b>Events:</b> {len(roaming_events)} | <b>BSSIDs:</b> {ub} | {'Mesh' if ub > 1 else 'Single AP'}", body_style))
    if roaming_events:
        rt = [["#","Time","From","To"]]
        for i,e in enumerate(roaming_events[:15],1):
            rt.append([str(i),f"{e['timestamp']:.1f}",e['from_bssid'][-8:],e['to_bssid'][-8:]])
        story.append(make_table(rt))
    story.append(Spacer(1, 0.15*inch))
    
    # ---- Interference ----
    if interference_log:
        story.append(Paragraph("7. Interference Log", heading_style))
        it = {}
        for inc in interference_log:
            for iss in inc['issues']: it[iss] = it.get(iss,0)+1
        id2 = [["Issue","Count"]]
        for iss,cnt in sorted(it.items(),key=lambda x:-x[1]): id2.append([iss,str(cnt)])
        story.append(make_table(id2, col_widths=[4.5*inch,1.5*inch]))
    
    # ---- Per-Iteration Data ----
    story.append(PageBreak())
    story.append(Paragraph("8. Per-Iteration Data", heading_style))
    ih = ["#","Time","RSSI","SNR","Tx","Lat","MCS","CU%","Dist","Health"]
    idr = [ih]
    for i,row in enumerate(csv_data,1):
        ts=row[0]; rr=row[1] if len(row)>1 else None; txr=row[2] if len(row)>2 else None
        lr=row[3] if len(row)>3 else None; mr=row[4] if len(row)>4 else None
        cr=row[5] if len(row)>5 else None; sr=row[7] if len(row)>7 else None
        dr=estimate_distance(rr) if rr else None; hr=evaluate_network_health(rr,mr,txr)
        idr.append([str(i),f"{ts:.1f}",str(rr) if rr else "-",str(sr) if sr else "-",
            str(txr) if txr else "-",f"{lr:.1f}" if lr else "-",str(mr) if mr else "-",
            str(cr) if cr else "-",f"{dr:.1f}" if dr else "-",hr or "-"])
    icw=[0.3*inch,0.5*inch,0.45*inch,0.4*inch,0.55*inch,0.5*inch,0.4*inch,0.4*inch,0.45*inch,0.65*inch]
    story.append(make_table(idr, col_widths=icw, header_color='#34495E'))
    
    # ---- Snapshots ----
    if iteration_summaries:
        story.append(PageBreak())
        story.append(Paragraph("9. Periodic Analysis", heading_style))
        for s in iteration_summaries:
            story.append(Paragraph(f"<b>Iter {s['iteration']}:</b> RSSI={s['rssi']}dBm SNR={s['snr']}dB Tx={s['tx']}Mbps MCS={s['mcs']} | {s['health']}", body_style))
            if s.get('health_details'): story.append(Paragraph(f"<i>{s['health_details']}</i>", small_style))
    
    # ---- Recommendations ----
    story.append(PageBreak())
    story.append(Paragraph("10. Recommendations", heading_style))
    recs = []
    if rssi_vals and avg_rssi < -65: recs.append("RSSI below -65 dBm. Reduce distance or add mesh nodes.")
    if rssi_vals and safe_std(rssi_vals) > 6: recs.append(f"High RSSI variance ({safe_std(rssi_vals):.1f} dB).")
    if snr_vals_pdf and avg_snr < 25: recs.append(f"SNR ({avg_snr:.1f} dB) below 25 dB threshold.")
    if mcs_vals_pdf and avg_mcs < 7: recs.append(f"Avg MCS ({avg_mcs:.1f}) below 7. Not reaching 256-QAM.")
    if cu_vals and avg_cu > 60: recs.append(f"Channel util {avg_cu:.0f}%. Consider DFS or 6 GHz.")
    if len(roaming_events) > 5: recs.append(f"{len(roaming_events)} roaming events. Check AP overlap.")
    if not recs: recs.append("Performance meets 802.11ax expectations. No action required.")
    for r in recs: story.append(Paragraph(f"&bull; {r}", body_style))
    
    # ---- Plots: Generate each chart individually, one per PDF page ----
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import tempfile
    
    from reportlab.platypus import Image
    
    # Extract time-series from csv_data
    _ts = [row[0] for row in csv_data]
    _rssi = [row[1] for row in csv_data]
    _tx = [row[2] for row in csv_data]
    _lat = [row[3] for row in csv_data]
    _mcs = [row[4] for row in csv_data]
    _snr = [row[7] for row in csv_data]
    _dist = [estimate_distance(row[1]) if row[1] else None for row in csv_data]
    
    def _make_plot(plot_func, title_text, width=7.0, height=4.0):
        """Helper: render a single plot to a temp PNG and return an Image flowable."""
        fig_tmp, ax_tmp = plt.subplots(figsize=(12, 5), dpi=150, facecolor='white')
        plot_func(fig_tmp, ax_tmp)
        fig_tmp.tight_layout(rect=[0, 0, 1, 0.95])
        tmp_path = os.path.join(tempfile.gettempdir(), f'_wl_plot_{id(fig_tmp)}.png')
        fig_tmp.savefig(tmp_path, dpi=150, bbox_inches='tight')
        plt.close(fig_tmp)
        img = Image(tmp_path, width=width*inch, height=height*inch)
        img.hAlign = 'CENTER'
        return img, tmp_path
    
    tmp_files = []  # Track for cleanup
    
    # --- Plot 1: RSSI ---
    def _plot_rssi(fig, ax):
        valid = [(t, r) for t, r in zip(_ts, _rssi) if r is not None]
        if valid:
            ax.plot([v[0] for v in valid], [v[1] for v in valid], color='#E74C3C', linewidth=2.5)
            ax.axhline(y=-50, color='#27AE60', linestyle='--', alpha=0.5, label='-50 dBm (Strong)')
            ax.axhline(y=-65, color='#F39C12', linestyle='--', alpha=0.5, label='-65 dBm (Medium)')
            ax.legend(fontsize=9)
        ax.set_title("Signal Strength (RSSI) Over Time", fontsize=14, fontweight='bold')
        ax.set_xlabel("Time (s)", fontsize=12); ax.set_ylabel("RSSI (dBm)", fontsize=12, color='#E74C3C')
        ax.grid(True, alpha=0.2); ax.tick_params(labelsize=10)
    
    story.append(PageBreak())
    story.append(Paragraph("11. Diagnostic Plots", heading_style))
    img, p = _make_plot(_plot_rssi, "RSSI"); story.append(img); tmp_files.append(p)
    
    # --- Plot 2: MCS ---
    def _plot_mcs(fig, ax):
        valid = [(t, m) for t, m in zip(_ts, _mcs) if m is not None]
        if valid:
            ax.plot([v[0] for v in valid], [v[1] for v in valid], color='#3498DB', linewidth=2.5, marker='o', markersize=4)
        ax.set_title("MCS Index Over Time", fontsize=14, fontweight='bold')
        ax.set_xlabel("Time (s)", fontsize=12); ax.set_ylabel("MCS Index", fontsize=12, color='#3498DB')
        ax.set_ylim(-1, 12); ax.grid(True, alpha=0.2); ax.tick_params(labelsize=10)
    
    story.append(PageBreak())
    img, p = _make_plot(_plot_mcs, "MCS"); story.append(img); tmp_files.append(p)
    
    # --- Plot 3: SNR ---
    def _plot_snr(fig, ax):
        valid = [(t, s) for t, s in zip(_ts, _snr) if s is not None]
        # Quality zones (higher SNR = better). Bands shaded back-to-front.
        ax.axhspan(35, 70, facecolor='#27AE60', alpha=0.12, zorder=0)   # Excellent
        ax.axhspan(25, 35, facecolor='#9ACD32', alpha=0.12, zorder=0)   # Good
        ax.axhspan(15, 25, facecolor='#F1C40F', alpha=0.12, zorder=0)   # Fair
        ax.axhspan(0,  15, facecolor='#E74C3C', alpha=0.12, zorder=0)   # Poor
        if valid:
            ax.plot([v[0] for v in valid], [v[1] for v in valid], color='#2C3E50', linewidth=2.5, zorder=3)
            ax.axhline(y=25, color='#7F8C8D', linestyle='--', linewidth=1.2, alpha=0.7,
                       label='25 dB — min for high MCS')
        # Fixed, sensible scale so the axis never looks inverted/misleading
        all_snr = [v[1] for v in valid]
        top = max(60, (max(all_snr) + 5)) if all_snr else 60
        ax.set_ylim(0, top)
        ax.set_title("Signal-to-Noise Ratio (SNR) — higher is better", fontsize=14, fontweight='bold')
        ax.set_xlabel("Time (s)", fontsize=12); ax.set_ylabel("SNR (dB)", fontsize=12, color='#2C3E50')
        # Zone labels on the right edge (positions for the 0..top scale)
        ax.text(0.995, 0.80, 'Excellent', transform=ax.transAxes, ha='right', fontsize=7, color='#1E8449', fontweight='bold')
        ax.text(0.995, 0.50, 'Good',      transform=ax.transAxes, ha='right', fontsize=7, color='#5E8B00', fontweight='bold')
        ax.text(0.995, 0.33, 'Fair',      transform=ax.transAxes, ha='right', fontsize=7, color='#B7950B', fontweight='bold')
        ax.text(0.995, 0.12, 'Poor',      transform=ax.transAxes, ha='right', fontsize=7, color='#C0392B', fontweight='bold')
        ax.legend(fontsize=9, loc='upper left'); ax.grid(True, alpha=0.2); ax.tick_params(labelsize=10)
    
    img, p = _make_plot(_plot_snr, "SNR"); story.append(img); tmp_files.append(p)
    
    # --- Plot 4: Tx Rate ---
    def _plot_tx(fig, ax):
        valid = [(t, tx) for t, tx in zip(_ts, _tx) if tx is not None]
        if valid:
            ax.plot([v[0] for v in valid], [v[1] for v in valid], color='#9B59B6', linewidth=2.5)
        ax.set_title("Throughput (Tx Rate) Over Time", fontsize=14, fontweight='bold')
        ax.set_xlabel("Time (s)", fontsize=12); ax.set_ylabel("Tx Rate (Mbps)", fontsize=12, color='#9B59B6')
        ax.grid(True, alpha=0.2); ax.tick_params(labelsize=10)
    
    story.append(PageBreak())
    img, p = _make_plot(_plot_tx, "Tx"); story.append(img); tmp_files.append(p)
    
    # --- Plot 5: Latency ---
    def _plot_lat(fig, ax):
        valid = [(t, l) for t, l in zip(_ts, _lat) if l is not None]
        if valid:
            ax.plot([v[0] for v in valid], [v[1] for v in valid], color='#E67E22', linewidth=2.5)
        ax.set_title("Network Latency Over Time", fontsize=14, fontweight='bold')
        ax.set_xlabel("Time (s)", fontsize=12); ax.set_ylabel("Latency (ms)", fontsize=12, color='#E67E22')
        ax.grid(True, alpha=0.2); ax.tick_params(labelsize=10)
    
    img, p = _make_plot(_plot_lat, "Latency"); story.append(img); tmp_files.append(p)
    
    # --- Plot 6: Distance ---
    def _plot_dist(fig, ax):
        valid = [(t, d) for t, d in zip(_ts, _dist) if d is not None]
        if valid:
            ax.plot([v[0] for v in valid], [v[1] for v in valid], color='#34495E', linewidth=2.5)
        ax.set_title("Estimated Distance from AP", fontsize=14, fontweight='bold')
        ax.set_xlabel("Time (s)", fontsize=12); ax.set_ylabel("Distance (m)", fontsize=12, color='#34495E')
        ax.grid(True, alpha=0.2); ax.tick_params(labelsize=10)
    
    story.append(PageBreak())
    img, p = _make_plot(_plot_dist, "Distance"); story.append(img); tmp_files.append(p)
    
    # --- Plot 7: Rate vs Range ---
    def _plot_rate_range(fig, ax):
        valid = [(d, tx, m) for d, tx, m in zip(_dist, _tx, _mcs) if d and tx and m is not None]
        if valid:
            sorted_v = sorted(valid, key=lambda x: x[0])
            ds = [v[0] for v in sorted_v]; txs = [v[1] for v in sorted_v]; ms = [v[2] for v in sorted_v]
            bar_c = ['#27AE60' if wl_tool12_rssi > -50 else '#F1C40F' if wl_tool12_rssi >= -65 else '#E74C3C'
                     for wl_tool12_rssi in [r for r, d_v in zip(_rssi, _dist) if d_v and r is not None][:len(ds)]]
            if len(bar_c) < len(ds): bar_c = ['#9B59B6'] * len(ds)
            w = max(0.3, (ds[-1]-ds[0])/len(ds)*0.7) if len(ds) > 1 else 0.5
            ax.bar(ds, txs, width=w, color=bar_c[:len(ds)], alpha=0.7, edgecolor='white')
            ax2 = ax.twinx()
            ax2.plot(ds, ms, color='#3498DB', linewidth=2.5, marker='o', markersize=5)
            ax2.set_ylabel("MCS Index", fontsize=12, color='#3498DB'); ax2.set_ylim(-1, 12)
            ax2.tick_params(labelsize=10)
        ax.set_title("Rate vs Range (Throughput & MCS by Distance)", fontsize=14, fontweight='bold')
        ax.set_xlabel("Distance (m)", fontsize=12); ax.set_ylabel("Tx Rate (Mbps)", fontsize=12)
        ax.grid(True, alpha=0.2); ax.tick_params(labelsize=10)
    
    img, p = _make_plot(_plot_rate_range, "RateRange"); story.append(img); tmp_files.append(p)
    
    # --- Plot 8: Coverage Heatmap (if data exists) ---
    hm_path = plot_file_path.replace('.png', '_coverage_heatmap.png')
    if os.path.exists(hm_path):
        story.append(PageBreak())
        story.append(Paragraph("12. RSSI Coverage Heatmap", heading_style))
        story.append(Paragraph("AP at origin. Green > -50 dBm | Yellow -50 to -65 | Red < -65. M# = MCS at that point.", small_style))
        story.append(Spacer(1, 0.1*inch))
        try:
            img_hm = Image(hm_path, width=7.0*inch, height=3.6*inch)
            img_hm.hAlign = 'CENTER'
            story.append(img_hm)
        except Exception: pass
    
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(f"<i>Wireless Diagnostic Suite v3.0.0 | {time.strftime('%Y-%m-%d %H:%M:%S')} | IEEE 802.11ax</i>",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#AAA'), alignment=TA_CENTER)))
    
    doc.build(story)
    
    # Cleanup temp plot files
    for tf in tmp_files:
        try: os.remove(tf)
        except: pass
    
    print_success(f"PDF report generated: {pdf_report_file}")
    print_info(f"  Sections: config, summary, RF stats, MCS table, link budget, per-iteration data, plots")


def scan_networks_summary():
    """
    Scans for nearby Wi-Fi networks and returns, for each band:
      - total count
      - least crowded channel
      - most crowded channel (None if only one channel present)
      6GHz chan =  21, 37, 53, 69, 85, 101, 117, 133, 149, 165, 181, 197, 213, and 229
    """
    iface = CoreWLAN.CWInterface.interface()
    result = iface.scanForNetworksWithName_error_(None, None)
    nets = result[0] if isinstance(result, tuple) else result
    if not nets:
        return {}

    # Prepare counters
    bands = ("2.4GHz", "5GHz", "6GHz")
    band_counts = {b: 0 for b in bands}
    chan_counts = {b: Counter() for b in bands}

    # Map CoreWLAN channelBand() enums to our labels
    cw_band_map = {
        CoreWLAN.kCWChannelBand2GHz: "2.4GHz",
        CoreWLAN.kCWChannelBand5GHz: "5GHz",
        CoreWLAN.kCWChannelBand6GHz: "6GHz",
    }

    for net in nets:
        try:
            ch_obj = net.wlanChannel()
            band_enum = ch_obj.channelBand()
            band = cw_band_map.get(band_enum)
            if band is None:
                # unknown band (shouldn't happen), skip
                continue

            ch = ch_obj.channelNumber()
        except Exception:
            continue

        band_counts[band] += 1
        chan_counts[band][ch] += 1

    # Build the summary
    summary = {}
    for band in bands:
        count = band_counts[band]
        if count == 0:
            summary[band] = {
                "count": 0,
                "least_crowded_channel": None,
                "most_crowded_channel": None
            }
            continue

        channels = chan_counts[band]
        if len(channels) == 1:
            only_chan = next(iter(channels))
            least = only_chan
            most = None
        else:
            # least = channel with the smallest count
            least = min(channels.items(), key=lambda kv: kv[1])[0]
            # most = channel with the largest count
            most = max(channels.items(), key=lambda kv: kv[1])[0]

        summary[band] = {
            "count": count,
            "least_crowded_channel": least,
            "most_crowded_channel": most
        }

    return summary

''' DID NOT WORK CODE BUT GOOD TO HAVE OLD LOGIC FOR DEBUGGING LATER
def scan_networks_summary():
    """
    Scans for nearby Wi-Fi networks and returns, for each band:
      - total count
      - least crowded channel
      - most crowded channel (None if only one channel present)
    """
    iface = CoreWLAN.CWInterface.interface()
    result = iface.scanForNetworksWithName_error_(None, None)
    nets = result[0] if isinstance(result, tuple) else result
    if not nets:
        return {}

    # Initialize counters
    band_counts = {"2.4GHz": 0, "5GHz": 0, "6GHz": 0}
    chan_counts = {b: Counter() for b in band_counts}

    # Tally networks per channel per band
    for net in nets:
        try:
            ch = net.wlanChannel().channelNumber()
        except Exception:
            continue
        if ch <= 14:
            band = "2.4GHz"
        elif ch <= 165:
            band = "5GHz"
        else:
            band = "6GHz"
        band_counts[band] += 1
        chan_counts[band][ch] += 1

    # Build summary including least and most crowded channels
    summary = {}
    for band, count in band_counts.items():
        if count:
            channels = chan_counts[band]
            if len(channels) == 1:
                # Only one channel present: least is that channel, most is None
                only_chan = next(iter(channels))
                least = only_chan
                most = None
            else:
                least = min(channels.items(), key=lambda x: x[1])[0]
                most = max(channels.items(), key=lambda x: x[1])[0]
        else:
            least = None
            most = None
        summary[band] = {
            "count": count,
            "least_crowded_channel": least,
            "most_crowded_channel": most
        }
    return summary
'''

def network_sanity_check():
    global sanity_check_passed
    print_header("🔍 Network Sanity Check")
    print_info("Checking connectivity...")

    # A full download+upload speedtest here used to add 30-60s of startup
    # latency before the test could even begin — and its numbers were never
    # stored or used in the report (only the pass/fail boolean is). So we now
    # confirm connectivity with a fast TCP probe. A full speedtest is still
    # available on demand during the live loop (every 10th iteration).
    reachable = False
    for host, port in (("8.8.8.8", 53), ("1.1.1.1", 53), ("google.com", 443)):
        try:
            with contextlib.closing(socket.create_connection((host, port), timeout=2)):
                reachable = True
                break
        except Exception:
            continue

    if reachable:
        sanity_check_passed = True
        print_success("Internet connectivity confirmed.")

        summary = scan_networks_summary()
        if summary:
            print(f"\n{Colors.BOLD}📡 Nearby Wi-Fi Summary:{Colors.ENDC}")
            for band in ("2.4GHz","5GHz","6GHz"):
                s = summary[band]
                band_color = Colors.ORANGE if band == "2.4GHz" else Colors.PURPLE if band == "5GHz" else Colors.VIOLET
                print(f"  {band_color}{band}:{Colors.ENDC} {s['count']} networks | "
                      f"Least: {Colors.GREEN}Ch {s['least_crowded_channel']}{Colors.ENDC} | "
                      f"Most: {Colors.RED}Ch {s['most_crowded_channel']}{Colors.ENDC}")
        print_info("Tip: enter 'y' at the speedtest prompt during the test for a full speed measurement.")
        return True

    sanity_check_passed = False
    print_error("Network connectivity check failed")
    print_info("You can still run diagnostics, but internet-dependent features will be skipped")

    # Ask user if they want to continue
    response = input(f"\n{Colors.BOLD}{Colors.PURPLE}Continue anyway? (y/n): {Colors.ENDC}").strip().lower()
    if response == 'y':
        sanity_check_passed = True  # Allow continuation
    return response == 'y'


def estimate_distance(rssi, tx_power=-30, path_loss_exponent=2.7):
    """
    Improved RSSI to distance conversion using log-distance path loss model.
    
    Formula: Distance = 10^((TxPower - RSSI) / (10 * n))
    
    Parameters:
    - rssi: Received Signal Strength Indicator in dBm
    - tx_power: Transmit power at 1 meter (default -30 dBm for WiFi)
    - path_loss_exponent: Environment-dependent factor
      * Free space: 2.0
      * Indoor (line of sight): 2.0-2.5
      * Indoor (obstructed): 2.7-3.5
      * Indoor (heavy obstruction): 3.5-4.3
      * Default: 2.7 (typical indoor with some obstacles)
    
    Returns:
    - Distance in meters (non-negative)
    
    Note: RSSI-based distance is an estimate with ±2-3m accuracy due to:
    - Multipath interference
    - Signal reflections
    - Environmental changes
    - Device variations
    """
    if rssi is None:
        return None
    
    # Calculate distance using log-distance path loss model
    distance = 10 ** ((tx_power - rssi) / (10 * path_loss_exponent))
    
    # Ensure distance is never negative
    return max(0, distance)


# ===== FLOOR PLAN OVERLAY =====

def setup_floorplan(test_folder):
    """
    Configure floor plan overlay for heatmap visualization.
    Called after the test folder is created.
    
    Checks for default floor plan first, then asks user if they want to
    use it, change it, or skip.
    """
    global floorplan_config
    
    # Look for default floor plan in the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_path = os.path.join(script_dir, _DEFAULT_FLOORPLAN)
    
    # Also check test folder for a custom floor plan
    custom_in_folder = None
    for ext in ['png', 'jpg', 'jpeg', 'PNG', 'JPG']:
        candidate = os.path.join(test_folder, f'floorplan.{ext}')
        if os.path.exists(candidate):
            custom_in_folder = candidate
            break
    
    has_default = os.path.exists(default_path)
    
    print_header("Floor Plan Configuration")
    
    if has_default:
        print_info(f"Default floor plan found: {_DEFAULT_FLOORPLAN}")
        print_info(f"  Size: {_DEFAULT_FP_WIDTH:.0f}m × {_DEFAULT_FP_HEIGHT:.0f}m | AP at ({_DEFAULT_AP_X:.0f}m, {_DEFAULT_AP_Y:.0f}m)")
        try:
            choice = input(f"{Colors.BOLD}{Colors.CYAN}Use default floor plan? (y/n/skip): {Colors.ENDC}").strip().lower()
        except EOFError:
            choice = 'skip'
        
        if choice == 'y':
            import shutil
            dest = os.path.join(test_folder, 'floorplan.png')
            shutil.copy2(default_path, dest)
            floorplan_config.update({
                'image_path': dest,
                'width_m': _DEFAULT_FP_WIDTH,
                'height_m': _DEFAULT_FP_HEIGHT,
                'ap_x_m': _DEFAULT_AP_X,
                'ap_y_m': _DEFAULT_AP_Y,
                'enabled': True
            })
            print_success("Using default floor plan (eero office, AP near CENTO 5)")
            
            # Ask if AP position needs adjustment
            try:
                adjust = input(f"{Colors.CYAN}Adjust AP position? (Enter to keep default, or type 'x,y' in meters): {Colors.ENDC}").strip()
                if adjust and ',' in adjust:
                    parts = adjust.split(',')
                    floorplan_config['ap_x_m'] = float(parts[0].strip())
                    floorplan_config['ap_y_m'] = float(parts[1].strip())
                    print_success(f"AP position set to ({floorplan_config['ap_x_m']:.1f}m, {floorplan_config['ap_y_m']:.1f}m)")
            except (EOFError, ValueError):
                pass
            # Don't return — fall through to walk path selection
        
        elif choice == 'n':
            print_info(f"Drop your floor plan image into: {test_folder}")
            print_info("  Name it 'floorplan.png' (or .jpg)")
            try:
                input(f"{Colors.CYAN}Press Enter when the file is ready...{Colors.ENDC}")
            except EOFError:
                pass
            
            # Re-check for custom file
            for ext in ['png', 'jpg', 'jpeg', 'PNG', 'JPG']:
                candidate = os.path.join(test_folder, f'floorplan.{ext}')
                if os.path.exists(candidate):
                    custom_in_folder = candidate
                    break
            
            if custom_in_folder:
                try:
                    w = float(input(f"{Colors.CYAN}Floor plan width in meters: {Colors.ENDC}").strip())
                    h = float(input(f"{Colors.CYAN}Floor plan height in meters: {Colors.ENDC}").strip())
                    ax = float(input(f"{Colors.CYAN}AP X position from left (meters): {Colors.ENDC}").strip())
                    ay = float(input(f"{Colors.CYAN}AP Y position from top (meters): {Colors.ENDC}").strip())
                    floorplan_config.update({
                        'image_path': custom_in_folder,
                        'width_m': w, 'height_m': h,
                        'ap_x_m': ax, 'ap_y_m': ay,
                        'enabled': True
                    })
                    print_success(f"Custom floor plan loaded: {custom_in_folder}")
                    return
                except (EOFError, ValueError) as e:
                    print_warning(f"Invalid input: {e}. Skipping floor plan.")
            else:
                print_warning("No floor plan found in folder. Skipping.")
        else:
            print_info("Floor plan skipped — using radial heatmap")
    
    elif custom_in_folder:
        print_info(f"Floor plan found in test folder: {custom_in_folder}")
        try:
            w = float(input(f"{Colors.CYAN}Floor plan width in meters: {Colors.ENDC}").strip())
            h = float(input(f"{Colors.CYAN}Floor plan height in meters: {Colors.ENDC}").strip())
            ax = float(input(f"{Colors.CYAN}AP X position from left (meters): {Colors.ENDC}").strip())
            ay = float(input(f"{Colors.CYAN}AP Y position from top (meters): {Colors.ENDC}").strip())
            floorplan_config.update({
                'image_path': custom_in_folder,
                'width_m': w, 'height_m': h,
                'ap_x_m': ax, 'ap_y_m': ay,
                'enabled': True
            })
            print_success("Custom floor plan loaded")
        except (EOFError, ValueError):
            print_warning("Skipping floor plan")
    else:
        print_info("No floor plan available — using radial heatmap")
        print_info(f"  To use one, place '{_DEFAULT_FLOORPLAN}' in {script_dir}")
    
    # Walk path selection — always shown
    print()
    print_header("Walk Path Selection")
    for pid, pdata in WALK_PATHS.items():
        print(f"  {Colors.BOLD}{pid}.{Colors.ENDC} {pdata['name']}")
        print(f"     {Colors.GRAY}{pdata['description']}{Colors.ENDC}")
    
    try:
        choice = input(f"\n{Colors.BOLD}{Colors.CYAN}Select walk path (1/2/3, or Enter to skip): {Colors.ENDC}").strip()
        if choice in ('1', '2', '3'):
            pid = int(choice)
            _walk_path_config['path_id'] = pid
            _walk_path_config['waypoints'] = [(w[0], w[1], w[2]) for w in WALK_PATHS[pid]['waypoints']]
            _walk_path_config['enabled'] = True
            print_success(f"Walk path: {WALK_PATHS[pid]['name']}")
            print_info(f"  {len(_walk_path_config['waypoints'])} waypoints — loops for multiple laps")
        else:
            print_info("Walk path skipped — dots will use radial positioning")
    except (EOFError, ValueError):
        print_info("Walk path skipped")


# ===== RSSI COVERAGE HEATMAP FUNCTIONS =====

# Global storage for heatmap measurement points
heatmap_measurements = []  # List of measurement dicts
heatmap_angle_counter = 0  # Tracks angular position for radial spread

# Kalman filter state for RSSI smoothing
_kalman_state = {
    'initialized': False,
    'x': 0.0,       # Estimated RSSI (state)
    'P': 1.0,       # Estimate uncertainty (covariance)
    'R': 4.0,       # Measurement noise (RSSI variance ~4 dBm²)
    'Q': 0.5,       # Process noise (moderate — allows tracking real movement)
}

# Movement detection state
_movement_state = {
    'smoothed_distances': [],   # Kalman-filtered distance history
    'current_angle': 0.0,       # Current heading angle (radians)
    'last_distance': None,      # Previous smoothed distance
    'stationary_threshold': 1.0, # Meters — below this delta = stationary
    'angle_step': 0.4,          # Radians to advance per movement event (~23°)
}

def _kalman_filter_rssi(raw_rssi):
    """
    1D Kalman filter for RSSI smoothing.
    
    Based on the approach described by Bulten (2016) for removing noise
    from RSSI signals. The filter assumes a static system where the true
    RSSI changes slowly, and most variation is measurement noise.
    
    This dramatically reduces the ±3-6 dBm jitter that causes false
    distance changes and phantom movement on the heatmap.
    
    Reference: wouterbulten.nl/blog/tech/kalman-filters-explained-removing-noise-from-rssi-signals/
    Content was rephrased for compliance with licensing restrictions.
    """
    ks = _kalman_state
    
    if not ks['initialized']:
        ks['x'] = float(raw_rssi)
        ks['P'] = 1.0
        ks['initialized'] = True
        return ks['x']
    
    # Predict step (static model: x_t = x_{t-1} + noise)
    x_pred = ks['x']
    P_pred = ks['P'] + ks['Q']
    
    # Update step
    K = P_pred / (P_pred + ks['R'])  # Kalman gain
    ks['x'] = x_pred + K * (raw_rssi - x_pred)
    ks['P'] = (1 - K) * P_pred
    
    return ks['x']

def _detect_movement(smoothed_distance):
    """
    Determine if the user has actually moved based on smoothed distance changes.
    
    Key insight: RSSI noise causes ±1-2m jitter in distance estimates even when
    stationary. We only declare movement when the Kalman-filtered distance changes
    by more than the stationary threshold over a sliding window.
    
    Returns: (is_moving: bool, distance_delta: float)
    """
    ms = _movement_state
    
    ms['smoothed_distances'].append(smoothed_distance)
    
    # Keep a sliding window of 5 measurements
    if len(ms['smoothed_distances']) > 5:
        ms['smoothed_distances'].pop(0)
    
    if ms['last_distance'] is None:
        ms['last_distance'] = smoothed_distance
        return False, 0.0
    
    # Compare current smoothed distance to the recent average (more stable)
    if len(ms['smoothed_distances']) >= 3:
        recent_avg = sum(ms['smoothed_distances'][-3:]) / 3
        delta = abs(recent_avg - ms['last_distance'])
    else:
        delta = abs(smoothed_distance - ms['last_distance'])
    
    is_moving = delta > ms['stationary_threshold']
    
    if is_moving:
        ms['last_distance'] = smoothed_distance
    
    return is_moving, delta

def add_heatmap_measurement(distance, rssi, mcs, snr=None, tx_rate=None, phy_rate=None):
    """
    Record a measurement point for the coverage heatmap.

    Stores a composite 0-100 network performance score (blended from RSSI, SNR,
    MCS, Tx rate and PHY rate) so the map can be colored by real-world
    performance rather than a single metric.

    Two modes:
    A) Walk Path mode: position comes from the predefined walk path waypoints
       (mapped by iteration number, loops for multiple laps)
    B) Radial mode: Kalman-filtered RSSI → distance with movement detection
    """
    ms = _movement_state
    
    if distance is None or rssi is None:
        return

    # Composite real-world performance score (0-100) for this point
    score, _ = compute_network_score(rssi=rssi, snr=snr, mcs=mcs,
                                      tx_rate=tx_rate, phy_rate=phy_rate)
    
    # Kalman filter RSSI regardless of mode (for smoothed distance)
    smoothed_rssi = _kalman_filter_rssi(rssi)
    smoothed_distance = estimate_distance(smoothed_rssi)
    if smoothed_distance is None:
        smoothed_distance = distance
    
    is_moving, delta = _detect_movement(smoothed_distance)
    
    # Check if walk path provides the position
    iteration_num = len(heatmap_measurements) + 1
    walk_pos = get_walk_position(iteration_num)
    
    if walk_pos is not None and _walk_path_config['enabled']:
        # WALK PATH MODE — position from predefined waypoints
        # Coordinates are already in floor plan space (meters from top-left)
        # Store as raw x,y (the update_heatmap_plot will handle the transform)
        fp = floorplan_config
        # Convert floor plan coords to AP-relative coords for consistency
        x = walk_pos[0] - fp['ap_x_m']
        y = -(walk_pos[1] - fp['ap_y_m'])  # Flip Y back
        
        heatmap_measurements.append({
            'x': x, 'y': y,
            'distance': smoothed_distance,
            'raw_distance': distance,
            'angle': 0,
            'rssi': rssi,
            'smoothed_rssi': smoothed_rssi,
            'mcs': mcs if mcs is not None else 0,
            'snr': snr,
            'tx_rate': tx_rate,
            'phy_rate': phy_rate,
            'score': score,
            'is_moving': is_moving,
            'walk_label': walk_pos[2],
            'walk_x': walk_pos[0],
            'walk_y': walk_pos[1],
        })
    else:
        # RADIAL MODE — Kalman-filtered positioning
        if is_moving:
            angle_increment = ms['angle_step'] * max(1.0, delta / ms['stationary_threshold'])
            ms['current_angle'] += angle_increment
        
        x = smoothed_distance * np.cos(ms['current_angle'])
        y = smoothed_distance * np.sin(ms['current_angle'])
        
        heatmap_measurements.append({
            'x': x, 'y': y,
            'distance': smoothed_distance,
            'raw_distance': distance,
            'angle': ms['current_angle'],
            'rssi': rssi,
            'smoothed_rssi': smoothed_rssi,
            'mcs': mcs if mcs is not None else 0,
            'snr': snr,
            'tx_rate': tx_rate,
            'phy_rate': phy_rate,
            'score': score,
            'is_moving': is_moving
        })

def get_rssi_coverage_category(rssi, mcs):
    """
    Classify a measurement into coverage quality.
    Returns: 0=Weak, 1=Medium, 2=Strong
    
    Simple 3-zone system matching the RSSI heatmap dot colors:
    - Strong:  RSSI > -50 dBm  (green)
    - Medium:  -50 to -65 dBm  (yellow)
    - Weak:    < -65 dBm       (red)
    """
    if rssi is None:
        return 0
    if rssi > -50:
        return 2  # Strong
    elif rssi >= -65:
        return 1  # Medium
    else:
        return 0  # Weak

def update_heatmap_plot(ax_heatmap, ax_coverage):
    """
    Update the RSSI heatmap and coverage classification plots.
    
    If a floor plan is loaded, measurements are overlaid on the floor plan image
    with the AP at the configured position. Otherwise, uses the radial plot.
    
    Dots colored by RSSI: Green > -50 dBm, Yellow -50 to -65, Red < -65
    """
    if len(heatmap_measurements) < 1:
        return
    
    fp = floorplan_config
    use_floorplan = fp['enabled'] and fp['image_path'] and os.path.exists(fp['image_path'])
    
    xs_raw = np.array([m['x'] for m in heatmap_measurements])
    ys_raw = np.array([m['y'] for m in heatmap_measurements])
    rssis = np.array([m['rssi'] for m in heatmap_measurements])
    mcs_vals = np.array([m['mcs'] for m in heatmap_measurements])
    moving_flags = [m.get('is_moving', False) for m in heatmap_measurements]
    smoothed_dists = np.array([m['distance'] for m in heatmap_measurements])

    # Composite performance score per point (fall back to RSSI-only if needed)
    scores = np.array([
        (m.get('score') if m.get('score') is not None
         else (compute_network_score(rssi=m['rssi'], mcs=m.get('mcs'))[0] or 50.0))
        for m in heatmap_measurements
    ], dtype=float)
    # Session-average secondary metrics for modeling the score field
    _snr_list = [m.get('snr') for m in heatmap_measurements if m.get('snr') is not None]
    _tx_list = [m.get('tx_rate') for m in heatmap_measurements if m.get('tx_rate') is not None]
    _phy_list = [m.get('phy_rate') for m in heatmap_measurements if m.get('phy_rate') is not None]
    avg_snr = float(np.mean(_snr_list)) if _snr_list else None
    avg_tx = float(np.mean(_tx_list)) if _tx_list else None
    avg_phy = float(np.mean(_phy_list)) if _phy_list else None
    
    if use_floorplan:
        # Transform coordinates: raw (x,y) are relative to AP at origin
        # Floor plan coords: AP is at (ap_x_m, ap_y_m) from top-left
        xs = xs_raw + fp['ap_x_m']
        ys = -(ys_raw) + fp['ap_y_m']  # Flip Y (image Y goes down)
    else:
        xs = xs_raw
        ys = ys_raw
    
    move_count = sum(moving_flags)
    mostly_stationary = move_count < len(heatmap_measurements) * 0.3
    
    x_spread = np.ptp(xs) if len(xs) > 1 else 0
    y_spread = np.ptp(ys) if len(ys) > 1 else 0
    has_spread = (x_spread > 0.5 or y_spread > 0.5) and len(xs) >= 3
    
    avg_dist = np.mean(smoothed_dists)
    avg_rssi = np.mean(rssis)
    avg_mcs = int(np.mean(mcs_vals))
    avg_score = float(np.mean(scores))

    def _score_field_from_rssi(rssi_grid):
        """Map a modeled-RSSI grid to a 0-100 score field using session-average
        SNR/MCS/Tx/PHY as constant context (only RSSI varies spatially)."""
        flat = np.asarray(rssi_grid, dtype=float).ravel()
        out = np.empty_like(flat)
        for i, rv in enumerate(flat):
            sc, _ = compute_network_score(rssi=float(rv), snr=avg_snr,
                                          mcs=avg_mcs, tx_rate=avg_tx, phy_rate=avg_phy)
            out[i] = sc if sc is not None else 50.0
        return out.reshape(np.asarray(rssi_grid).shape)
    

    # ===== Helper: draw floor plan background =====
    def _draw_floorplan_bg(ax):
        """Load and display the floor plan image as background."""
        try:
            from matplotlib.image import imread
            img = imread(fp['image_path'])
            ax.imshow(img, extent=[0, fp['width_m'], fp['height_m'], 0],
                     aspect='equal', alpha=0.75, zorder=0)
            ax.set_xlim(0, fp['width_m'])
            ax.set_ylim(fp['height_m'], 0)  # Flip Y so 0 is at top
        except Exception as e:
            pass  # Silently fall back to no background
    
    def _draw_rssi_color_wash(ax):
        """Overlay a smooth RSSI gradient calibrated to the measured signal."""
        grid_res = 100
        x_grid = np.linspace(0, fp['width_m'], grid_res)
        y_grid = np.linspace(0, fp['height_m'], grid_res)
        X, Y = np.meshgrid(x_grid, y_grid)
        # Distance from AP for each grid point
        D = np.sqrt((X - fp['ap_x_m'])**2 + (Y - fp['ap_y_m'])**2)
        D = np.maximum(D, 0.1)  # Avoid log(0)
        # Reference power fitted to real measurements (not a fixed -30 dBm)
        p0 = _calibrated_ref_power(rssis, smoothed_dists)
        Z_rssi = p0 - 10 * 2.7 * np.log10(D)
        ax.contourf(X, Y, Z_rssi, levels=80, cmap=SIGNAL_CMAP, norm=SIGNAL_NORM,
                    alpha=0.6, zorder=1, antialiased=True)
    
    # ===== Plot 1: RSSI Heatmap =====
    ax_heatmap.clear()
    
    if use_floorplan:
        # FLOOR PLAN MODE
        _draw_floorplan_bg(ax_heatmap)
        _draw_rssi_color_wash(ax_heatmap)  # RSSI gradient overlay on floor plan
        
        # Draw the predefined walk path route (faint guideline)
        if _walk_path_config['enabled'] and _walk_path_config['waypoints']:
            route_xs = [w[0] for w in _walk_path_config['waypoints']]
            route_ys = [w[1] for w in _walk_path_config['waypoints']]
            ax_heatmap.plot(route_xs, route_ys, '-', lw=1.5, alpha=0.25, color='#3498DB', zorder=2)
            # Label key waypoints
            for i, (wx, wy, wlabel) in enumerate(_walk_path_config['waypoints']):
                if i == 0 or i == len(_walk_path_config['waypoints'])-1:
                    continue  # Skip start/end (same as AP)
                ax_heatmap.plot(wx, wy, 'o', color='#3498DB', markersize=3, alpha=0.3, zorder=2)
        
        # AP marker
        ax_heatmap.scatter(fp['ap_x_m'], fp['ap_y_m'], c='white', edgecolor='black',
                          s=200, marker='*', zorder=10, label='AP')
        
        # Measurement dots colored by RSSI
        ax_heatmap.scatter(xs, ys, c=rssis, cmap=SIGNAL_CMAP, norm=SIGNAL_NORM, s=55,
                          edgecolors='white', linewidth=0.8, zorder=6)
        
        # Path line connecting actual measurements
        if len(xs) > 1:
            ax_heatmap.plot(xs, ys, '-', lw=1.5, alpha=0.5, color='#2C3E50', zorder=4)
        
        # Iteration numbers + walk labels
        for i in range(len(xs)):
            label = f'{i+1}'
            # Add waypoint name if available
            if i < len(heatmap_measurements) and 'walk_label' in heatmap_measurements[i]:
                wl = heatmap_measurements[i]['walk_label']
                if wl and 'Start' not in wl and 'Return' not in wl:
                    label = f'{i+1}'  # Keep number only, label shown on route
            ax_heatmap.annotate(label, (xs[i], ys[i]), fontsize=6, ha='center', va='center',
                               color='black', fontweight='bold', zorder=7)
        
        # Distance rings from AP
        for ring_dist in [5, 10, 15, 20, 30]:
            circle = plt.Circle((fp['ap_x_m'], fp['ap_y_m']), ring_dist,
                               fill=False, color='gray', linestyle=':', linewidth=0.5, alpha=0.3)
            ax_heatmap.add_patch(circle)
        
        # Summary annotation
        path_name = WALK_PATHS.get(_walk_path_config.get('path_id', 0), {}).get('name', '') if _walk_path_config['enabled'] else ''
        summary_text = f'{len(xs)} samples | {avg_rssi:.0f}dBm avg | MCS {avg_mcs}'
        if path_name:
            summary_text = f'{path_name}\n{summary_text}'
        ax_heatmap.annotate(summary_text,
                           xy=(np.mean(xs), np.mean(ys)),
                           xytext=(0.02, 0.02), textcoords='axes fraction',
                           fontsize=7, ha='left', va='bottom', color='#2C3E50', fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='#FFF9C4', alpha=0.9, edgecolor='#F39C12'),
                           arrowprops=dict(arrowstyle='->', color='#F39C12', lw=1.2))
        
        max_dist = max(fp['width_m'], fp['height_m'])
        
    elif has_spread and not mostly_stationary:
        # MOVING MODE: Full interpolated heatmap
        margin = 2.0
        x_min = min(xs.min() - margin, -margin)
        y_min = min(ys.min() - margin, -margin)
        x_max = max(xs.max() + margin, margin)
        y_max = max(ys.max() + margin, margin)
        
        grid_res = 80
        xi = np.linspace(x_min, x_max, grid_res)
        yi = np.linspace(y_min, y_max, grid_res)
        xi_grid, yi_grid = np.meshgrid(xi, yi)
        
        try:
            zi_rssi = griddata((xs, ys), rssis, (xi_grid, yi_grid),
                               method='cubic', fill_value=np.min(rssis) - 20)
        except Exception:
            try:
                zi_rssi = griddata((xs, ys), rssis, (xi_grid, yi_grid),
                                   method='linear', fill_value=np.min(rssis) - 20)
            except Exception:
                zi_rssi = np.full_like(xi_grid, avg_rssi)
        
        ax_heatmap.contourf(xi_grid, yi_grid, zi_rssi, levels=60, cmap=SIGNAL_CMAP,
                            norm=SIGNAL_NORM, alpha=0.9, antialiased=True)
        
        # Path line
        ax_heatmap.plot(xs, ys, '--', lw=1.0, alpha=0.4, color='#2C3E50')
        
        # Movement arrows
        if len(xs) > 1:
            for i in range(len(xs) - 1):
                dx = xs[i+1] - xs[i]
                dy = ys[i+1] - ys[i]
                if abs(dx) > 0.1 or abs(dy) > 0.1:
                    color = '#27AE60' if moving_flags[i+1] else '#95A5A6'
                    ax_heatmap.annotate('', xy=(xs[i+1], ys[i+1]), xytext=(xs[i], ys[i]),
                                       arrowprops=dict(arrowstyle='->', color=color, lw=1.0, alpha=0.5))
        
        # Measurement dots colored by RSSI
        ax_heatmap.scatter(xs, ys, c=rssis, cmap=SIGNAL_CMAP, norm=SIGNAL_NORM, s=45,
                          edgecolors='white', linewidth=0.5, zorder=5)
        
        # Iteration numbers on every dot
        for i in range(len(xs)):
            ax_heatmap.annotate(f'{i+1}', (xs[i], ys[i]),
                               fontsize=7, ha='center', va='center', color='black', fontweight='bold',
                               zorder=7)
        
        # Start/End markers
        ax_heatmap.scatter(xs[0], ys[0], c='blue', marker='o', s=60, zorder=8, label=f'#1 Start')
        ax_heatmap.scatter(xs[-1], ys[-1], c='magenta', marker='X', s=60, zorder=8, label=f'#{len(xs)} End')
        
        max_dist = max(np.max(np.abs(xs)), np.max(np.abs(ys))) + margin
    else:
        # STATIONARY MODE — extend radius to show all 3 coverage zones
        # STATIONARY MODE — show the area actually surveyed, not theoretical far-field.
        # Extrapolating out to 20m always invents weak signal at the edges even when
        # the user stayed in strong signal. Keep the radius close to where measurements
        # were actually taken so the map reflects reality.
        pt_spread = max(np.max(np.abs(xs)) if len(xs) else 0,
                        np.max(np.abs(ys)) if len(ys) else 0)
        max_dist = max(avg_dist * 1.4, pt_spread + 3, 6)
        
        # Radial gradient heatmap — calibrated to measured signal
        theta = np.linspace(0, 2 * np.pi, 60)
        r_grid = np.linspace(0, max_dist, 60)
        T, R = np.meshgrid(theta, r_grid)
        X_polar = R * np.cos(T)
        Y_polar = R * np.sin(T)
        p0 = _calibrated_ref_power(rssis, smoothed_dists)
        Z_rssi = p0 - 10 * 2.7 * np.log10(np.maximum(R, 0.1))
        
        ax_heatmap.contourf(X_polar, Y_polar, Z_rssi, levels=60, cmap=SIGNAL_CMAP,
                            norm=SIGNAL_NORM, alpha=0.8, antialiased=True)
        
        # Measurement cluster dots
        ax_heatmap.scatter(xs, ys, c=rssis, cmap=SIGNAL_CMAP, norm=SIGNAL_NORM, s=55,
                          edgecolors='white', linewidth=0.8, zorder=6)
        
        # Iteration numbers on every dot
        for i in range(len(xs)):
            ax_heatmap.annotate(f'{i+1}', (xs[i], ys[i]),
                               fontsize=7, ha='center', va='center', color='black', fontweight='bold',
                               zorder=7)
        
        # Cluster summary annotation — placed OUTSIDE the circle (upper-left corner)
        ax_heatmap.annotate(f'User Position ({len(xs)} samples)\n~{avg_dist:.1f}m from AP | {avg_rssi:.0f} dBm | MCS {avg_mcs}',
                           xy=(np.mean(xs), np.mean(ys)),
                           xytext=(0.02, 0.98), textcoords='axes fraction',
                           fontsize=8, ha='left', va='top', color='#2C3E50', fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.4', facecolor='#FFF9C4', alpha=0.95, edgecolor='#F39C12', linewidth=1.2),
                           arrowprops=dict(arrowstyle='->', color='#F39C12', lw=1.5, connectionstyle='arc3,rad=0.2'))
    
    # AP marker (both modes)
    ax_heatmap.scatter(0, 0, c='white', edgecolor='black', s=150, marker='*', zorder=10, label='AP (Router)')
    
    # Distance rings
    for ring_dist in [2, 5, 10, 15, 20, 30]:
        if ring_dist < max_dist * 1.2:
            circle = plt.Circle((0, 0), ring_dist, fill=False, color='gray',
                               linestyle=':', linewidth=0.5, alpha=0.3)
            ax_heatmap.add_patch(circle)
            ax_heatmap.annotate(f'{ring_dist}m', (ring_dist * 0.7, ring_dist * 0.7),
                               fontsize=6, color='gray', alpha=0.5)
    
    # Color legend explaining the signal gradient (sampled from the smooth colormap)
    from matplotlib.lines import Line2D
    def _sig_color(dbm):
        return SIGNAL_CMAP(SIGNAL_NORM(dbm))
    color_legend = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor=_sig_color(-45), markersize=8, label='Excellent (≥ -50 dBm)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=_sig_color(-58), markersize=8, label='Good (-50 to -65)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=_sig_color(-68), markersize=8, label='Fair (-65 to -72)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=_sig_color(-80), markersize=8, label='Poor (< -72 dBm)'),
        Line2D([0], [0], marker='*', color='w', markerfacecolor='white', markeredgecolor='black', markersize=10, label='AP (Router)'),
    ]
    
    status_text = "STATIONARY" if mostly_stationary else f"MOVING ({move_count} events)"
    ax_heatmap.set_title(f"RSSI Coverage Heatmap [{status_text}]\nDot# = Iteration | Color = Signal Strength",
                         fontsize=12, fontweight='bold', pad=12)
    ax_heatmap.set_xlabel("X (m)", fontsize=11)
    ax_heatmap.set_ylabel("Y (m)", fontsize=11)
    ax_heatmap.legend(handles=color_legend, loc='upper right', fontsize=7, framealpha=0.9)
    ax_heatmap.grid(True, alpha=0.1)
    ax_heatmap.set_aspect('equal')
    ax_heatmap.tick_params(labelsize=10)
    for spine in ax_heatmap.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')
    
    # ===== Plot 2: Network Performance Score (0-100) =====
    # Composite of RSSI + SNR + MCS + Tx rate + PHY rate -> green (great) to red (bad)
    ax_coverage.clear()
    
    if use_floorplan:
        # FLOOR PLAN MODE — performance score field calibrated to measurements
        _draw_floorplan_bg(ax_coverage)
        
        grid_res = 100
        x_grid = np.linspace(0, fp['width_m'], grid_res)
        y_grid = np.linspace(0, fp['height_m'], grid_res)
        X_cov, Y_cov = np.meshgrid(x_grid, y_grid)
        D_cov = np.sqrt((X_cov - fp['ap_x_m'])**2 + (Y_cov - fp['ap_y_m'])**2)
        D_cov = np.maximum(D_cov, 0.1)
        p0_cov = _calibrated_ref_power(rssis, smoothed_dists)
        Z_rssi_cov = p0_cov - 10 * 2.7 * np.log10(D_cov)
        Z_score_cov = _score_field_from_rssi(Z_rssi_cov)
        ax_coverage.contourf(X_cov, Y_cov, Z_score_cov, levels=80,
                            cmap=SCORE_CMAP, norm=SCORE_NORM, alpha=0.6,
                            zorder=1, antialiased=True)
        
        # AP marker
        ax_coverage.scatter(fp['ap_x_m'], fp['ap_y_m'], c='black', edgecolor='white',
                          s=200, marker='*', zorder=10)
        
        # Dots colored by composite score, labeled with the score
        ax_coverage.scatter(xs, ys, c=scores, cmap=SCORE_CMAP, norm=SCORE_NORM, s=60,
                           edgecolors='white', linewidth=0.8, zorder=6)
        for i, (x, y, sv) in enumerate(zip(xs, ys, scores)):
            ax_coverage.annotate(f'{int(round(sv))}', (x, y), fontsize=5, ha='center', va='center',
                                color='black', fontweight='bold', zorder=7)
        
        # Path line
        if len(xs) > 1:
            ax_coverage.plot(xs, ys, '--', lw=1.0, alpha=0.4, color='#2C3E50', zorder=4)
    
    elif has_spread and not mostly_stationary:
        try:
            zi_score_cov = griddata((xs, ys), scores, (xi_grid, yi_grid),
                                    method='cubic', fill_value=float(np.min(scores)))
            zi_score_cov = np.clip(zi_score_cov, 0, 100)
            ax_coverage.contourf(xi_grid, yi_grid, zi_score_cov, levels=80,
                                cmap=SCORE_CMAP, norm=SCORE_NORM, alpha=0.85,
                                antialiased=True)
        except Exception:
            pass
        
        ax_coverage.plot(xs, ys, '--', lw=1.0, alpha=0.4, color='#2C3E50')
        
        # Dots with score superimposed, colored by composite score
        ax_coverage.scatter(xs, ys, c=scores, cmap=SCORE_CMAP, norm=SCORE_NORM, s=55,
                           edgecolors='white', linewidth=0.8, zorder=5)
        for i, (x, y, sv) in enumerate(zip(xs, ys, scores)):
            ax_coverage.annotate(f'{int(round(sv))}', (x, y), fontsize=6, ha='center', va='center',
                                color='black', fontweight='bold', zorder=7)
    else:
        theta = np.linspace(0, 2 * np.pi, 80)
        r_grid = np.linspace(0, max_dist, 80)
        T, R = np.meshgrid(theta, r_grid)
        X_polar = R * np.cos(T)
        Y_polar = R * np.sin(T)
        
        p0_cov = _calibrated_ref_power(rssis, smoothed_dists)
        Z_rssi_polar = p0_cov - 10 * 2.7 * np.log10(np.maximum(R, 0.1))
        Z_score_polar = _score_field_from_rssi(Z_rssi_polar)
        ax_coverage.contourf(X_polar, Y_polar, Z_score_polar,
                            levels=80, cmap=SCORE_CMAP, norm=SCORE_NORM,
                            alpha=0.8, antialiased=True)
        
        # Dots with score superimposed, colored by composite score
        ax_coverage.scatter(xs, ys, c=scores, cmap=SCORE_CMAP, norm=SCORE_NORM, s=55,
                           edgecolors='white', linewidth=1.0, zorder=6)
        for i, (x, y, sv) in enumerate(zip(xs, ys, scores)):
            ax_coverage.annotate(f'{int(round(sv))}', (x, y), fontsize=6, ha='center', va='center',
                                color='black', fontweight='bold', zorder=7)
    
    # AP marker + distance rings (radial modes only; floor-plan draws its own)
    if not use_floorplan:
        ax_coverage.scatter(0, 0, c='black', edgecolor='white', s=180, marker='*', zorder=10)
        _p0 = _calibrated_ref_power(rssis, smoothed_dists)
        d_strong = 10 ** ((_p0 - (-50)) / 27.0)   # -50 dBm boundary
        d_fair = 10 ** ((_p0 - (-65)) / 27.0)     # -65 dBm boundary
        for d_ring, lbl in [(d_strong, '-50 dBm'), (d_fair, '-65 dBm')]:
            if 0 < d_ring < max_dist * 1.2:
                cR = plt.Circle((0, 0), d_ring, fill=False, color='#34495E',
                                linewidth=1.0, linestyle='--', alpha=0.35, zorder=3)
                ax_coverage.add_patch(cR)
                ax_coverage.annotate(lbl, (d_ring * 0.7, d_ring * 0.7), fontsize=6,
                                    color='#34495E', alpha=0.6, fontweight='bold')
        for ring_dist in [2, 5, 10, 15, 20, 30]:
            if ring_dist < max_dist * 1.2:
                circle = plt.Circle((0, 0), ring_dist, fill=False, color='gray',
                                   linestyle=':', linewidth=0.4, alpha=0.25)
                ax_coverage.add_patch(circle)
    
    # Score legend using sampled swatches (lives inside axes, cleared on redraw)
    from matplotlib.lines import Line2D as _L2D
    def _scol(val):
        return SCORE_CMAP(SCORE_NORM(val))
    grad_legend = [
        _L2D([0], [0], marker='s', color='w', markerfacecolor=_scol(92), markersize=9, label='Excellent (85-100)'),
        _L2D([0], [0], marker='s', color='w', markerfacecolor=_scol(75), markersize=9, label='Good (65-85)'),
        _L2D([0], [0], marker='s', color='w', markerfacecolor=_scol(50), markersize=9, label='Fair (40-65)'),
        _L2D([0], [0], marker='s', color='w', markerfacecolor=_scol(20), markersize=9, label='Poor (< 40)'),
    ]
    ax_coverage.legend(handles=grad_legend, loc='upper right', fontsize=7, framealpha=0.9,
                       title=f'Score (avg {avg_score:.0f}/100)', title_fontsize=7)
    
    ax_coverage.set_title("Network Performance Score (0-100)\nRSSI+SNR+MCS+Tx+PHY blended · #=score at each point",
                         fontsize=12, fontweight='bold', pad=12)
    ax_coverage.set_xlabel("X (m)", fontsize=11)
    ax_coverage.set_ylabel("Y (m)", fontsize=11)
    ax_coverage.grid(True, alpha=0.08)
    ax_coverage.set_aspect('equal')
    ax_coverage.tick_params(labelsize=10)
    for spine in ax_coverage.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')


# Global variables for mobility tracking
mobility_history = []  # Store recent distance measurements
mobility_state = "Unknown"  # Current mobility state
mobility_direction = "●"  # Visual indicator


def analyze_client_mobility(current_distance, tolerance=1.5, window_size=3):
    """
    Intelligent client mobility tracking and direction analysis.
    
    Analyzes the last N distance measurements to determine if client is:
    - Moving Away (↑) - Distance increasing
    - Moving Towards (↓) - Distance decreasing  
    - Stationary (●) - Distance stable within tolerance
    
    Parameters:
    - current_distance: Current estimated distance in meters
    - tolerance: Distance variation threshold for "stationary" (default 1.5m, optimized for indoor)
    - window_size: Number of consecutive measurements to analyze (default 3)
    
    Returns:
    - state: "Moving Away", "Moving Towards", "Stationary", "Unknown"
    - direction: Visual indicator (↑, ↓, ●, ?)
    - velocity: Rate of change in m/s (positive = away, negative = towards)
    - confidence: Confidence level (0-100%)
    """
    global mobility_history, mobility_state, mobility_direction
    
    # Handle None or negative distances
    if current_distance is None or current_distance < 0:
        current_distance = 0
    
    # Add current distance to history
    mobility_history.append(current_distance)
    
    # Keep only the last window_size + 1 measurements
    if len(mobility_history) > window_size + 1:
        mobility_history.pop(0)
    
    # Need at least window_size measurements to determine trend
    if len(mobility_history) < window_size:
        return "Unknown", "?", 0.0, 0
    
    # Analyze trend over the window
    recent_distances = mobility_history[-window_size:]
    
    # Calculate differences between consecutive measurements
    differences = [recent_distances[i+1] - recent_distances[i] 
                   for i in range(len(recent_distances)-1)]
    
    # Calculate average change
    avg_change = sum(differences) / len(differences) if differences else 0
    
    # Calculate velocity (m/iteration, can be converted to m/s if sample interval known)
    velocity = avg_change
    
    # Determine if all changes are in same direction (more sensitive now)
    all_increasing = all(d > tolerance for d in differences)
    all_decreasing = all(d < -tolerance for d in differences)
    all_stable = all(abs(d) <= tolerance for d in differences)
    
    # More lenient detection: check if majority are in same direction
    increasing_count = sum(1 for d in differences if d > tolerance)
    decreasing_count = sum(1 for d in differences if d < -tolerance)
    stable_count = sum(1 for d in differences if abs(d) <= tolerance)
    
    total_changes = len(differences)
    
    # Calculate confidence based on consistency
    if all_increasing or all_decreasing or all_stable:
        confidence = 100
    else:
        # Partial confidence based on majority direction
        max_count = max(increasing_count, decreasing_count, stable_count)
        confidence = int((max_count / total_changes) * 100)
    
    # Determine state and direction with more sensitive thresholds
    # If 2 out of 2 measurements show same trend, detect it
    if all_increasing or (increasing_count >= total_changes * 0.66):
        state = "Moving Away"
        direction = "↑"
        confidence = max(confidence, int((increasing_count / total_changes) * 100))
    elif all_decreasing or (decreasing_count >= total_changes * 0.66):
        state = "Moving Towards"
        direction = "↓"
        confidence = max(confidence, int((decreasing_count / total_changes) * 100))
    elif all_stable or (stable_count >= total_changes * 0.66):
        state = "Stationary"
        direction = "●"
        confidence = max(confidence, int((stable_count / total_changes) * 100))
    else:
        # Mixed signals - use average change with lower threshold
        if abs(avg_change) <= tolerance * 0.5:  # More sensitive
            state = "Stationary"
            direction = "●"
        elif avg_change > 0:
            state = "Moving Away"
            direction = "↑"
        else:
            state = "Moving Towards"
            direction = "↓"
    
    # Update global state
    mobility_state = state
    mobility_direction = direction
    
    return state, direction, velocity, confidence


def get_mobility_summary():
    """Get a formatted summary of current mobility state"""
    global mobility_history, mobility_state, mobility_direction
    
    if len(mobility_history) < 2:
        return "Insufficient data"
    
    current_dist = mobility_history[-1]
    initial_dist = mobility_history[0]
    total_change = current_dist - initial_dist
    
    summary = f"{mobility_direction} {mobility_state}"
    if len(mobility_history) >= 3:
        summary += f" | Δ: {total_change:+.1f}m"
    
    return summary

def evaluate_network_health_advanced(recent_data):
    """
    Advanced network health evaluation using last 10 iterations
    Based on WiFi 6 (802.11ax) industry standards
    
    Parameters analyzed:
    - MCS Index: Higher is better (0-11 for WiFi 6)
    - SNR: Signal-to-Noise Ratio (dB)
    - NSS: Number of Spatial Streams (1-4)
    
    Returns: (health_score, health_status, details)
    """
    if not recent_data or len(recent_data) == 0:
        return 0, "Unknown", "Insufficient data"
    
    # Extract metrics from recent iterations
    mcs_values = [d.get('mcs') for d in recent_data if d.get('mcs') is not None]
    snr_values = [d.get('snr') for d in recent_data if d.get('snr') is not None]
    nss_values = [d.get('nss') for d in recent_data if d.get('nss') is not None and isinstance(d.get('nss'), int)]
    rssi_values = [d.get('rssi') for d in recent_data if d.get('rssi') is not None]
    
    if not mcs_values or not snr_values:
        return 0, "Unknown", "Insufficient metrics"
    
    # Calculate averages
    avg_mcs = sum(mcs_values) / len(mcs_values)
    avg_snr = sum(snr_values) / len(snr_values)
    avg_nss = sum(nss_values) / len(nss_values) if nss_values else 1
    avg_rssi = sum(rssi_values) / len(rssi_values) if rssi_values else -70
    
    score = 0
    max_score = 100
    details = []
    
    # ===== MCS Index Scoring (50 points) =====
    # User-defined thresholds:
    # MCS 8-11: Excellent
    # MCS 5-7: Good
    # MCS < 5: Poor
    
    if avg_mcs >= 8:
        mcs_score = 50  # Excellent
        details.append(f"MCS: Excellent ({avg_mcs:.1f})")
    elif avg_mcs >= 5:
        mcs_score = 35  # Good
        details.append(f"MCS: Good ({avg_mcs:.1f})")
    elif avg_mcs >= 3:
        mcs_score = 20  # Fair
        details.append(f"MCS: Fair ({avg_mcs:.1f})")
    else:
        mcs_score = 10  # Poor
        details.append(f"MCS: Poor ({avg_mcs:.1f})")
    
    score += mcs_score
    
    # ===== SNR Scoring (35 points) =====
    # Based on WiFi 6 requirements:
    # SNR >= 35dB: Excellent (supports 1024-QAM, MCS 10-11)
    # SNR >= 25dB: Good (supports 256-QAM, MCS 8-9)
    # SNR >= 20dB: Fair (supports 64-QAM, MCS 6-7)
    # SNR >= 15dB: Poor (supports 16-QAM, MCS 4-5)
    # SNR < 15dB: Very Poor
    
    if avg_snr >= 35:
        snr_score = 35
        details.append(f"SNR: Excellent ({avg_snr:.1f}dB)")
    elif avg_snr >= 25:
        snr_score = 28
        details.append(f"SNR: Good ({avg_snr:.1f}dB)")
    elif avg_snr >= 20:
        snr_score = 20
        details.append(f"SNR: Fair ({avg_snr:.1f}dB)")
    elif avg_snr >= 15:
        snr_score = 12
        details.append(f"SNR: Poor ({avg_snr:.1f}dB)")
    else:
        snr_score = 5
        details.append(f"SNR: Very Poor ({avg_snr:.1f}dB)")
    
    score += snr_score
    
    # ===== NSS Scoring (15 points) =====
    # More spatial streams = better throughput potential
    # NSS 4: Excellent (4x4 MIMO)
    # NSS 3: Good (3x3 MIMO)
    # NSS 2: Fair (2x2 MIMO)
    # NSS 1: Basic (1x1 SISO)
    
    if avg_nss >= 4:
        nss_score = 15
        details.append("NSS: Excellent (4 streams)")
    elif avg_nss >= 3:
        nss_score = 12
        details.append("NSS: Good (3 streams)")
    elif avg_nss >= 2:
        nss_score = 8
        details.append("NSS: Fair (2 streams)")
    else:
        nss_score = 4
        details.append("NSS: Basic (1 stream)")
    
    score += nss_score
    
    # Normalize score to 0-100
    score = min(max(score, 0), max_score)
    
    # Determine health status based on MCS primarily
    # Since MCS is the most important indicator
    if avg_mcs >= 8:
        status = "Excellent"
    elif avg_mcs >= 5:
        status = "Good"
    elif avg_mcs >= 3:
        status = "Fair"
    else:
        status = "Poor"
    
    # Adjust status based on overall score if needed
    if score >= 85:
        status = "Excellent"
    elif score >= 70 and status not in ["Excellent"]:
        status = "Good"
    elif score < 50:
        status = "Poor"
    
    return score, status, " | ".join(details)


def evaluate_network_health(rssi, mcs, tx):
    """Legacy simple health evaluation - kept for backward compatibility"""
    score = 0
    if rssi is not None:
        score += 3 if rssi > -50 else 2 if rssi > -65 else 1 if rssi > -80 else 0
    if tx is not None:
        score += 3 if tx > 1000 else -1 if tx < 100 else -2 if tx < 500 else 0
    if mcs is not None:
        score += 3 if mcs >= 9 else -2 if mcs >= 5 else -3 if mcs >=3 else 0
    return "Excellent" if score>=7 else "Good" if score>=1 else "Bad"

def detect_interference(rssi, noise, cu, tx_rate):
    """Advanced interference detection with specific issue identification"""
    issues = []
    if noise is not None and rssi is not None:
        snr = rssi - noise
        if snr < 15:
            issues.append(f"Low SNR ({snr}dB) - High noise floor detected")
    if cu is not None and isinstance(cu, int):
        if cu > 80:
            issues.append(f"Critical channel utilization ({cu}%) - Severe congestion")
        elif cu > 60:
            issues.append(f"High channel utilization ({cu}%) - Consider channel change")
    if tx_rate is not None and rssi is not None:
        if rssi > -60 and tx_rate < 200:
            issues.append("Good signal but low throughput - Possible interference or AP overload")
    return issues

def detect_roaming_event(current_bssid, timestamp):
    """Track AP roaming events"""
    global bssid_history, roaming_events
    if not bssid_history or bssid_history[-1] != current_bssid:
        if bssid_history:
            roaming_events.append({
                "timestamp": timestamp,
                "from_bssid": bssid_history[-1],
                "to_bssid": current_bssid
            })
            print(f"{Colors.ORANGE}⚠  ROAMING EVENT:{Colors.ENDC} {Colors.GRAY}{bssid_history[-1]}{Colors.ENDC} → {Colors.PURPLE}{current_bssid}{Colors.ENDC}")
        bssid_history.append(current_bssid)

def recommend_band_channel(summary, current_channel, current_band):
    """Provide intelligent band/channel recommendations"""
    recommendations = []
    
    # Find least congested band
    band_congestion = {b: summary[b]["count"] for b in summary}
    least_congested_band = min(band_congestion, key=band_congestion.get)
    
    if band_congestion[least_congested_band] < band_congestion.get(current_band, 999) * 0.7:
        recommendations.append(
            f"Consider switching to {least_congested_band} band "
            f"(only {band_congestion[least_congested_band]} networks vs "
            f"{band_congestion.get(current_band, 'N/A')} on current band)"
        )
    
    # Channel recommendation within current band
    if current_band in summary and summary[current_band]["least_crowded_channel"]:
        least_ch = summary[current_band]["least_crowded_channel"]
        if str(least_ch) != str(current_channel).split()[0]:
            recommendations.append(
                f"Within {current_band}, channel {least_ch} is less crowded than current channel {current_channel}"
            )
    
    return recommendations

def generate_troubleshooting_report(rssi, mcs, tx, latency, cu, noise):
    """Automated troubleshooting with actionable steps"""
    issues = []
    
    if rssi is not None and rssi < -75:
        issues.append({
            "issue": "Weak Signal Strength",
            "severity": "HIGH" if rssi < -80 else "MEDIUM",
            "steps": [
                "Move closer to the access point",
                "Check for physical obstructions (walls, metal objects)",
                "Verify AP antenna orientation",
                "Consider adding a wireless repeater or mesh node"
            ]
        })
    
    if noise is not None and rssi is not None:
        snr = rssi - noise
        if snr < 20:
            issues.append({
                "issue": f"Poor Signal-to-Noise Ratio ({snr}dB)",
                "severity": "HIGH" if snr < 15 else "MEDIUM",
                "steps": [
                    "Identify nearby interference sources (microwaves, Bluetooth, cordless phones)",
                    "Switch to a less congested channel",
                    "Enable 5GHz or 6GHz if available",
                    "Check for neighboring networks on same channel"
                ]
            })
    
    if latency is not None and latency > 100:
        issues.append({
            "issue": f"High Latency ({latency}ms)",
            "severity": "HIGH" if latency > 200 else "MEDIUM",
            "steps": [
                "Check for bandwidth-heavy applications",
                "Verify QoS settings on router",
                "Test wired connection to isolate wireless issue",
                "Check for AP CPU/memory overload"
            ]
        })
    
    if tx is not None and tx < 100:
        issues.append({
            "issue": f"Low Throughput ({tx}Mbps)",
            "severity": "HIGH",
            "steps": [
                "Verify client supports current PHY mode (802.11ac/ax)",
                "Check for rate limiting on AP",
                "Ensure proper channel width (40/80/160MHz)",
                "Update wireless drivers"
            ]
        })
    
    return issues

def export_to_json(test_name):
    """Export diagnostics data to JSON for integration"""
    
    # Analyze mesh node connections (BSSID changes indicate mesh node switches)
    mesh_nodes = {}
    for event in roaming_events:
        from_bssid = event['from_bssid']
        to_bssid = event['to_bssid']
        
        if from_bssid not in mesh_nodes:
            mesh_nodes[from_bssid] = {"connections": 0, "last_seen": 0}
        if to_bssid not in mesh_nodes:
            mesh_nodes[to_bssid] = {"connections": 0, "last_seen": 0}
        
        mesh_nodes[from_bssid]["connections"] += 1
        mesh_nodes[to_bssid]["connections"] += 1
        mesh_nodes[to_bssid]["last_seen"] = event['timestamp']
    
    # Get current BSSID
    current_bssid = bssid_history[-1] if bssid_history else "Unknown"
    
    data = {
        "test_name": test_name,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "current_connection": {
            "ssid": cached_ssid,
            "bssid": current_bssid,
            "channel": cached_chan
        },
        "mesh_analysis": {
            "total_nodes_detected": len(mesh_nodes),
            "current_node": current_bssid,
            "nodes": mesh_nodes,
            "roaming_events": roaming_events,
            "note": "BSSID changes indicate connections to different mesh nodes or APs"
        },
        "roaming_events": roaming_events,
        "interference_log": interference_log,
        "summary": {
            "total_iterations": len(csv_data),
            "total_roaming_events": len(roaming_events),
            "interference_incidents": len(interference_log),
            "unique_bssids": len(set(bssid_history)) if bssid_history else 0
        }
    }
    
    json_file = os.path.join(os.getcwd(), f"diagnostics_{test_name}.json")
    with open(json_file, "w") as f:
        json.dump(data, f, indent=2)
    
    print_success(f"JSON export saved to: {json_file}")
    print_info(f"  Mesh Analysis: {len(mesh_nodes)} unique nodes detected")
    print_info(f"  Current node (BSSID): {current_bssid}")
    if len(mesh_nodes) > 1:
        print_info(f"  ✓ Mesh network detected - {len(roaming_events)} transitions between nodes")

def export_to_csv(test_name):
    """Export comprehensive time-series data to CSV with all KPIs"""
    csv_file = os.path.join(os.getcwd(), f"diagnostics_{test_name}.csv")
    
    with open(csv_file, "w") as f:
        # Write header with all KPIs
        f.write("Iteration,Timestamp_s,SSID,Channel,BSSID,")
        f.write("RSSI_dBm,SNR_dB,Noise_dBm,")
        f.write("TxRate_Mbps,Latency_ms,")
        f.write("MCS_Index,PHY_Mode,NSS,")
        f.write("ChannelUtil_%,Distance_m,")
        f.write("Health_Status\n")
        
        # Write data rows
        iteration = 0
        for row in csv_data:
            iteration += 1
            # Unpack all data
            if len(row) >= 13:
                timestamp, rssi, tx, lat, mcs, cu, noise, snr, bssid, phy, nss, ssid, channel = row[:13]
            else:
                # Fallback for old format
                timestamp, rssi, tx, lat, mcs, cu, noise, snr, bssid = row[:9]
                phy, nss, ssid, channel = "N/A", "N/A", "N/A", "N/A"
            
            # Calculate distance
            distance = estimate_distance(rssi) if rssi else None
            distance_str = f"{distance:.2f}" if distance else "N/A"
            
            # Calculate health
            health = evaluate_network_health(rssi, mcs, tx)
            
            # Clean up PHY mode - extract just the standard (e.g., "802.11ax" -> "11ax")
            phy_str = "N/A"
            if phy and isinstance(phy, str):
                phy = phy.strip()
                if "802.11ax" in phy or "ax" in phy.lower():
                    phy_str = "11ax"
                elif "802.11ac" in phy or "ac" in phy.lower():
                    phy_str = "11ac"
                elif "802.11n" in phy or "ht" in phy.lower():
                    phy_str = "11n"
                elif "802.11a" in phy:
                    phy_str = "11a"
                elif "802.11g" in phy:
                    phy_str = "11g"
                elif "802.11b" in phy:
                    phy_str = "11b"
                else:
                    phy_str = phy
            
            # Clean up NSS - extract just the number
            nss_str = "N/A"
            if nss and isinstance(nss, str):
                nss = nss.strip()
                # Extract number from strings like "2" or "NSS: 2" or "2 streams"
                import re
                match = re.search(r'\d+', nss)
                if match:
                    nss_str = match.group(0)
                else:
                    nss_str = nss
            elif isinstance(nss, int):
                nss_str = str(nss)
            
            # Validate and clean up MCS - must be 0-12
            mcs_str = "N/A"
            if mcs is not None:
                if isinstance(mcs, int):
                    # Clamp MCS to valid range 0-12
                    if 0 <= mcs <= 12:
                        mcs_str = str(mcs)
                    else:
                        mcs_str = "N/A"  # Invalid MCS
                elif isinstance(mcs, str):
                    try:
                        mcs_int = int(mcs)
                        if 0 <= mcs_int <= 12:
                            mcs_str = str(mcs_int)
                        else:
                            mcs_str = "N/A"
                    except ValueError:
                        mcs_str = "N/A"
            
            # Clean up other values
            rssi_str = str(rssi) if rssi is not None else "N/A"
            snr_str = str(snr) if snr is not None else "N/A"
            noise_str = str(noise) if noise is not None else "N/A"
            tx_str = str(tx) if tx is not None else "N/A"
            lat_str = f"{lat:.2f}" if lat is not None else "N/A"
            
            # Clean up channel utilization - extract just the percentage number (no % or spaces)
            cu_str = "N/A"
            if cu is not None:
                if isinstance(cu, int):
                    cu_str = str(cu)
                elif isinstance(cu, str):
                    # Extract number from strings like "86%", "86 %", or "86"
                    import re
                    cu_clean = cu.strip().replace('%', '').replace(' ', '')
                    match = re.search(r'\d+', cu_clean)
                    if match:
                        cu_str = match.group(0)
                    else:
                        cu_str = "N/A"
            
            # Clean up SSID, Channel, BSSID - remove commas, newlines, and extra whitespace
            ssid_clean = str(ssid).strip().replace(',', '_').replace('\n', ' ').replace('\r', ' ') if ssid else "N/A"
            channel_clean = str(channel).strip().replace(',', '_').replace('\n', ' ').replace('\r', ' ') if channel else "N/A"
            bssid_clean = str(bssid).strip().replace(',', '_').replace('\n', ' ').replace('\r', ' ') if bssid else "N/A"
            
            # Write row
            f.write(f"{iteration},{timestamp:.2f},{ssid_clean},{channel_clean},{bssid_clean},")
            f.write(f"{rssi_str},{snr_str},{noise_str},")
            f.write(f"{tx_str},{lat_str},")
            f.write(f"{mcs_str},{phy_str},{nss_str},")
            f.write(f"{cu_str},{distance_str},")
            f.write(f"{health}\n")
    
    print_success(f"CSV export saved to: {csv_file}")
    print_info(f"  Contains {len(csv_data)} iterations with all KPIs")
    print_info(f"  Columns: Iteration, Timestamp, SSID, Channel, BSSID, RSSI, SNR, Noise,")
    print_info(f"           TxRate, Latency, MCS, PHY, NSS, ChannelUtil, Distance, Health")
    print_info(f"  Format: MCS (0-12), PHY (11ax/11ac/11n), NSS (1-4), SNR (dB)")
    print_info(f"  Open in Excel or Google Sheets for analysis")




def plot_live_diagnostics(sample_interval):
    plt.ion()
    
    # Clean, minimal style
    plt.style.use('seaborn-v0_8-whitegrid')
    
    # Presentation-quality layout: generous spacing, large figure.
    # dpi is kept modest for the *interactive* canvas (this figure is ~20x42in;
    # at 150 dpi that is a ~19 MP canvas redrawn every iteration, which is slow
    # and memory-heavy). Saved PNGs below still pass dpi=150 explicitly, so
    # exported image quality is unchanged.
    fig = plt.figure(figsize=(20, 42), dpi=100, facecolor='white')
    gs = gridspec.GridSpec(8, 2, 
                           height_ratios=[1, 1, 1, 1, 1, 1.2, 1, 0.5],
                           hspace=0.55, wspace=0.40,
                           left=0.06, right=0.94, top=0.97, bottom=0.02)
    
    ax1 = fig.add_subplot(gs[0, :])  # Full width - RSSI
    ax2 = fig.add_subplot(gs[1, 0])  # Left - MCS
    ax3 = fig.add_subplot(gs[1, 1])  # Right - SNR
    ax4 = fig.add_subplot(gs[2, :])  # Full width - Rate vs Range
    ax5 = fig.add_subplot(gs[3, 0])  # Left - Tx Rate
    ax6 = fig.add_subplot(gs[3, 1])  # Right - Latency
    ax7 = fig.add_subplot(gs[4, :])  # Full width - Distance
    ax_heatmap  = fig.add_subplot(gs[5, 0])  # Left - RSSI Heatmap
    ax_coverage = fig.add_subplot(gs[5, 1])  # Right - Coverage Zones
    ax_mcs_scatter = fig.add_subplot(gs[6, :])  # Full width - MCS vs Distance scatter
    ax8 = fig.add_subplot(gs[7, :])  # Full width - Bar chart
    
    # Clean title with AP info — fetch current connection info for header
    _init_ssid = get_ssid()
    _init_chan = get_wifi_channel()
    ap_info_line = f"AP: {ap_model}" if ap_model and ap_model != "Not specified" else ""
    ssid_info = user_provided_ssid or _init_ssid or "Unknown"
    chan_info = _init_chan or "Unknown"
    # Clean newlines from channel
    chan_info = str(chan_info).strip().replace('\n', ' ').replace('\r', '')
    
    title_lines = "Wireless Network Performance Analysis"
    subtitle = f"SSID: {ssid_info}  |  Channel: {chan_info}  |  {ap_info_line}".strip().rstrip('|').strip()
    
    fig.suptitle(title_lines, fontsize=22, fontweight='bold', color='#2C3E50', y=0.988)
    fig_subtitle = fig.text(0.5, 0.978, subtitle, ha='center', fontsize=12, color='#7F8C8D', style='italic')

    # ===== Separate Coverage Window =====
    fig_cov = plt.figure(figsize=(14, 7), dpi=100, facecolor='white', num='WiFi Coverage Map')
    gs_cov = gridspec.GridSpec(1, 2, wspace=0.35)
    ax_cov_heatmap = fig_cov.add_subplot(gs_cov[0, 0])
    ax_cov_zones = fig_cov.add_subplot(gs_cov[0, 1])
    fig_cov.suptitle("Live WiFi Coverage Map", fontsize=16, fontweight='bold', color='#2C3E50', y=0.98)
    
    # Initialize coverage window
    ax_cov_heatmap.set_title("RSSI Coverage Heatmap", fontsize=12, fontweight='bold')
    ax_cov_heatmap.scatter(0, 0, c='white', edgecolor='black', s=150, marker='*', label='AP')
    ax_cov_heatmap.legend(loc='upper right', fontsize=8)
    ax_cov_heatmap.set_aspect('equal')
    ax_cov_heatmap.grid(True, alpha=0.15)
    
    ax_cov_zones.set_title("Coverage Zones", fontsize=12, fontweight='bold')
    ax_cov_zones.scatter(0, 0, c='black', edgecolor='white', s=150, marker='*', label='AP')
    ax_cov_zones.legend(loc='upper right', fontsize=8)
    ax_cov_zones.set_aspect('equal')
    ax_cov_zones.grid(True, alpha=0.15)

    # Professional color palette - cleaner, less saturated
    color_rssi = '#E74C3C'      # Red
    color_mcs = '#3498DB'       # Blue  
    color_tx = '#9B59B6'        # Purple
    color_lat = '#E67E22'       # Orange
    color_snr = '#27AE60'       # Green
    color_dist = '#34495E'      # Dark gray
    
    # ===== Plot 1: RSSI Over Time (Clean line chart) =====
    line_rssi, = ax1.plot([],[],color=color_rssi,linewidth=2.5, alpha=0.9)
    ax1.fill_between([], [], [], color=color_rssi, alpha=0.1)
    ax1.set_xlabel("Time (s)", fontsize=12)
    ax1.set_ylabel("RSSI (dBm)", fontsize=12, color=color_rssi)
    ax1.set_title("Signal Strength Over Time", fontsize=14, fontweight='bold', pad=12)
    ax1.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
    ax1.tick_params(axis='y', labelcolor=color_rssi, labelsize=10)
    ax1.tick_params(axis='x', labelsize=10)
    for spine in ax1.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')

    # ===== Plot 2: MCS Index (Clean) =====
    line_mcs, = ax2.plot([],[],color=color_mcs,linewidth=2.5, alpha=0.9)
    ax2.set_xlabel("Time (s)", fontsize=12)
    ax2.set_ylabel("MCS Index", fontsize=12, color=color_mcs)
    ax2.set_title("Modulation & Coding Scheme", fontsize=14, fontweight='bold', pad=12)
    ax2.set_ylim(-1, 12)
    ax2.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
    ax2.tick_params(axis='y', labelcolor=color_mcs, labelsize=10)
    ax2.tick_params(axis='x', labelsize=10)
    for spine in ax2.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')

    # ===== Plot 3: SNR (Clean) — higher is better =====
    line_snr, = ax3.plot([],[],color='#2C3E50',linewidth=2.5, alpha=0.9)
    # Quality zone bands (green=excellent at top, red=poor at bottom)
    ax3.axhspan(35, 70, facecolor='#27AE60', alpha=0.12, zorder=0)
    ax3.axhspan(25, 35, facecolor='#9ACD32', alpha=0.12, zorder=0)
    ax3.axhspan(15, 25, facecolor='#F1C40F', alpha=0.12, zorder=0)
    ax3.axhspan(0,  15, facecolor='#E74C3C', alpha=0.12, zorder=0)
    ax3.axhline(y=25, color='#7F8C8D', linestyle='--', linewidth=1.2, alpha=0.7)
    ax3.set_xlabel("Time (s)", fontsize=12)
    ax3.set_ylabel("SNR (dB)", fontsize=12, color='#2C3E50')
    ax3.set_title("Signal-to-Noise Ratio (higher = better)", fontsize=14, fontweight='bold', pad=12)
    ax3.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
    ax3.tick_params(axis='y', labelcolor='#2C3E50', labelsize=10)
    ax3.tick_params(axis='x', labelsize=10)
    for spine in ax3.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')

    # ===== Plot 4: Rate vs Range — 802.11ax Performance Profile =====
    ax4.set_xlabel("Estimated Distance (m)", fontsize=12)
    ax4.set_ylabel("Tx Rate (Mbps)", fontsize=12, color=color_tx)
    ax4.set_title("802.11ax Rate vs Range Profile (Throughput & MCS by Distance)", fontsize=14, fontweight='bold', pad=12)
    ax4.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
    ax4.tick_params(axis='y', labelcolor=color_tx, labelsize=10)
    ax4.tick_params(axis='x', labelsize=10)
    
    # MCS on secondary y-axis
    ax4_mcs = ax4.twinx()
    ax4_mcs.set_ylabel("MCS Index", fontsize=12, color=color_mcs)
    ax4_mcs.tick_params(axis='y', labelcolor=color_mcs, labelsize=10)
    ax4_mcs.set_ylim(-1, 12)
    
    # RSSI zone background bands on the primary axis
    # These will be drawn during the update loop
    
    for spine in ax4.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')
    for spine in ax4_mcs.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')

    # ===== Plot 5: Tx Rate (Clean) =====
    line_tx, = ax5.plot([],[],color=color_tx,linewidth=2.5, alpha=0.9)
    ax5.set_xlabel("Time (s)", fontsize=12)
    ax5.set_ylabel("Tx Rate (Mbps)", fontsize=12, color=color_tx)
    ax5.set_title("Throughput", fontsize=14, fontweight='bold', pad=12)
    ax5.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
    ax5.tick_params(axis='y', labelcolor=color_tx, labelsize=10)
    ax5.tick_params(axis='x', labelsize=10)
    for spine in ax5.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')

    # ===== Plot 6: Latency (Clean) =====
    line_lat, = ax6.plot([],[],color=color_lat,linewidth=2.5, alpha=0.9)
    ax6.set_xlabel("Time (s)", fontsize=12)
    ax6.set_ylabel("Latency (ms)", fontsize=12, color=color_lat)
    ax6.set_title("Network Latency", fontsize=14, fontweight='bold', pad=12)
    ax6.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
    ax6.tick_params(axis='y', labelcolor=color_lat, labelsize=10)
    ax6.tick_params(axis='x', labelsize=10)
    for spine in ax6.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')

    # ===== Plot 7: Distance Over Time =====
    line_dist, = ax7.plot([],[],color=color_dist,linewidth=2.5, alpha=0.9)
    ax7.fill_between([], [], [], color=color_dist, alpha=0.1)
    ax7.set_xlabel("Time (s)", fontsize=12)
    ax7.set_ylabel("Distance (m)", fontsize=12, color=color_dist)
    ax7.set_title("Estimated Distance from Access Point", fontsize=14, fontweight='bold', pad=12)
    ax7.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
    ax7.tick_params(axis='y', labelcolor=color_dist, labelsize=10)
    ax7.tick_params(axis='x', labelsize=10)
    for spine in ax7.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')

    # ===== RSSI Coverage Heatmap (initially empty) =====
    ax_heatmap.set_title("RSSI Coverage Heatmap", fontsize=14, fontweight='bold', pad=12)
    ax_heatmap.set_xlabel("X (m)", fontsize=11)
    ax_heatmap.set_ylabel("Y (m)", fontsize=11)
    ax_heatmap.scatter(0, 0, c='white', edgecolor='black', s=150, marker='*', zorder=10, label='AP')
    ax_heatmap.legend(loc='upper right', fontsize=9)
    ax_heatmap.set_aspect('equal')
    ax_heatmap.grid(True, alpha=0.15)
    ax_heatmap.tick_params(labelsize=10)
    for spine in ax_heatmap.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')
    
    # ===== Coverage Zone Map (initially empty) =====
    ax_coverage.set_title("Coverage Zones (RSSI + MCS)", fontsize=14, fontweight='bold', pad=12)
    ax_coverage.set_xlabel("X (m)", fontsize=11)
    ax_coverage.set_ylabel("Y (m)", fontsize=11)
    ax_coverage.scatter(0, 0, c='black', edgecolor='white', s=150, marker='*', zorder=10, label='AP')
    ax_coverage.legend(loc='upper right', fontsize=9)
    ax_coverage.set_aspect('equal')
    ax_coverage.grid(True, alpha=0.15)
    ax_coverage.tick_params(labelsize=10)
    for spine in ax_coverage.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')
    
    # ===== MCS at Distance Scatter Plot =====
    ax_mcs_scatter.set_title("MCS Index at Each RSSI / Distance", fontsize=14, fontweight='bold', pad=12)
    ax_mcs_scatter.set_xlabel("Estimated Distance (m)", fontsize=12)
    ax_mcs_scatter.set_ylabel("MCS Index", fontsize=12, color='#3498DB')
    ax_mcs_scatter.set_ylim(-1, 13)
    ax_mcs_scatter.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
    ax_mcs_scatter.tick_params(labelsize=10)
    ax_mcs_scatter_rssi = ax_mcs_scatter.twinx()
    ax_mcs_scatter_rssi.set_ylabel("RSSI (dBm)", fontsize=12, color='#E74C3C')
    ax_mcs_scatter_rssi.tick_params(axis='y', labelcolor='#E74C3C', labelsize=10)
    for spine in ax_mcs_scatter.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')

    # ===== Plot 8: Network Summary Bar Chart (Clean) =====
    ax8.set_title("Nearby WiFi Networks by Band", fontsize=14, fontweight='bold', pad=12)
    ax8.set_xlabel("Frequency Band", fontsize=12)
    ax8.set_ylabel("Network Count", fontsize=12)
    ax8.grid(True, alpha=0.2, linestyle='-', linewidth=0.5, axis='y')
    ax8.tick_params(labelsize=9)
    for spine in ax8.spines.values():
        spine.set_linewidth(0.5)
        spine.set_color('#CCCCCC')

    # Adjust layout
    plt.tight_layout(rect=[0, 0, 1, 0.99])

    x_vals, r_vals, t_vals = [],[],[]
    lat_vals, mcs_vals, snr_vals = [],[],[]
    dist_vals = []  # Distance values
    iteration = 0
    start = time.time()

    cached_ssid = get_ssid()
    cached_chan = get_wifi_channel()
    gi = get_guard_interval()  # Guard interval (800/1600/3200 ns)
    try:
        if cached_chan and cached_chan != "Unknown":
            chan_num = int(cached_chan.split()[0])
            current_band = "6GHz" if chan_num > 165 else "5GHz" if chan_num > 14 else "2.4GHz"
        else:
            current_band = "Unknown"
    except (ValueError, IndexError):
        current_band = "Unknown"

    print_header("Live diagnostics running. Type 'q' then Enter to quit.")
    while not exit_requested:
        iteration += 1
        
        # Print iteration header with color
        iter_color = Colors.PURPLE if iteration % 10 == 0 else Colors.GRAY
        print(f"\n{iter_color}{'─'*80}{Colors.ENDC}")
        print(f"{Colors.BOLD}{iter_color}Iteration {iteration}{Colors.ENDC} {Colors.GRAY}| Time: {time.time() - start:.1f}s{Colors.ENDC}")
        print(f"{iter_color}{'─'*80}{Colors.ENDC}")

        now = time.time() - start
        x_vals.append(now)

        # Single wdutil snapshot for this whole iteration. Every get_* metric
        # helper below reads from this cache instead of spawning its own
        # `sudo wdutil info` subprocess (was 8-9 shells per iteration).
        refresh_wdutil_info()

        if iteration % 5 == 0:
            cached_ssid = get_ssid()
            cached_chan = get_wifi_channel()

        stats = get_wifi_stats()
        if "Error" in stats:
            print(stats["Error"])
            break

        rssi = stats["RSSI"]
        tx   = stats["Tx Rate"]
        mcs  = stats["MCS Index"]
        if not isinstance(mcs, int):
            mcs = None

        lat = run_ping_test()
        phy = get_phy()
        nss = get_nss()
        cu  = get_channel_utilization()
        noise = get_noise_floor()
        bssid = get_bssid()
        
        # Calculate SNR = RSSI - Noise (both dBm). Guard against bad inputs:
        # SNR must be non-negative and within a realistic 0..70 dB range.
        snr = None
        if rssi is not None and noise is not None:
            _snr_calc = rssi - noise
            if 0 <= _snr_calc <= 70:
                snr = _snr_calc
        
        # Retransmission & packet error measurement
        retx_stats = get_retransmission_stats()
        
        # Real throughput measurement (netstat byte counters)
        real_tp = get_real_throughput()
        
        # 802.11ax theoretical PHY rate calculation
        # GI changes rarely — only fetch every 5 iterations (same as channel)
        if iteration == 1 or iteration % 5 == 0:
            gi = get_guard_interval()
        # Parse bandwidth from channel string
        _bw = 80  # default
        if cached_chan:
            if '160' in str(cached_chan): _bw = 160
            elif '80' in str(cached_chan): _bw = 80
            elif '40' in str(cached_chan): _bw = 40
            else: _bw = 20
        # Parse NSS as integer
        _nss_int = 1
        if nss:
            _nss_m = re.search(r'\d+', str(nss))
            if _nss_m: _nss_int = int(_nss_m.group(0))
        phy_calc = calculate_80211ax_phy_rate(mcs, _nss_int, _bw, gi)
        
        # Detect roaming
        detect_roaming_event(bssid, now)
        
        # Interference detection
        interference = detect_interference(rssi, noise, cu, tx)
        if interference:
            interference_log.append({"timestamp": now, "issues": interference})
            for issue in interference:
                print(f"{Colors.WARNING}⚠  INTERFERENCE:{Colors.ENDC} {issue}")
        
        if isinstance(cu, int) and cu > 60:
            cu_color = Colors.RED if cu > 80 else Colors.YELLOW
            print(f"{cu_color}⚠  High channel utilization detected: {cu}%{Colors.ENDC}")

        if iteration % 10 == 0:
            try:
                run_st = input(f"\n{Colors.BOLD}{Colors.CYAN}Run speedtest? (y/n): {Colors.ENDC}").strip().lower()
            except EOFError:
                run_st = 'n'
            if run_st == 'y':
                print_header(f"📊 SPEEDTEST - Iteration {iteration}")
                ping, dl, ul = get_speedtest()
                if dl is not None:
                    print_success(f"Speedtest complete: ↓ {dl:.2f} Mbps | ↑ {ul:.2f} Mbps | Ping: {ping:.1f}ms")
                else:
                    print_warning("Speedtest skipped or failed")
            else:
                print_info("Speedtest skipped")

        dist = estimate_distance(rssi) if rssi is not None else None
        
        # Analyze client mobility
        mobility_state, mobility_dir, velocity, confidence = analyze_client_mobility(dist)

        r_vals.append(rssi)
        t_vals.append(tx)
        lat_vals.append(lat)
        mcs_vals.append(mcs)
        snr_vals.append(snr)
        dist_vals.append(dist)  # Track distance
        
        # Store comprehensive data for CSV export (including PHY and NSS)
        csv_data.append([now, rssi, tx, lat, mcs, cu, noise, snr, bssid, phy, nss, cached_ssid, cached_chan])
        
        # Record measurement for the coverage heatmap (composite score uses all metrics)
        add_heatmap_measurement(dist, rssi, mcs, snr=snr, tx_rate=tx,
                                phy_rate=phy_calc.get('phy_rate_mbps'))

        # Print metrics with colors
        rssi_color = get_rssi_color(rssi)
        snr_color = get_snr_color(snr)
        
        dist_str = f"{dist:.2f}m" if dist is not None else "N/A"
        snr_str = f"{snr}dB" if snr is not None else "N/A"
        
        # Mobility color coding
        if mobility_state == "Moving Away":
            mobility_color = Colors.ORANGE
        elif mobility_state == "Moving Towards":
            mobility_color = Colors.GREEN
        elif mobility_state == "Stationary":
            mobility_color = Colors.TEAL
        else:
            mobility_color = Colors.GRAY
        
        print(f"{Colors.BOLD}Metrics:{Colors.ENDC}")
        print(f"  SSID: {Colors.PURPLE}{cached_ssid}{Colors.ENDC} | Channel: {Colors.PURPLE}{cached_chan}{Colors.ENDC}")
        print(f"  RSSI: {rssi_color}{rssi}dBm{Colors.ENDC} | SNR: {snr_color}{snr_str}{Colors.ENDC} | Distance: {Colors.ORANGE}~{dist_str}{Colors.ENDC}")
        print(f"  Tx Rate: {Colors.GREEN}{tx}Mbps{Colors.ENDC} | Latency: {Colors.TEAL}{lat}ms{Colors.ENDC} | MCS: {Colors.VIOLET}{mcs}{Colors.ENDC}")
        print(f"  PHY: {Colors.BLUE}{phy}{Colors.ENDC} | NSS: {Colors.BLUE}{nss}{Colors.ENDC} | CU: {Colors.ORANGE}{cu}%{Colors.ENDC}")
        print(f"  BSSID: {Colors.GRAY}{bssid}{Colors.ENDC}")
        print(f"  Mobility: {mobility_color}{mobility_dir} {mobility_state}{Colors.ENDC} | Confidence: {Colors.CYAN}{confidence}%{Colors.ENDC}")
        
        # Retransmission display
        retx_color = Colors.GREEN if retx_stats['status'] == 'Good' else (Colors.YELLOW if retx_stats['status'] == 'Fair' else Colors.RED if retx_stats['status'] == 'Poor' else Colors.GRAY)
        print(f"  Retx: {retx_color}TCP={retx_stats['tcp_retx_delta']} | IF Err={retx_stats['if_err_rate']}% | Pkts={retx_stats['pkt_out_delta']} | {retx_stats['status']}{Colors.ENDC}")
        
        # Real throughput display
        tp_color = Colors.GREEN if real_tp['total_mbps'] > 50 else (Colors.YELLOW if real_tp['total_mbps'] > 5 else Colors.GRAY)
        # Calculate link efficiency: actual throughput vs PHY rate
        efficiency = (real_tp['total_mbps'] / tx * 100) if (tx and tx > 0 and real_tp['total_mbps'] > 0) else 0
        eff_color = Colors.GREEN if efficiency > 50 else (Colors.YELLOW if efficiency > 20 else Colors.RED if efficiency > 0 else Colors.GRAY)
        print(f"  Throughput: {tp_color}Rx={real_tp['rx_mbps']:.1f} Mbps | Tx={real_tp['tx_mbps']:.1f} Mbps | Total={real_tp['total_mbps']:.1f} Mbps{Colors.ENDC} | Efficiency: {eff_color}{efficiency:.0f}%{Colors.ENDC}")
        
        # Estimated link throughput from 802.11ax PHY rate
        if phy_calc['phy_rate_mbps'] > 0:
            phy_color = Colors.GREEN if phy_calc['phy_rate_mbps'] > 500 else (Colors.YELLOW if phy_calc['phy_rate_mbps'] > 100 else Colors.RED)
            print(f"  Est. Link: {phy_color}{phy_calc['phy_rate_mbps']:.0f} Mbps PHY → ~{phy_calc['est_throughput_mbps']:.0f} Mbps throughput{Colors.ENDC} | {Colors.GRAY}{phy_calc['modulation']} {phy_calc['coding_rate']} × {_nss_int}SS × {_bw}MHz GI={gi}ns{Colors.ENDC}")
        
        log_line=(f"Iter:{iteration} | Time:{now:.2f}s | SSID:{cached_ssid} | Chan:{cached_chan} | "
                  f"CU:{cu}% | RSSI:{rssi}dB | SNR:{snr_str} | Dist:{dist_str} | Mobility:{mobility_state} | "
                  f"Tx:{tx}Mbps | Lat:{lat}ms | MCS:{mcs} | PHY:{phy} | NSS:{nss} | BSSID:{bssid}")
        log_to_file(log_line)

        # Update all plots
        line_rssi.set_data(x_vals, r_vals)
        line_mcs.set_data(x_vals, mcs_vals)
        line_tx.set_data(x_vals, t_vals)
        line_lat.set_data(x_vals, lat_vals)
        line_snr.set_data(x_vals, snr_vals)
        line_dist.set_data(x_vals, dist_vals)
        
        # Update Rate vs Range plot — 802.11ax Performance Profile
        valid_data = [(d, m, s, t, r) for d, m, s, t, r in 
                      zip(dist_vals, mcs_vals, snr_vals, t_vals, r_vals)
                      if d is not None and m is not None and s is not None 
                      and t is not None and r is not None]
        if valid_data:
            sorted_data = sorted(valid_data, key=lambda x: x[0])
            dist_sorted = [x[0] for x in sorted_data]
            mcs_sorted = [x[1] for x in sorted_data]
            snr_sorted = [x[2] for x in sorted_data]
            tx_sorted = [x[3] for x in sorted_data]
            rssi_sorted = [x[4] for x in sorted_data]
            
            ax4.clear()
            ax4_mcs.clear()
            
            # Tx Rate as bar chart (primary y-axis)
            bar_colors = []
            for r_val in rssi_sorted:
                if r_val > -30: bar_colors.append('#27AE60')
                elif r_val >= -55: bar_colors.append('#2ECC71')
                elif r_val >= -67: bar_colors.append('#F1C40F')
                elif r_val >= -75: bar_colors.append('#E67E22')
                else: bar_colors.append('#E74C3C')
            
            ax4.bar(dist_sorted, tx_sorted, width=max(0.3, (max(dist_sorted) - min(dist_sorted)) / len(dist_sorted) * 0.7),
                   color=bar_colors, alpha=0.7, edgecolor='white', linewidth=0.5, label='Tx Rate (Mbps)')
            
            # MCS as line on secondary y-axis
            ax4_mcs.plot(dist_sorted, mcs_sorted, color='#3498DB', linewidth=2.5, marker='o',
                        markersize=6, label='MCS Index', zorder=5)
            
            # Annotate MCS values
            for i, (d, m) in enumerate(zip(dist_sorted, mcs_sorted)):
                ax4_mcs.annotate(f'{m}', (d, m), fontsize=7, ha='center', va='bottom',
                                color='#2C3E50', fontweight='bold', xytext=(0, 4), textcoords='offset points')
            
            ax4.set_xlabel("Estimated Distance (m)", fontsize=12)
            ax4.set_ylabel("Tx Rate (Mbps)", fontsize=12, color=color_tx)
            ax4.set_title("802.11ax Rate vs Range Profile (Throughput & MCS by Distance)",
                         fontsize=14, fontweight='bold', pad=12)
            ax4.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
            ax4.tick_params(axis='y', labelcolor=color_tx, labelsize=10)
            ax4.tick_params(axis='x', labelsize=10)
            ax4.set_xlim(0, max(dist_sorted) + 1)
            
            ax4_mcs.set_ylabel("MCS Index", fontsize=12, color=color_mcs)
            ax4_mcs.tick_params(axis='y', labelcolor=color_mcs, labelsize=10)
            ax4_mcs.set_ylim(-1, 12)
            
            # Combined legend
            from matplotlib.lines import Line2D as _L2D
            legend_elements = [
                mpatches.Patch(facecolor='#2ECC71', alpha=0.7, label='Tx Rate (Mbps)'),
                _L2D([0], [0], color='#3498DB', linewidth=2.5, marker='o', label='MCS Index'),
            ]
            ax4.legend(handles=legend_elements, loc='upper right', fontsize=9, framealpha=0.9)
            
            for spine in ax4.spines.values():
                spine.set_linewidth(0.5)
                spine.set_color('#CCCCCC')
        
        # Update RSSI Coverage Heatmap and Coverage Zones (every 2 iterations to save CPU)
        if iteration % 2 == 0 and len(heatmap_measurements) >= 1:
            try:
                update_heatmap_plot(ax_heatmap, ax_coverage)
                # Also update the separate coverage window
                update_heatmap_plot(ax_cov_heatmap, ax_cov_zones)
                fig_cov.canvas.draw_idle()
                fig_cov.canvas.flush_events()
            except Exception as e:
                pass  # Silently handle interpolation errors during early iterations
        
        # Update MCS at Distance scatter plot
        if valid_data:
            ax_mcs_scatter.clear()
            ax_mcs_scatter_rssi.clear()
            
            valid_scatter = [(d, m, r) for d, m, r in zip(dist_vals, mcs_vals, r_vals)
                            if d is not None and m is not None and r is not None]
            if valid_scatter:
                sc_dist = [x[0] for x in valid_scatter]
                sc_mcs = [x[1] for x in valid_scatter]
                sc_rssi = [x[2] for x in valid_scatter]
                
                # MCS dots (left y-axis) - colored by RSSI
                scatter_mcs = ax_mcs_scatter.scatter(sc_dist, sc_mcs, c=sc_rssi, cmap='RdYlGn',
                                                      s=50, edgecolors='white', linewidth=0.5,
                                                      zorder=5, vmin=-80, vmax=-30)
                
                # RSSI line (right y-axis)
                dist_rssi_sorted = sorted(zip(sc_dist, sc_rssi), key=lambda x: x[0])
                ax_mcs_scatter_rssi.plot([x[0] for x in dist_rssi_sorted], 
                                         [x[1] for x in dist_rssi_sorted],
                                         color='#E74C3C', linewidth=1.5, alpha=0.6, linestyle='--')
                
                # Annotate latest point
                ax_mcs_scatter.annotate(f'MCS {sc_mcs[-1]}\n{sc_rssi[-1]}dBm',
                                       (sc_dist[-1], sc_mcs[-1]),
                                       fontsize=7, ha='left', va='bottom',
                                       color='#2C3E50', fontweight='bold',
                                       bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', 
                                                alpha=0.8, edgecolor='none'))
                
                # Coverage zone background bands
                ax_mcs_scatter.axhspan(7, 13, alpha=0.08, color='green', label='Excellent MCS')
                ax_mcs_scatter.axhspan(3, 7, alpha=0.08, color='yellow', label='Good MCS')
                ax_mcs_scatter.axhspan(-1, 3, alpha=0.08, color='red', label='Poor MCS')
                
                ax_mcs_scatter.set_title("MCS Index at Each RSSI / Distance", fontsize=14, fontweight='bold', pad=12)
                ax_mcs_scatter.set_xlabel("Estimated Distance (m)", fontsize=12)
                ax_mcs_scatter.set_ylabel("MCS Index", fontsize=12, color='#3498DB')
                ax_mcs_scatter.set_ylim(-1, 13)
                ax_mcs_scatter.set_xlim(0, max(sc_dist) + 2)
                ax_mcs_scatter.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
                ax_mcs_scatter.tick_params(labelsize=10)
                ax_mcs_scatter.legend(loc='upper right', fontsize=9, framealpha=0.9)
                
                ax_mcs_scatter_rssi.set_ylabel("RSSI (dBm)", fontsize=12, color='#E74C3C')
                ax_mcs_scatter_rssi.tick_params(axis='y', labelcolor='#E74C3C', labelsize=10)
                
                for spine in ax_mcs_scatter.spines.values():
                    spine.set_linewidth(0.5)
                    spine.set_color('#CCCCCC')

        # Set x-axis limits (rolling window)
        x_min, x_max = max(0, now-60), now+5
        ax1.set_xlim(x_min, x_max)
        ax2.set_xlim(x_min, x_max)
        ax3.set_xlim(x_min, x_max)
        ax5.set_xlim(x_min, x_max)
        ax6.set_xlim(x_min, x_max)
        ax7.set_xlim(x_min, x_max)

        # Set y-axis limits
        if r_vals:
            valid_rssi = [v for v in r_vals if v is not None]
            if valid_rssi:
                ax1.set_ylim(min(valid_rssi)-5, max(valid_rssi)+5)
        
        if t_vals:
            valid_tx = [v for v in t_vals if v is not None]
            if valid_tx:
                ax5.set_ylim(min(valid_tx)-50, max(valid_tx)+50)
        
        if lat_vals:
            valid_lat = [v for v in lat_vals if v is not None]
            if valid_lat:
                ax6.set_ylim(min(valid_lat)-5, max(valid_lat)+10)
                
        if snr_vals:
            valid_snr = [s for s in snr_vals if s is not None]
            if valid_snr:
                # Fixed floor at 0 so quality zones stay meaningful (never inverted-looking)
                ax3.set_ylim(0, max(60, max(valid_snr) + 5))
                
        if dist_vals:
            valid_dist = [d for d in dist_vals if d is not None]
            if valid_dist:
                ax7.set_ylim(0, max(valid_dist)+2)
                
        # Every 10 iterations: comprehensive analysis
        if iteration % 10 == 0:
            print_header(f"📊 COMPREHENSIVE ANALYSIS - Iteration {iteration}")
            
            # Client Mobility Summary
            mobility_summary = get_mobility_summary()
            print(f"{Colors.BOLD}🚶 Client Mobility:{Colors.ENDC} {mobility_color}{mobility_summary}{Colors.ENDC}\n")
            
            # Use advanced health evaluation with last 10 iterations
            recent_iterations = []
            start_idx = max(0, len(csv_data) - 10)
            for row in csv_data[start_idx:]:
                # Extract NSS as integer if possible
                nss_val = None
                if len(row) > 10:
                    try:
                        nss_str = str(row[10]).strip()
                        nss_val = int(nss_str) if nss_str.isdigit() else None
                    except:
                        pass
                
                recent_iterations.append({
                    'rssi': row[1] if len(row) > 1 else None,
                    'tx': row[2] if len(row) > 2 else None,
                    'mcs': row[4] if len(row) > 4 else None,
                    'snr': row[7] if len(row) > 7 else None,
                    'nss': nss_val
                })
            
            health_score, health, health_details = evaluate_network_health_advanced(recent_iterations)
            health_color = get_health_color(health)
            
            print(f"{Colors.BOLD}🏥 Network Health:{Colors.ENDC} {health_color}{health} ({health_score}/100){Colors.ENDC}")
            print(f"{Colors.GRAY}   {health_details}{Colors.ENDC}\n")

            summary = scan_networks_summary()
            
            # Store iteration summary for PDF report
            iteration_summary = {
                'iteration': iteration,
                'rssi': rssi,
                'snr': snr,
                'tx': tx,
                'latency': lat,
                'mcs': mcs,
                'cu': cu,
                'health': f"{health} ({health_score}/100)",
                'health_details': health_details,
                'issues': [],
                'recommendations': []
            }
            
            if summary:
                print(f"{Colors.BOLD}📡 Nearby Wi-Fi Networks:{Colors.ENDC}")
                for band in ("2.4GHz","5GHz","6GHz"):
                    s = summary[band]
                    band_color = Colors.ORANGE if band == "2.4GHz" else Colors.PURPLE if band == "5GHz" else Colors.VIOLET
                    print(f"  {band_color}{band}:{Colors.ENDC} {s['count']} networks | "
                          f"Least crowded: {Colors.GREEN}Ch {s['least_crowded_channel']}{Colors.ENDC} | "
                          f"Most crowded: {Colors.RED}Ch {s['most_crowded_channel']}{Colors.ENDC}")
                
                # Band/channel recommendations
                recommendations = recommend_band_channel(summary, cached_chan, current_band)
                if recommendations:
                    print(f"\n{Colors.BOLD}💡 RECOMMENDATIONS:{Colors.ENDC}")
                    for rec in recommendations:
                        print(f"  {Colors.GREEN}•{Colors.ENDC} {rec}")
                        iteration_summary['recommendations'].append(rec)
            
            # Troubleshooting report
            issues = generate_troubleshooting_report(rssi, mcs, tx, lat, cu, noise)
            if issues:
                print(f"\n{Colors.BOLD}🔧 TROUBLESHOOTING GUIDE:{Colors.ENDC}")
                for issue in issues:
                    severity_color = Colors.RED if issue['severity'] == 'HIGH' else Colors.YELLOW
                    print(f"\n  {severity_color}⚠  {issue['issue']} [Severity: {issue['severity']}]{Colors.ENDC}")
                    print(f"  {Colors.BOLD}Steps to resolve:{Colors.ENDC}")
                    for step in issue['steps']:
                        print(f"    {Colors.CYAN}→{Colors.ENDC} {step}")
                    iteration_summary['issues'].append(f"{issue['issue']} ({issue['severity']})")
            
            # Store summary
            iteration_summaries.append(iteration_summary)
            
            # Roaming summary with mesh node detection
            if roaming_events:
                roam_color = Colors.RED if len(roaming_events) > 3 else Colors.ORANGE
                unique_bssids = len(set(bssid_history))
                print(f"\n{Colors.BOLD}🔄 Roaming & Mesh Analysis:{Colors.ENDC}")
                print(f"  Total roaming events: {roam_color}{len(roaming_events)}{Colors.ENDC}")
                print(f"  Unique nodes/APs: {Colors.PURPLE}{unique_bssids}{Colors.ENDC}")
                
                if unique_bssids > 1:
                    print(f"  {Colors.GREEN}✓ Mesh network detected{Colors.ENDC} - Connected to {unique_bssids} different nodes")
                    print(f"  Current node (BSSID): {Colors.PURPLE}{bssid}{Colors.ENDC}")
                    
                    # Show recent roaming history
                    if len(roaming_events) > 0:
                        print(f"\n  {Colors.BOLD}Recent transitions:{Colors.ENDC}")
                        for event in roaming_events[-3:]:  # Show last 3
                            print(f"    {Colors.GRAY}{event['from_bssid'][-8:]}{Colors.ENDC} → "
                                  f"{Colors.PURPLE}{event['to_bssid'][-8:]}{Colors.ENDC} "
                                  f"at {event['timestamp']:.1f}s")
                
                if len(roaming_events) > 3:
                    print(f"  {Colors.ORANGE}⚠  Frequent roaming - may indicate coverage issues{Colors.ENDC}")
            else:
                print(f"\n{Colors.BOLD}🔄 Roaming & Mesh Analysis:{Colors.ENDC}")
                print(f"  No roaming events detected")
                print(f"  Connected to single node: {Colors.PURPLE}{bssid}{Colors.ENDC}")
            
            print(f"\n{Colors.PURPLE}{'='*80}{Colors.ENDC}\n")

            # Update band chart
            bands  = ["2.4GHz","5GHz","6GHz"]
            counts = [summary[b]["count"] for b in bands]
            leasts = [summary[b]["least_crowded_channel"] for b in bands]

            ax8.clear()
            # Clean bar chart
            colors_bars = ['#E67E22', '#9B59B6', '#3498DB']  # Orange, Purple, Blue
            bars = ax8.bar(bands, counts, color=colors_bars, edgecolor='#2C3E50', linewidth=1.5, alpha=0.85)
            ax8.set_title("Nearby WiFi Networks by Band", fontsize=12, fontweight='bold', pad=10)
            ax8.set_xlabel("Frequency Band", fontsize=10)
            ax8.set_ylabel("Network Count", fontsize=10)
            ax8.grid(True, alpha=0.2, linestyle='-', linewidth=0.5, axis='y')
            ax8.tick_params(labelsize=9)
            for spine in ax8.spines.values():
                spine.set_linewidth(0.5)
                spine.set_color('#CCCCCC')
            
            # Add value labels on top of bars
            for i, (ch, cnt) in enumerate(zip(leasts, counts)):
                if cnt > 0:
                    ax8.text(i, cnt + 0.5, f"{cnt} networks\nLeast: Ch {ch}", 
                            ha='center', va='bottom', fontsize=8, color='#2C3E50')

        fig.canvas.draw_idle()
        fig.canvas.flush_events()
        time.sleep(sample_interval)

    # restore x-axis on exit
    if x_vals:
        ax1.set_xlim(0, x_vals[-1] + 5)
        ax2.set_xlim(0, x_vals[-1] + 5)
        ax3.set_xlim(0, x_vals[-1] + 5)
        ax5.set_xlim(0, x_vals[-1] + 5)
        ax6.set_xlim(0, x_vals[-1] + 5)
        ax7.set_xlim(0, x_vals[-1] + 5)

    fig.savefig(plot_file_path, dpi=150, bbox_inches='tight')
    print_success(f"Plot saved at: {plot_file_path}")
    
    # Save split-page PNGs for clean PDF embedding
    # Page 1: Time-series plots (rows 0-4: RSSI, MCS/SNR, Rate vs Range, Tx/Latency, Distance)
    # Page 2: Heatmaps + MCS scatter + Bar chart (rows 5-7)
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        
        # Page 1: Top 5 rows
        fig_p1 = plt.figure(figsize=(20, 24), dpi=150, facecolor='white')
        gs_p1 = gridspec.GridSpec(5, 2, height_ratios=[1,1,1,1,1], hspace=0.50, wspace=0.40,
                                   left=0.06, right=0.94, top=0.96, bottom=0.03)
        
        axes_p1 = {
            'ax1': fig_p1.add_subplot(gs_p1[0, :]),
            'ax2': fig_p1.add_subplot(gs_p1[1, 0]),
            'ax3': fig_p1.add_subplot(gs_p1[1, 1]),
            'ax4': fig_p1.add_subplot(gs_p1[2, :]),
            'ax5': fig_p1.add_subplot(gs_p1[3, 0]),
            'ax6': fig_p1.add_subplot(gs_p1[3, 1]),
            'ax7': fig_p1.add_subplot(gs_p1[4, :]),
        }
        
        # Redraw time-series data on page 1
        _ssid_info = user_provided_ssid or _init_ssid or "Unknown"
        _chan_info = str(_init_chan).strip().replace('\n','') if _init_chan else "Unknown"
        _ap_info = f"AP: {ap_model}" if ap_model and ap_model != "Not specified" else ""
        fig_p1.suptitle("Wireless Network Performance Analysis (Page 1/2)", fontsize=18, fontweight='bold', color='#2C3E50', y=0.99)
        fig_p1.text(0.5, 0.975, f"SSID: {_ssid_info}  |  Channel: {_chan_info}  |  {_ap_info}".strip().rstrip('|').strip(),
                   ha='center', fontsize=11, color='#7F8C8D', style='italic')
        
        # RSSI
        valid_r = [(x, r) for x, r in zip(x_vals, r_vals) if r is not None]
        if valid_r:
            axes_p1['ax1'].plot([v[0] for v in valid_r], [v[1] for v in valid_r], color='#E74C3C', linewidth=2.5)
        axes_p1['ax1'].set_title("Signal Strength (RSSI) Over Time", fontsize=14, fontweight='bold', pad=12)
        axes_p1['ax1'].set_xlabel("Time (s)", fontsize=12); axes_p1['ax1'].set_ylabel("RSSI (dBm)", fontsize=12, color='#E74C3C')
        axes_p1['ax1'].grid(True, alpha=0.2); axes_p1['ax1'].tick_params(labelsize=10)
        
        # MCS
        valid_m = [(x, m) for x, m in zip(x_vals, mcs_vals) if m is not None]
        if valid_m:
            axes_p1['ax2'].plot([v[0] for v in valid_m], [v[1] for v in valid_m], color='#3498DB', linewidth=2.5)
        axes_p1['ax2'].set_title("MCS Index", fontsize=14, fontweight='bold', pad=12)
        axes_p1['ax2'].set_xlabel("Time (s)", fontsize=12); axes_p1['ax2'].set_ylabel("MCS", fontsize=12, color='#3498DB')
        axes_p1['ax2'].set_ylim(-1, 12); axes_p1['ax2'].grid(True, alpha=0.2); axes_p1['ax2'].tick_params(labelsize=10)
        
        # SNR
        valid_s = [(x, s) for x, s in zip(x_vals, snr_vals) if s is not None]
        if valid_s:
            axes_p1['ax3'].plot([v[0] for v in valid_s], [v[1] for v in valid_s], color='#27AE60', linewidth=2.5)
        axes_p1['ax3'].set_title("SNR", fontsize=14, fontweight='bold', pad=12)
        axes_p1['ax3'].set_xlabel("Time (s)", fontsize=12); axes_p1['ax3'].set_ylabel("SNR (dB)", fontsize=12, color='#27AE60')
        axes_p1['ax3'].axhline(y=25, color='gray', linestyle='--', alpha=0.5)
        axes_p1['ax3'].grid(True, alpha=0.2); axes_p1['ax3'].tick_params(labelsize=10)
        
        # Rate vs Range (simplified for static page)
        valid_rr = [(d, t, m) for d, t, m in zip(dist_vals, t_vals, mcs_vals) if d and t and m is not None]
        if valid_rr:
            sorted_rr = sorted(valid_rr, key=lambda x: x[0])
            axes_p1['ax4'].bar([x[0] for x in sorted_rr], [x[1] for x in sorted_rr],
                              width=max(0.3, (sorted_rr[-1][0]-sorted_rr[0][0])/len(sorted_rr)*0.7),
                              color='#9B59B6', alpha=0.7, edgecolor='white')
            ax4b = axes_p1['ax4'].twinx()
            ax4b.plot([x[0] for x in sorted_rr], [x[2] for x in sorted_rr], color='#3498DB', linewidth=2.5, marker='o', markersize=5)
            ax4b.set_ylabel("MCS", fontsize=12, color='#3498DB'); ax4b.set_ylim(-1, 12); ax4b.tick_params(labelsize=10)
        axes_p1['ax4'].set_title("Rate vs Range (Tx Rate & MCS by Distance)", fontsize=14, fontweight='bold', pad=12)
        axes_p1['ax4'].set_xlabel("Distance (m)", fontsize=12); axes_p1['ax4'].set_ylabel("Tx Rate (Mbps)", fontsize=12, color='#9B59B6')
        axes_p1['ax4'].grid(True, alpha=0.2); axes_p1['ax4'].tick_params(labelsize=10)
        
        # Tx Rate
        valid_t = [(x, t) for x, t in zip(x_vals, t_vals) if t is not None]
        if valid_t:
            axes_p1['ax5'].plot([v[0] for v in valid_t], [v[1] for v in valid_t], color='#9B59B6', linewidth=2.5)
        axes_p1['ax5'].set_title("Throughput", fontsize=14, fontweight='bold', pad=12)
        axes_p1['ax5'].set_xlabel("Time (s)", fontsize=12); axes_p1['ax5'].set_ylabel("Tx Rate (Mbps)", fontsize=12, color='#9B59B6')
        axes_p1['ax5'].grid(True, alpha=0.2); axes_p1['ax5'].tick_params(labelsize=10)
        
        # Latency
        valid_l = [(x, l) for x, l in zip(x_vals, lat_vals) if l is not None]
        if valid_l:
            axes_p1['ax6'].plot([v[0] for v in valid_l], [v[1] for v in valid_l], color='#E67E22', linewidth=2.5)
        axes_p1['ax6'].set_title("Latency", fontsize=14, fontweight='bold', pad=12)
        axes_p1['ax6'].set_xlabel("Time (s)", fontsize=12); axes_p1['ax6'].set_ylabel("Latency (ms)", fontsize=12, color='#E67E22')
        axes_p1['ax6'].grid(True, alpha=0.2); axes_p1['ax6'].tick_params(labelsize=10)
        
        # Distance
        valid_d = [(x, d) for x, d in zip(x_vals, dist_vals) if d is not None]
        if valid_d:
            axes_p1['ax7'].plot([v[0] for v in valid_d], [v[1] for v in valid_d], color='#34495E', linewidth=2.5)
        axes_p1['ax7'].set_title("Estimated Distance from AP", fontsize=14, fontweight='bold', pad=12)
        axes_p1['ax7'].set_xlabel("Time (s)", fontsize=12); axes_p1['ax7'].set_ylabel("Distance (m)", fontsize=12, color='#34495E')
        axes_p1['ax7'].grid(True, alpha=0.2); axes_p1['ax7'].tick_params(labelsize=10)
        
        p1_path = plot_file_path.replace('.png', '_page1.png')
        fig_p1.savefig(p1_path, dpi=150, bbox_inches='tight')
        plt.close(fig_p1)
        print_success(f"Plot page 1 saved: {p1_path}")
        
        # Page 2: Heatmaps + MCS scatter
        fig_p2 = plt.figure(figsize=(20, 18), dpi=150, facecolor='white')
        gs_p2 = gridspec.GridSpec(3, 2, height_ratios=[1.2, 1, 0.5], hspace=0.45, wspace=0.40,
                                   left=0.06, right=0.94, top=0.95, bottom=0.04)
        ax_hm_p2 = fig_p2.add_subplot(gs_p2[0, 0])
        ax_cov_p2 = fig_p2.add_subplot(gs_p2[0, 1])
        ax_mcs_p2 = fig_p2.add_subplot(gs_p2[1, :])
        ax_bar_p2 = fig_p2.add_subplot(gs_p2[2, :])
        
        fig_p2.suptitle("Wireless Network Performance Analysis (Page 2/2)", fontsize=18, fontweight='bold', color='#2C3E50', y=0.98)
        
        # Heatmaps
        if len(heatmap_measurements) >= 1:
            update_heatmap_plot(ax_hm_p2, ax_cov_p2)
        
        # MCS scatter
        valid_scatter = [(d, m, r) for d, m, r in zip(dist_vals, mcs_vals, r_vals) if d and m is not None and r is not None]
        if valid_scatter:
            sc_d = [x[0] for x in valid_scatter]; sc_m = [x[1] for x in valid_scatter]; sc_r = [x[2] for x in valid_scatter]
            ax_mcs_p2.scatter(sc_d, sc_m, c=sc_r, cmap='RdYlGn', s=60, edgecolors='white', linewidth=0.5, vmin=-80, vmax=-30, zorder=5)
            ax_mcs_p2.axhspan(7, 13, alpha=0.08, color='green'); ax_mcs_p2.axhspan(3, 7, alpha=0.08, color='yellow'); ax_mcs_p2.axhspan(-1, 3, alpha=0.08, color='red')
        ax_mcs_p2.set_title("MCS Index at Each Distance", fontsize=14, fontweight='bold', pad=12)
        ax_mcs_p2.set_xlabel("Distance (m)", fontsize=12); ax_mcs_p2.set_ylabel("MCS Index", fontsize=12)
        ax_mcs_p2.set_ylim(-1, 13); ax_mcs_p2.grid(True, alpha=0.2); ax_mcs_p2.tick_params(labelsize=10)
        
        # Bar chart placeholder
        ax_bar_p2.set_title("Nearby WiFi Networks by Band", fontsize=14, fontweight='bold', pad=12)
        ax_bar_p2.set_xlabel("Band", fontsize=12); ax_bar_p2.set_ylabel("Count", fontsize=12)
        ax_bar_p2.tick_params(labelsize=10)
        
        p2_path = plot_file_path.replace('.png', '_page2.png')
        fig_p2.savefig(p2_path, dpi=150, bbox_inches='tight')
        plt.close(fig_p2)
        print_success(f"Plot page 2 saved: {p2_path}")
    except Exception as e:
        print_warning(f"Could not save split pages: {e}")
    
    # Save standalone RSSI coverage heatmap PNG
    if len(heatmap_measurements) >= 1:
        try:
            heatmap_file = plot_file_path.replace('.png', '_coverage_heatmap.png')
            fig_hm, (ax_hm1, ax_hm2) = plt.subplots(1, 2, figsize=(16, 7), dpi=150)
            update_heatmap_plot(ax_hm1, ax_hm2)
            fig_hm.suptitle("WiFi Coverage Analysis", fontsize=16, fontweight='bold', color='#2C3E50')
            fig_hm.tight_layout(rect=[0, 0, 1, 0.95])
            fig_hm.savefig(heatmap_file, dpi=150, bbox_inches='tight')
            plt.close(fig_hm)
            print_success(f"Coverage heatmap saved at: {heatmap_file}")
        except Exception as e:
            print_warning(f"Could not save standalone heatmap: {e}")
    
    # Close the separate coverage window
    try:
        fig_cov.savefig(plot_file_path.replace('.png', '_coverage_window.png'), dpi=150, bbox_inches='tight')
        print_success(f"Coverage window saved at: {plot_file_path.replace('.png', '_coverage_window.png')}")
        plt.close(fig_cov)
    except Exception:
        pass

    # Close the main live figure. It was never closed before, so in comparative
    # mode (plot_live_diagnostics is called twice) the giant figures piled up in
    # memory. Drop all live figures now that everything is saved.
    try:
        plt.close(fig)
        plt.close('all')
    except Exception:
        pass

    # Print final summary with colors
    print_header("📊 FINAL DIAGNOSTIC SUMMARY")
    print_metric("  Total iterations", iteration, "", Colors.PURPLE)
    print_metric("  Total roaming events", len(roaming_events), "", Colors.ORANGE if len(roaming_events) > 0 else Colors.GREEN)
    print_metric("  Total interference incidents", len(interference_log), "", Colors.RED if len(interference_log) > 0 else Colors.GREEN)
    
    if r_vals:
        avg_rssi = sum([r for r in r_vals if r is not None])/len([r for r in r_vals if r is not None])
        rssi_color = get_rssi_color(avg_rssi)
        print_metric("  Average RSSI", f"{avg_rssi:.2f}", " dBm", rssi_color)
    
    if snr_vals:
        valid_snr = [s for s in snr_vals if s is not None]
        if valid_snr:
            avg_snr = sum(valid_snr)/len(valid_snr)
            snr_color = get_snr_color(avg_snr)
            print_metric("  Average SNR", f"{avg_snr:.2f}", " dB", snr_color)
    
    if t_vals:
        valid_tx = [t for t in t_vals if t is not None]
        if valid_tx:
            avg_tx = sum(valid_tx)/len(valid_tx)
            tx_color = Colors.GREEN if avg_tx > 400 else Colors.TEAL if avg_tx > 200 else Colors.ORANGE
            print_metric("  Average Tx Rate", f"{avg_tx:.2f}", " Mbps", tx_color)
    
    print(f"\n{Colors.PURPLE}{'='*80}{Colors.ENDC}")


# ===== COMPARATIVE TESTING MODE FUNCTIONS =====

def store_test_results(test_type="KGU"):
    """Store test results for comparative analysis"""
    global csv_data, roaming_events, interference_log, bssid_history
    global ap_model, user_provided_ssid, cached_ssid, cached_chan
    
    # Calculate statistics
    rssi_vals = [row[1] for row in csv_data if row[1] is not None]
    snr_vals = [row[7] for row in csv_data if row[7] is not None]
    tx_vals = [row[2] for row in csv_data if row[2] is not None]
    lat_vals = [row[3] for row in csv_data if row[3] is not None]
    mcs_vals = [row[4] for row in csv_data if row[4] is not None]
    dist_vals = [estimate_distance(row[1]) for row in csv_data if row[1] is not None]
    dist_vals = [d for d in dist_vals if d is not None]
    
    # Calculate peak values
    peak_download = None
    peak_upload = None
    # Extract from speedtest results if available (stored in iteration summaries or separate)
    
    results = {
        "test_type": test_type,
        "ap_model": ap_model,
        "ssid": user_provided_ssid if user_provided_ssid else cached_ssid,
        "channel": cached_chan,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_iterations": len(csv_data),
        
        # RSSI statistics
        "rssi_avg": sum(rssi_vals) / len(rssi_vals) if rssi_vals else None,
        "rssi_min": min(rssi_vals) if rssi_vals else None,
        "rssi_max": max(rssi_vals) if rssi_vals else None,
        "rssi_values": rssi_vals,
        
        # SNR statistics
        "snr_avg": sum(snr_vals) / len(snr_vals) if snr_vals else None,
        "snr_min": min(snr_vals) if snr_vals else None,
        "snr_max": max(snr_vals) if snr_vals else None,
        "snr_values": snr_vals,
        
        # MCS statistics
        "mcs_avg": sum(mcs_vals) / len(mcs_vals) if mcs_vals else None,
        "mcs_min": min(mcs_vals) if mcs_vals else None,
        "mcs_max": max(mcs_vals) if mcs_vals else None,
        "mcs_values": mcs_vals,
        
        # Tx Rate statistics
        "tx_avg": sum(tx_vals) / len(tx_vals) if tx_vals else None,
        "tx_min": min(tx_vals) if tx_vals else None,
        "tx_max": max(tx_vals) if tx_vals else None,
        "tx_peak": max(tx_vals) if tx_vals else None,
        "tx_values": tx_vals,
        
        # Latency statistics
        "latency_avg": sum(lat_vals) / len(lat_vals) if lat_vals else None,
        "latency_min": min(lat_vals) if lat_vals else None,
        "latency_max": max(lat_vals) if lat_vals else None,
        "latency_values": lat_vals,
        
        # Distance statistics
        "distance_avg": sum(dist_vals) / len(dist_vals) if dist_vals else None,
        "distance_min": min(dist_vals) if dist_vals else None,
        "distance_max": max(dist_vals) if dist_vals else None,
        "distance_values": dist_vals,
        
        # Connection quality
        "roaming_events": len(roaming_events),
        "interference_incidents": len(interference_log),
        "unique_bssids": len(set(bssid_history)) if bssid_history else 0,
        
        # Raw data
        "csv_data": csv_data,
        "roaming_events_detail": roaming_events,
        "interference_log": interference_log
    }
    
    return results


def calculate_rssi_mcs_correlation(rssi_values, mcs_values):
    """
    Calculate RSSI to MCS correlation for comparison
    Returns: List of (rssi_bucket, avg_mcs) tuples
    """
    if not rssi_values or not mcs_values or len(rssi_values) != len(mcs_values):
        return []
    
    # Group by RSSI buckets (5dB intervals)
    buckets = {}
    for rssi, mcs in zip(rssi_values, mcs_values):
        if rssi is None or mcs is None:
            continue
        bucket = int(rssi / 5) * 5  # Round to nearest 5dB
        if bucket not in buckets:
            buckets[bucket] = []
        buckets[bucket].append(mcs)
    
    # Calculate average MCS per bucket
    correlation = []
    for bucket in sorted(buckets.keys()):
        avg_mcs = sum(buckets[bucket]) / len(buckets[bucket])
        correlation.append((bucket, avg_mcs))
    
    return correlation


def compare_kgu_dut(kgu_results, dut_results):
    """
    Compare KGU and DUT test results with scientific tolerances
    
    Based on industry standards and research:
    - Throughput: ±10% acceptable, ±15% warning, >15% fail
    - RSSI: ±3dB acceptable, ±5dB warning, >5dB fail
    - MCS: ±1 index acceptable, ±2 warning, >2 fail
    - Latency: ±20% acceptable, ±30% warning, >30% fail
    - RSSI-to-MCS correlation: Must follow similar degradation curve
    
    Returns: comparison dict with pass/fail status and detailed analysis
    """
    
    comparison = {
        "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kgu_info": {
            "model": kgu_results["ap_model"],
            "ssid": kgu_results["ssid"],
            "channel": kgu_results["channel"]
        },
        "dut_info": {
            "model": dut_results["ap_model"],
            "ssid": dut_results["ssid"],
            "channel": dut_results["channel"]
        },
        "metrics": {},
        "overall_status": "PASS",
        "overall_score": 100,
        "failures": [],
        "warnings": [],
        "passed": [],
        "disposition": "PASS",
        "recommendation": ""
    }
    
    # Test Criteria 1: Peak Throughput (Tx Rate)
    kgu_peak_tx = kgu_results["tx_peak"]
    dut_peak_tx = dut_results["tx_peak"]
    
    if kgu_peak_tx and dut_peak_tx:
        tx_delta = dut_peak_tx - kgu_peak_tx
        tx_delta_pct = (tx_delta / kgu_peak_tx) * 100
        
        if abs(tx_delta_pct) <= 10:
            tx_status = "PASS"
            comparison["passed"].append(f"Peak Throughput within ±10% ({tx_delta_pct:+.1f}%)")
        elif abs(tx_delta_pct) <= 15:
            tx_status = "WARN"
            comparison["warnings"].append(f"Peak Throughput deviation {tx_delta_pct:+.1f}% (±10% expected)")
            comparison["overall_score"] -= 10
        else:
            tx_status = "FAIL"
            comparison["failures"].append(f"Peak Throughput deviation {tx_delta_pct:+.1f}% (>±15% threshold)")
            comparison["overall_status"] = "FAIL"
            comparison["overall_score"] -= 25
        
        comparison["metrics"]["peak_throughput"] = {
            "kgu": kgu_peak_tx,
            "dut": dut_peak_tx,
            "delta": tx_delta,
            "delta_pct": tx_delta_pct,
            "status": tx_status,
            "threshold": "±10% acceptable, ±15% warning"
        }
    
    # Test Criteria 2: Peak MCS vs RSSI correlation
    kgu_mcs_peak = kgu_results["mcs_max"]
    dut_mcs_peak = dut_results["mcs_max"]
    kgu_rssi_at_peak = kgu_results["rssi_avg"]  # Simplified - could track RSSI at peak MCS
    dut_rssi_at_peak = dut_results["rssi_avg"]
    
    if kgu_mcs_peak and dut_mcs_peak:
        mcs_delta = dut_mcs_peak - kgu_mcs_peak
        
        if abs(mcs_delta) <= 1:
            mcs_status = "PASS"
            comparison["passed"].append(f"Peak MCS within ±1 index ({mcs_delta:+.0f})")
        elif abs(mcs_delta) <= 2:
            mcs_status = "WARN"
            comparison["warnings"].append(f"Peak MCS deviation {mcs_delta:+.0f} (±1 expected)")
            comparison["overall_score"] -= 10
        else:
            mcs_status = "FAIL"
            comparison["failures"].append(f"Peak MCS deviation {mcs_delta:+.0f} (>±2 threshold)")
            comparison["overall_status"] = "FAIL"
            comparison["overall_score"] -= 25
        
        comparison["metrics"]["peak_mcs"] = {
            "kgu": kgu_mcs_peak,
            "dut": dut_mcs_peak,
            "delta": mcs_delta,
            "status": mcs_status,
            "threshold": "±1 index acceptable, ±2 warning"
        }
    
    # Test Criteria 3: RSSI Ramp Down to MCS Ramp Down
    # Calculate correlation curves
    kgu_correlation = calculate_rssi_mcs_correlation(kgu_results["rssi_values"], kgu_results["mcs_values"])
    dut_correlation = calculate_rssi_mcs_correlation(dut_results["rssi_values"], dut_results["mcs_values"])
    
    if kgu_correlation and dut_correlation:
        # Compare degradation curves - check if MCS drops similarly as RSSI decreases
        correlation_match = True
        correlation_details = []
        
        # Find common RSSI buckets
        kgu_dict = dict(kgu_correlation)
        dut_dict = dict(dut_correlation)
        common_buckets = set(kgu_dict.keys()) & set(dut_dict.keys())
        
        if common_buckets:
            max_mcs_diff = 0
            for bucket in sorted(common_buckets):
                kgu_mcs = kgu_dict[bucket]
                dut_mcs = dut_dict[bucket]
                mcs_diff = abs(dut_mcs - kgu_mcs)
                max_mcs_diff = max(max_mcs_diff, mcs_diff)
                correlation_details.append({
                    "rssi_bucket": bucket,
                    "kgu_mcs": kgu_mcs,
                    "dut_mcs": dut_mcs,
                    "diff": mcs_diff
                })
            
            if max_mcs_diff <= 1.5:
                corr_status = "PASS"
                comparison["passed"].append(f"RSSI-to-MCS correlation matches (max diff: {max_mcs_diff:.1f})")
            elif max_mcs_diff <= 2.5:
                corr_status = "WARN"
                comparison["warnings"].append(f"RSSI-to-MCS correlation deviation {max_mcs_diff:.1f} (≤1.5 expected)")
                comparison["overall_score"] -= 10
            else:
                corr_status = "FAIL"
                comparison["failures"].append(f"RSSI-to-MCS correlation mismatch {max_mcs_diff:.1f} (>2.5 threshold)")
                comparison["overall_status"] = "FAIL"
                comparison["overall_score"] -= 25
            
            comparison["metrics"]["rssi_mcs_correlation"] = {
                "max_deviation": max_mcs_diff,
                "status": corr_status,
                "threshold": "±1.5 MCS acceptable, ±2.5 warning",
                "details": correlation_details
            }
    
    # Additional metrics: Average RSSI
    if kgu_results["rssi_avg"] and dut_results["rssi_avg"]:
        rssi_delta = dut_results["rssi_avg"] - kgu_results["rssi_avg"]
        
        if abs(rssi_delta) <= 3:
            rssi_status = "PASS"
            comparison["passed"].append(f"Average RSSI within ±3dB ({rssi_delta:+.1f}dB)")
        elif abs(rssi_delta) <= 5:
            rssi_status = "WARN"
            comparison["warnings"].append(f"Average RSSI deviation {rssi_delta:+.1f}dB (±3dB expected)")
            comparison["overall_score"] -= 5
        else:
            rssi_status = "FAIL"
            comparison["failures"].append(f"Average RSSI deviation {rssi_delta:+.1f}dB (>±5dB threshold)")
            comparison["overall_status"] = "FAIL"
            comparison["overall_score"] -= 15
        
        comparison["metrics"]["avg_rssi"] = {
            "kgu": kgu_results["rssi_avg"],
            "dut": dut_results["rssi_avg"],
            "delta": rssi_delta,
            "status": rssi_status,
            "threshold": "±3dB acceptable, ±5dB warning"
        }
    
    # Additional metrics: Average Latency (INFO ONLY - not pass/fail)
    # Latency is server-dependent and not a reliable indicator of wireless issues
    if kgu_results["latency_avg"] and dut_results["latency_avg"]:
        lat_delta = dut_results["latency_avg"] - kgu_results["latency_avg"]
        lat_delta_pct = (lat_delta / kgu_results["latency_avg"]) * 100
        
        # Latency is informational only - always INFO status
        lat_status = "INFO"
        
        if abs(lat_delta_pct) > 50:
            comparison["warnings"].append(f"Average Latency deviation {lat_delta_pct:+.1f}% (server-dependent, informational only)")
        
        comparison["metrics"]["avg_latency"] = {
            "kgu": kgu_results["latency_avg"],
            "dut": dut_results["latency_avg"],
            "delta": lat_delta,
            "delta_pct": lat_delta_pct,
            "status": lat_status,
            "threshold": "Informational only (server-dependent)"
        }
    
    # Connection stability: Roaming events (INFO ONLY - not pass/fail)
    # macOS limitations prevent reliable BSSID tracking, so roaming is informational only
    kgu_roaming = kgu_results["roaming_events"]
    dut_roaming = dut_results["roaming_events"]
    roaming_delta = dut_roaming - kgu_roaming
    
    # Roaming is informational only due to Apple's BSSID redaction
    roam_status = "INFO"
    
    comparison["metrics"]["roaming_events"] = {
        "kgu": kgu_roaming,
        "dut": dut_roaming,
        "delta": roaming_delta,
        "status": roam_status,
        "threshold": "Informational only (Apple BSSID limitations)"
    }
    
    # Ensure score doesn't go negative
    comparison["overall_score"] = max(0, comparison["overall_score"])
    
    # Determine final disposition
    if comparison["overall_status"] == "PASS":
        comparison["disposition"] = "NTF - No Trouble Found"
        comparison["recommendation"] = "The DUT performs within acceptable tolerances. No wireless issues detected. Unit is acceptable for deployment."
    else:
        # Analyze failure patterns to provide specific recommendations
        # Note: Latency and roaming are excluded as they are informational only
        failure_types = []
        if any("Throughput" in f for f in comparison["failures"]):
            failure_types.append("throughput degradation")
        if any("MCS" in f or "correlation" in f.lower() for f in comparison["failures"]):
            failure_types.append("RF performance issues")
        if any("RSSI" in f for f in comparison["failures"]):
            failure_types.append("signal strength problems")
        
        if failure_types:
            comparison["disposition"] = "WIRELESS ISSUE DETECTED"
            comparison["recommendation"] = f"The DUT shows significant performance issues: {', '.join(failure_types)}. Further investigation required. Possible causes: antenna problems, RF calibration needed, hardware defect, or firmware issues. DO NOT DEPLOY until issues are resolved."
        else:
            comparison["disposition"] = "MARGINAL - Additional Testing Required"
            comparison["recommendation"] = "The DUT shows some performance deviations but no critical failures. Recommend additional testing to confirm unit stability before deployment."
    
    return comparison


def generate_comparative_report(kgu_results, dut_results, comparison):
    """Generate comprehensive comparative test report PDF"""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    
    report_file = os.path.join(os.getcwd(), f"comparative_report_{time.strftime('%Y%m%d_%H%M%S')}.pdf")
    
    doc = SimpleDocTemplate(report_file, pagesize=letter,
                           rightMargin=0.75*inch, leftMargin=0.75*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#5F00AF'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#5F00AF'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Title
    story.append(Paragraph("Comparative Test Report: KGU vs DUT", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Overall Result
    status_color = colors.green if comparison["overall_status"] == "PASS" else colors.red
    status_text = f"<font color='{status_color.hexval()}'><b>{comparison['overall_status']}</b></font> (Score: {comparison['overall_score']}/100)"
    story.append(Paragraph(f"<b>Overall Result:</b> {status_text}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Test Information
    story.append(Paragraph("Test Information", heading_style))
    test_info = [
        ["", "Known Good Unit (KGU)", "Device Under Test (DUT)"],
        ["AP Model", kgu_results["ap_model"], dut_results["ap_model"]],
        ["SSID", kgu_results["ssid"], dut_results["ssid"]],
        ["Channel", kgu_results["channel"], dut_results["channel"]],
        ["Test Date", kgu_results["timestamp"], dut_results["timestamp"]],
        ["Iterations", str(kgu_results["total_iterations"]), str(dut_results["total_iterations"])]
    ]
    
    t = Table(test_info, colWidths=[1.5*inch, 2.25*inch, 2.25*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5F00AF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#E6E6FA')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*inch))
    
    # Test Criteria Results
    story.append(Paragraph("Test Criteria Results", heading_style))
    
    criteria_data = [["Metric", "KGU", "DUT", "Delta", "Status", "Threshold"]]
    
    for metric_name, metric_data in comparison["metrics"].items():
        if metric_name == "rssi_mcs_correlation":
            # Special handling for correlation
            criteria_data.append([
                "RSSI-MCS Correlation",
                "Baseline",
                "Measured",
                f"{metric_data['max_deviation']:.1f} MCS",
                metric_data["status"],
                metric_data["threshold"]
            ])
        else:
            kgu_val = metric_data.get("kgu", "N/A")
            dut_val = metric_data.get("dut", "N/A")
            delta = metric_data.get("delta", "N/A")
            
            # Format values
            if isinstance(kgu_val, float):
                kgu_str = f"{kgu_val:.2f}"
                dut_str = f"{dut_val:.2f}"
                if "pct" in metric_data:
                    delta_str = f"{metric_data['delta_pct']:+.1f}%"
                else:
                    delta_str = f"{delta:+.2f}"
            else:
                kgu_str = str(kgu_val)
                dut_str = str(dut_val)
                delta_str = str(delta)
            
            criteria_data.append([
                metric_name.replace("_", " ").title(),
                kgu_str,
                dut_str,
                delta_str,
                metric_data["status"],
                metric_data["threshold"]
            ])
    
    t = Table(criteria_data, colWidths=[1.3*inch, 0.9*inch, 0.9*inch, 0.9*inch, 0.7*inch, 1.8*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5F00AF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*inch))
    
    # Failures
    if comparison["failures"]:
        story.append(Paragraph("Critical Failures", heading_style))
        failures_text = "<br/>".join([f"❌ {f}" for f in comparison["failures"]])
        story.append(Paragraph(failures_text, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
    
    # Warnings
    if comparison["warnings"]:
        story.append(Paragraph("Warnings", heading_style))
        warnings_text = "<br/>".join([f"⚠️ {w}" for w in comparison["warnings"]])
        story.append(Paragraph(warnings_text, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
    
    # Passed
    if comparison["passed"]:
        story.append(Paragraph("Passed Criteria", heading_style))
        passed_text = "<br/>".join([f"✅ {p}" for p in comparison["passed"]])
        story.append(Paragraph(passed_text, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
    
    # Disposition
    story.append(PageBreak())
    story.append(Paragraph("Test Disposition", heading_style))
    
    if comparison["overall_status"] == "PASS":
        disposition = """
        <b>DISPOSITION: PASS - Unit Acceptable</b><br/><br/>
        The Device Under Test (DUT) performs within acceptable tolerances compared to the Known Good Unit (KGU).
        All critical metrics are within industry-standard thresholds. The unit is suitable for deployment.<br/><br/>
        <b>Recommendation:</b> Approve for shipment.
        """
    else:
        disposition = f"""
        <b>DISPOSITION: FAIL - Unit Rejected</b><br/><br/>
        The Device Under Test (DUT) shows significant performance deviations from the Known Good Unit (KGU).
        {len(comparison['failures'])} critical failure(s) detected.<br/><br/>
        <b>Recommendation:</b> Investigate root cause. Possible issues:<br/>
        • Antenna connection problems<br/>
        • RF calibration needed<br/>
        • Hardware defect<br/>
        • Firmware mismatch<br/><br/>
        <b>Action Required:</b> Do not ship. Return for rework or further analysis.
        """
    
    story.append(Paragraph(disposition, styles['Normal']))
    
    # Build PDF
    doc.build(story)
    print_success(f"Comparative report generated: {report_file}")
    return report_file


# Test point break

if __name__ == "__main__":
    # CLI argument handling for viewer mode
    if len(sys.argv) > 1 and sys.argv[1] in ('--viewer', '--retrain-ml'):
        if sys.argv[1] == '--retrain-ml':
            from wl_viewer import MLScoringEngine
            print("Retraining ML models from history...")
            ml = MLScoringEngine()
            ml.retrain()
            print("Done.")
            sys.exit(0)
        
        if sys.argv[1] == '--viewer':
            from wl_viewer import DataBundler, MLScoringEngine, HTMLGenerator
            folders = [a for a in sys.argv[2:] if not a.startswith('--')]
            compare = '--compare' in sys.argv
            
            if not folders:
                print("Usage: python3 wl_tool12.py --viewer RUN_folder/ [RUN_folder2/ ...] [--compare]")
                sys.exit(1)
            
            bundler = DataBundler()
            ml = MLScoringEngine()
            gen = HTMLGenerator()
            
            bundles = []
            for folder in folders:
                print(f"Bundling {folder}...")
                bundle = bundler.bundle(folder)
                scored = ml.score_bundle(bundle)
                ml.append_to_history(scored)
                bundles.append(scored)
                
                # Save .wldata file
                wldata_path = f"{scored.test_name}.wldata"
                try:
                    bundler.save_bundle(scored, os.path.join(folder, wldata_path))
                except PermissionError:
                    bundler.save_bundle(scored, wldata_path)
                print(f"  Saved: {wldata_path}")
            
            # Generate viewer
            if compare and len(bundles) > 1:
                title = " vs ".join(b.test_name for b in bundles)
                out = f"viewer_comparison.html"
            else:
                title = f"{bundles[0].test_name} WiFi Diagnostics"
                out = f"viewer_{bundles[0].test_name}.html"
            
            gen.generate(bundles, out, title)
            print(f"\nViewer generated: {out}")
            print(f"Open in Chrome: file://{os.path.abspath(out)}")
            sys.exit(0)
    
    # Print beautiful banner
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                              ║")
    print("║          WIRELESS ENGINEER'S DIAGNOSTIC SUITE v3.0.0                         ║")
    print("║                                                                              ║")
    print("║                    Professional WiFi Analysis Tool                           ║")
    print("║                                                                              ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}\n")
    
    # ===== TOP-LEVEL OPERATING MODE SELECTION =====
    print_header("Select Operating Mode")
    print(f"{Colors.BOLD}1.{Colors.ENDC} Live Diagnostics  {Colors.GRAY}— real-time WiFi metrics, charts & PDF report{Colors.ENDC}")
    print(f"   {Colors.GRAY}AP-centered radial view. No floor plan. Debug real-world WiFi live.{Colors.ENDC}")
    print(f"{Colors.BOLD}2.{Colors.ENDC} Survey Mode       {Colors.GRAY}— interactive coverage heatmap on a floor plan{Colors.ENDC}")
    print(f"   {Colors.GRAY}Hamina-style: pick a floor plan (Finder), mark points, walk & measure.{Colors.ENDC}")
    print(f"   {Colors.GRAY}Supports single-device or A/B comparison (e.g. KGU vs DUT) on the same plan.{Colors.ENDC}")
    print()

    operating_mode = input(f"{Colors.BOLD}{Colors.PURPLE}Select mode (1 or 2): {Colors.ENDC}").strip()

    if operating_mode == "2":
        # ===== MODE 2: SURVEY (Hamina-style interactive heatmap) =====
        print_header("🗺️  SURVEY MODE")
        print_info("Launching the interactive site-survey workflow...")
        try:
            import wl_survey
            wl_survey.main()
        except Exception as e:
            print_error(f"Survey mode failed: {e}")
            import traceback
            traceback.print_exc()
        sys.exit(0)

    # ===== MODE 1: LIVE DIAGNOSTICS =====
    # AP-centered radial heatmap, no floor plan, no walk path.
    print_header("📡 LIVE DIAGNOSTICS MODE")
    print_info("Real-time WiFi metrics with AP-centered radial visualization (no floor plan).")
    print()

    # Sub-mode: standard vs comparative test
    print(f"{Colors.BOLD}1.{Colors.ENDC} Standard Diagnostic Test")
    print(f"{Colors.BOLD}2.{Colors.ENDC} Comparative Test (KGU vs DUT)")
    print()

    mode_choice = input(f"{Colors.BOLD}{Colors.PURPLE}Select test mode (1 or 2): {Colors.ENDC}").strip()
    
    if mode_choice == "2":
        comparative_mode = True
        print_header("🔬 COMPARATIVE TESTING MODE")
        print_info("This mode compares a Known Good Unit (KGU) against a Device Under Test (DUT)")
        print_info("You will run two tests back-to-back with a pause between them")
        print()
        print_warning("IMPORTANT: Only ONE router should be powered on at a time!")
        print_warning("  1. Test KGU first (press 'd' to end), then power it OFF")
        print_warning("  2. Power ON DUT, test it (press 'q' to end)")
        print()
        
        # Get base test name for the comparative test
        base_test_name = input(f"{Colors.BOLD}{Colors.PURPLE}Test name (e.g., ProductionTest_001): {Colors.ENDC}").strip()
        
        # Create parent folder for comparative test
        parent_folder = os.path.join(original_dir, "COMPARATIVE_" + base_test_name)
        os.makedirs(parent_folder, exist_ok=True)
        print_success(f"Comparative test folder created: {parent_folder}")
        
        # ===== PHASE 1: KGU Test =====
        print_header("📊 PHASE 1: Known Good Unit (KGU) Test")
        print_info("Connect to your Known Good Unit (KGU) and ensure it's the ONLY router powered on")
        print_warning("Press 'd' + Enter to end KGU test when ready")
        input(f"{Colors.BOLD}{Colors.PURPLE}Press Enter when ready to start KGU test...{Colors.ENDC}")
        
        # Create KGU folder
        kgu_folder = os.path.join(parent_folder, "KGU")
        os.makedirs(kgu_folder, exist_ok=True)
        os.chdir(kgu_folder)
        print_success(f"KGU results will be saved in: {kgu_folder}")
        
        # Live Diagnostics: AP-centered radial mode, no floor plan / walk path
        floorplan_config['enabled'] = False
        _walk_path_config['enabled'] = False
        
        test_name = "KGU"
        
        # Get AP model (validated against eero device database)
        ap_model = prompt_ap_model("KGU AP Model (e.g., eero Max 7): ")
        
        # Get SSID
        user_provided_ssid = input(f"{Colors.BOLD}{Colors.PURPLE}KGU SSID: {Colors.ENDC}").strip()
        
        log_file_path = os.path.join(kgu_folder, f"network_diagnostics_KGU.txt")
        plot_file_path = os.path.join(kgu_folder, f"network_diagnostics_plot_KGU.png")
        complete_diag_file = os.path.join(kgu_folder, f"complete_Wireless_diagnostics_KGU.txt")
        pdf_report_file = os.path.join(kgu_folder, f"network_report_KGU.pdf")

        try:
            sample_interval = float(input(f"{Colors.BOLD}{Colors.PURPLE}Enter the sample interval in seconds: {Colors.ENDC}").strip())
        except ValueError:
            sample_interval = 2.0
            print_warning(f"Invalid input, using default: {sample_interval}s")

        # Start exit thread for KGU (use 'd' key)
        exit_requested = False
        exit_thread = threading.Thread(target=check_for_exit, args=('d',), daemon=True)
        exit_thread.start()

        ssid = get_ssid()
        channel = get_wifi_channel()
        print_header("KGU Connection")
        print_metric("  SSID", ssid, "", Colors.PURPLE)
        print_metric("  Channel", channel, "", Colors.PURPLE)

        if not network_sanity_check():
            print_error("Cannot continue without network connectivity.")
            sys.exit(1)

        # Run KGU test
        plot_live_diagnostics(sample_interval)

        # Export KGU data
        print_header("📁 Exporting KGU Diagnostic Data")
        export_to_csv("KGU")
        export_to_json("KGU")
        
        # Generate KGU PDF report
        print_info("Generating KGU PDF report...")
        generate_pdf_report()
        print_success("KGU test complete!")
        
        # Store KGU results
        print_info("Storing KGU test results for comparison...")
        kgu_data = store_test_results("KGU")
        
        # ===== PHASE 2: DUT Test =====
        print_header("📊 PHASE 2: Device Under Test (DUT)")
        print_warning("Now POWER OFF the KGU router")
        print_info("Then POWER ON the DUT router")
        print_info("Connect your laptop to the DUT")
        print_warning("Press 'q' + Enter to end DUT test when ready")
        input(f"\n{Colors.BOLD}{Colors.PURPLE}Press Enter when connected to DUT and ready to start test...{Colors.ENDC}")
        
        # Reset globals for DUT test
        csv_data = []
        roaming_events = []
        interference_log = []
        bssid_history = []
        iteration_summaries = []
        mobility_history = []
        heatmap_measurements.clear()
        _kalman_state['initialized'] = False
        _kalman_state['x'] = 0.0
        _kalman_state['P'] = 1.0
        _movement_state['smoothed_distances'].clear()
        _movement_state['current_angle'] = 0.0
        _movement_state['last_distance'] = None
        _retx_prev['initialized'] = False
        _throughput_prev['initialized'] = False
        sanity_check_passed = False
        exit_requested = False
        
        # Create DUT folder
        dut_folder = os.path.join(parent_folder, "DUT")
        os.makedirs(dut_folder, exist_ok=True)
        os.chdir(dut_folder)
        print_success(f"DUT results will be saved in: {dut_folder}")
        
        test_name = "DUT"
        
        # Get DUT information (validated against eero device database)
        ap_model = prompt_ap_model("DUT AP Model: ")
        user_provided_ssid = input(f"{Colors.BOLD}{Colors.PURPLE}DUT SSID: {Colors.ENDC}").strip()
        
        log_file_path = os.path.join(dut_folder, f"network_diagnostics_DUT.txt")
        plot_file_path = os.path.join(dut_folder, f"network_diagnostics_plot_DUT.png")
        complete_diag_file = os.path.join(dut_folder, f"complete_Wireless_diagnostics_DUT.txt")
        pdf_report_file = os.path.join(dut_folder, f"network_report_DUT.pdf")
        
        # Start exit thread for DUT (use 'q' key)
        exit_thread = threading.Thread(target=check_for_exit, args=('q',), daemon=True)
        exit_thread.start()
        
        ssid = get_ssid()
        channel = get_wifi_channel()
        print_header("DUT Connection")
        print_metric("  SSID", ssid, "", Colors.PURPLE)
        print_metric("  Channel", channel, "", Colors.PURPLE)
        
        if not network_sanity_check():
            print_error("Cannot continue without network connectivity.")
            sys.exit(1)
        
        # Run DUT test (same duration as KGU)
        plot_live_diagnostics(sample_interval)
        
        # Export DUT data
        print_header("📁 Exporting DUT Diagnostic Data")
        export_to_csv("DUT")
        export_to_json("DUT")
        
        # Generate DUT PDF report
        print_info("Generating DUT PDF report...")
        generate_pdf_report()
        print_success("DUT test complete!")
        
        # Store DUT results
        print_info("Storing DUT test results for comparison...")
        dut_data = store_test_results("DUT")
        
        # ===== PHASE 3: Comparison =====
        print_header("📊 PHASE 3: Comparative Analysis")
        print_info("Comparing KGU vs DUT...")
        
        comparison = compare_kgu_dut(kgu_data, dut_data)
        
        # Display results
        print_header("🎯 COMPARATIVE TEST RESULTS")
        
        status_color = Colors.GREEN if comparison["overall_status"] == "PASS" else Colors.RED
        print(f"\n{Colors.BOLD}Overall Result:{Colors.ENDC} {status_color}{comparison['overall_status']}{Colors.ENDC}")
        print(f"{Colors.BOLD}Overall Score:{Colors.ENDC} {status_color}{comparison['overall_score']}/100{Colors.ENDC}\n")
        
        # Show metrics
        print(f"{Colors.BOLD}Test Criteria Results:{Colors.ENDC}\n")
        for metric_name, metric_data in comparison["metrics"].items():
            status = metric_data["status"]
            if status == "INFO":
                status_color = Colors.GRAY
                status_symbol = "ℹ️"
            elif status == "PASS":
                status_color = Colors.GREEN
                status_symbol = "✅"
            elif status == "WARN":
                status_color = Colors.ORANGE
                status_symbol = "⚠️"
            else:
                status_color = Colors.RED
                status_symbol = "❌"
            
            print(f"{status_symbol} {Colors.BOLD}{metric_name.replace('_', ' ').title()}:{Colors.ENDC} {status_color}{status}{Colors.ENDC}")
            print(f"   KGU: {metric_data.get('kgu', 'N/A')} | DUT: {metric_data.get('dut', 'N/A')} | Delta: {metric_data.get('delta', 'N/A')}")
            print(f"   {Colors.GRAY}Threshold: {metric_data['threshold']}{Colors.ENDC}\n")
        
        # Show failures
        if comparison["failures"]:
            print(f"\n{Colors.BOLD}{Colors.RED}Critical Failures:{Colors.ENDC}")
            for failure in comparison["failures"]:
                print(f"  {Colors.RED}❌ {failure}{Colors.ENDC}")
        
        # Show warnings
        if comparison["warnings"]:
            print(f"\n{Colors.BOLD}{Colors.ORANGE}Warnings:{Colors.ENDC}")
            for warning in comparison["warnings"]:
                print(f"  {Colors.ORANGE}⚠️ {warning}{Colors.ENDC}")
        
        # Show passed
        if comparison["passed"]:
            print(f"\n{Colors.BOLD}{Colors.GREEN}Passed Criteria:{Colors.ENDC}")
            for passed in comparison["passed"]:
                print(f"  {Colors.GREEN}✅ {passed}{Colors.ENDC}")
        
        # Generate comparative report
        print()
        os.chdir(parent_folder)
        print_info("Generating comparative PDF report...")
        report_file = generate_comparative_report(kgu_data, dut_data, comparison)
        
        # Final disposition
        print_header("🏁 TEST DISPOSITION")
        disposition_color = Colors.GREEN if "NTF" in comparison["disposition"] else Colors.RED
        print(f"{Colors.BOLD}Disposition:{Colors.ENDC} {disposition_color}{comparison['disposition']}{Colors.ENDC}\n")
        print(f"{Colors.BOLD}Recommendation:{Colors.ENDC}")
        print(f"{comparison['recommendation']}\n")
        
        if "NTF" in comparison["disposition"]:
            print_success("✅ DUT is acceptable - No wireless issues detected")
        elif "WIRELESS ISSUE" in comparison["disposition"]:
            print_error("❌ DUT has wireless issues - Further investigation required")
        else:
            print_warning("⚠️ DUT is marginal - Additional testing recommended")
        
        os.chdir(original_dir)
        print_header("✅ Comparative Testing Complete!")
        print_success(f"Parent folder: {parent_folder}")
        print_success(f"  ├── KGU/ (Known Good Unit results)")
        print_success(f"  ├── DUT/ (Device Under Test results)")
        print_success(f"  └── comparative_report_*.pdf")
        print_info(f"Returned to: {original_dir}")
        
    else:
        # ===== STANDARD MODE =====
        comparative_mode = False
        
        # Get test information
        test_name = input(f"{Colors.BOLD}{Colors.PURPLE}What is the test name? {Colors.ENDC}").strip()
        
        # Get AP model (validated against eero device database)
        ap_model = prompt_ap_model("AP Model (e.g., eero Max 7, UniFi AP AC Pro): ")
        
        # Get SSID (user-provided for report)
        user_provided_ssid = input(f"{Colors.BOLD}{Colors.PURPLE}SSID you're connected to: {Colors.ENDC}").strip()
        
        run_folder = os.path.join(original_dir, "RUN_" + test_name)
        os.makedirs(run_folder, exist_ok=True)
        os.chdir(run_folder)
        print_success(f"Results will be saved in: {run_folder}")
        
        # Live Diagnostics: AP-centered radial mode, no floor plan / walk path
        floorplan_config['enabled'] = False
        _walk_path_config['enabled'] = False

        log_file_path = os.path.join(run_folder, f"network_diagnostics_{test_name}.txt")
        plot_file_path = os.path.join(run_folder, f"network_diagnostics_plot_{test_name}.png")
        complete_diag_file = os.path.join(run_folder, f"complete_Wireless_diagnostics_{test_name}.txt")
        pdf_report_file = os.path.join(run_folder, f"network_report_{test_name}.pdf")

        try:
            sample_interval = float(input(f"{Colors.BOLD}{Colors.PURPLE}Enter the sample interval in seconds: {Colors.ENDC}").strip())
        except ValueError:
            sample_interval = 2.0
            print_warning(f"Invalid input, using default: {sample_interval}s")

        exit_thread = threading.Thread(target=check_for_exit, args=('q',), daemon=True)
        exit_thread.start()

        ssid = get_ssid()
        channel = get_wifi_channel()
        print_header("Current Connection")
        print_metric("  SSID", ssid, "", Colors.PURPLE)
        print_metric("  Channel", channel, "", Colors.PURPLE)

        if not network_sanity_check():
            print_error("Cannot continue without network connectivity.")
            sys.exit(1)

        plot_live_diagnostics(sample_interval)

        # Export data
        print_header("📁 Exporting Diagnostic Data")
        export_to_csv(test_name)
        export_to_json(test_name)

        if input(f"\n{Colors.BOLD}{Colors.PURPLE}Generate PDF report? (y/n): {Colors.ENDC}").strip().lower() == 'y':
            generate_pdf_report()
        else:
            print_info("Skipping PDF report.")

        os.chdir(original_dir)
        print_header("✅ Diagnostics Complete!")
        print_success(f"All results saved in: {run_folder}")
        print_info(f"Returned to: {original_dir}")
