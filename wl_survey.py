"""
WiFi Site Survey — Point-Based Heatmap Generator

Active site-survey workflow (Ekahau/Hamina style):
  1. Load a floor plan image.
  2. Interactively mark measurement points in sequence (click on the plan).
  3. Walk to each point; the tool collects WiFi metrics on demand.
  4. Interpolate (IDW) the per-point measurements into a smooth coverage
     heatmap overlaid on the floor plan, and export an interactive viewer.

Author: Anish Dutta
Version: 1.0.0
"""

__version__ = "1.0.0"

import os
import sys
import json
import base64
import time
import re
from datetime import datetime

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.image import imread

# Reuse measurement helpers from the main tool
try:
    from wl_tool12 import (
        get_wifi_stats, get_noise_floor, get_phy, get_nss,
        get_channel_utilization, get_bssid, get_ssid, get_wifi_channel,
        get_guard_interval, calculate_80211ax_phy_rate, estimate_distance,
        compute_network_score, refresh_wdutil_info,
        estimate_achievable_throughput, home_performance, FOURK_MIN_MBPS,
    )
    _HAVE_TOOL = True
except Exception as e:
    _HAVE_TOOL = False
    _IMPORT_ERR = str(e)


# ===== METRIC THRESHOLDS (for color coding) =====

# RSSI color zones (dBm) — used for the heatmap colorscale
RSSI_EXCELLENT = -50
RSSI_GOOD = -65
RSSI_FAIR = -75


# ===== EKAHAU-STYLE COLOR MAP =====
# Vivid, survey-tool gradient: bright green (best) -> yellow -> orange -> red
# (worst). Saturated so coverage zones are instantly readable on a floor plan.
from matplotlib.colors import LinearSegmentedColormap

# Position 0.0 = worst signal, 1.0 = best signal.
EKAHAU_CMAP = LinearSegmentedColormap.from_list("ekahau", [
    (0.00, "#B00000"),  # deep red    — dead zone
    (0.18, "#FF2A00"),  # red         — very poor
    (0.34, "#FF7A00"),  # orange      — poor
    (0.50, "#FFD400"),  # yellow      — medium
    (0.66, "#C8E000"),  # lime        — fair/good
    (0.82, "#46C300"),  # green       — good
    (1.00, "#00A300"),  # bright green — excellent
])

# Plotly equivalent (list of [position, color]) for the interactive HTML.
EKAHAU_PLOTLY = [
    [0.00, "#B00000"], [0.18, "#FF2A00"], [0.34, "#FF7A00"],
    [0.50, "#FFD400"], [0.66, "#C8E000"], [0.82, "#46C300"],
    [1.00, "#00A300"],
]


# ===== 4K / HOME-PERFORMANCE COLOR MAP =====
# For the estimated-throughput map the colour breakpoint sits at the 4K floor
# (25 Mbps). With vmin=0 / vmax=100 Mbps, position 0.25 == 25 Mbps: red/orange
# below it (cannot stream 4K), green above (4K-ready with headroom).
FOURK_VMAX_MBPS = 100.0
_fk = lambda mbps: max(0.0, min(1.0, mbps / FOURK_VMAX_MBPS))
FOURK_CMAP = LinearSegmentedColormap.from_list("home4k", [
    (0.00,            "#B00000"),  # 0 Mbps    — dead
    (_fk(12),         "#FF2A00"),  # 12 Mbps   — very poor
    (_fk(24.99),      "#FF7A00"),  # just under 4K floor — orange
    (_fk(25),         "#FFD400"),  # 25 Mbps   — exactly the 4K floor (yellow)
    (_fk(50),         "#9ACD32"),  # 50 Mbps   — comfortable
    (_fk(75),         "#46C300"),  # 75 Mbps   — great
    (1.00,            "#00A300"),  # >=100 Mbps — excellent headroom
])
FOURK_PLOTLY = [
    [0.00, "#B00000"], [_fk(12), "#FF2A00"], [_fk(24.99), "#FF7A00"],
    [_fk(25), "#FFD400"], [_fk(50), "#9ACD32"], [_fk(75), "#46C300"],
    [1.00, "#00A300"],
]


def band_channel_label(chan_str):
    """Parse a wdutil channel string into (band_label, channel_number, bandwidth_mhz).

    Handles macOS wdutil forms like '6g149/160', '5g36/80', '2g6/20', and bare
    channel numbers. Returns e.g. ("5 GHz", 36, 80). Unknown parts come back None.
    """
    s = str(chan_str or "").strip()
    m = re.search(r'(\d+)\s*[gG]\s*(\d+)(?:\s*/\s*(\d+))?', s)
    if m:
        ghz, ch = m.group(1), int(m.group(2))
        bw = int(m.group(3)) if m.group(3) else None
        band = {"2": "2.4 GHz", "5": "5 GHz", "6": "6 GHz"}.get(ghz, f"{ghz} GHz")
        return band, ch, bw
    # Fallback: a bare channel number
    m2 = re.search(r'(\d+)', s)
    if not m2:
        return ("Unknown", None, None)
    ch = int(m2.group(1))
    band = "6 GHz" if ch > 165 else "5 GHz" if ch > 14 else "2.4 GHz"
    bw = next((b for b in (160, 80, 40, 20) if str(b) in s), None)
    return band, ch, bw


def band_channel_summary(chan_str):
    """Human-readable one-liner, e.g. '5 GHz · Ch 36 · 80 MHz'."""
    band, ch, bw = band_channel_label(chan_str)
    parts = [band]
    if ch is not None:
        parts.append(f"Ch {ch}")
    if bw:
        parts.append(f"{bw} MHz")
    return " · ".join(parts)


# ===== AP MOUNT PROFILES =====
# Mount placement changes the real coverage shape. Ceiling/overhead mounting
# (facing down) is the recommended practice and radiates fairly evenly outward;
# a desk/table-top unit pushes energy into the horizontal plane where furniture,
# monitors and people block it, creating shadow zones and shorter range.
# (Refs: Cisco Catalyst 9100 deployment guide; Sophos AP mounting guide; WLAN
# Professionals. Path-loss exponent ~2.0 line-of-sight vs ~2.4-3.5 obstructed —
# Virginia Tech indoor measurements. Content rephrased for compliance.)
#
# We translate this into the survey map by:
#   - path_loss_exp : reference propagation exponent for interpretation,
#   - radius_frac   : how far from a sample we trust interpolation (fraction of
#                     the smaller floor-plan dimension). Table-top sees sharper
#                     local variation, so we trust a smaller radius,
#   - note          : a plain-language caveat printed on the map/report.
MOUNT_PROFILES = {
    "ceiling": {
        "label": "Ceiling / overhead mount",
        "path_loss_exp": 2.2,
        "radius_frac": 0.22,
        "note": ("Overhead mount: signal radiates fairly evenly outward — expect "
                 "smooth, roughly circular coverage around the AP."),
    },
    "tabletop": {
        "label": "Table-top / desk mount",
        "path_loss_exp": 3.2,
        "radius_frac": 0.14,
        "note": ("Desk mount: energy is pushed into the horizontal plane where "
                 "furniture, screens and people block it — expect shadow zones and "
                 "shorter range. Sample more densely near obstructions."),
    },
}

def mount_profile(mount_key):
    """Return the MOUNT_PROFILES entry for a key, defaulting to ceiling."""
    return MOUNT_PROFILES.get(mount_key or "ceiling", MOUNT_PROFILES["ceiling"])


# ===== PHASE 1: AP + POINT PLACEMENT =====

def place_ap_and_points(floorplan_path):
    """
    Interactive floor-plan setup, Ekahau/Hamina style.

    Workflow in a single window:
      1. The FIRST left-click drops the Access Point (gold star).
      2. Every following left-click adds a numbered measurement stop, in order.
      3. Right-click undoes the last action (last point, or the AP if no points).
      4. Close the window when done.

    A dashed path line connects the stops so the tester can see the planned
    walk route relative to the AP.

    Returns: (ap_xy or None, points list, img, w_px, h_px)
      - ap_xy: (x_px, y_px) of the AP, or None if not placed
      - points: list of (x_px, y_px) measurement stops in order
    """
    img = imread(floorplan_path)
    h_px, w_px = img.shape[0], img.shape[1]

    state = {"ap": None}
    points = []

    fig, ax = plt.subplots(figsize=(12, 12 * h_px / w_px))
    ax.imshow(img)
    ax.axis("off")

    def _title():
        if state["ap"] is None:
            return ("STEP 1: Left-click to place the ACCESS POINT (router).\n"
                    "Right-click = undo | Close window when done")
        return ("STEP 2: Left-click each measurement STOP in walk order.\n"
                f"AP placed ✓ | {len(points)} stops | Right-click = undo | Close when done")

    ax.set_title(_title(), fontsize=11)
    markers = []

    def redraw():
        for m in markers:
            try:
                m.remove()
            except Exception:
                pass
        markers.clear()
        # AP star
        if state["ap"] is not None:
            ax_, ay_ = state["ap"]
            star = ax.plot(ax_, ay_, "*", color="#FFD400", markersize=26,
                           markeredgecolor="black", markeredgewidth=1.5, zorder=8)[0]
            lbl = ax.annotate("AP", (ax_, ay_), color="black", fontsize=8,
                              fontweight="bold", ha="center", va="center", zorder=9)
            markers.extend([star, lbl])
        # Planned path line (AP -> stops in order)
        if points:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            line = ax.plot(xs, ys, "--", color="#8E44AD", alpha=0.5,
                           linewidth=1.5, zorder=4)[0]
            markers.append(line)
        # Stops (purple = planned/pending)
        for i, (x, y) in enumerate(points, 1):
            dot = ax.plot(x, y, "o", color="#8E44AD", markersize=14,
                          markeredgecolor="white", markeredgewidth=2, zorder=5)[0]
            txt = ax.annotate(str(i), (x, y), color="white", fontsize=9,
                              fontweight="bold", ha="center", va="center", zorder=6)
            markers.extend([dot, txt])
        ax.set_title(_title(), fontsize=11)
        fig.canvas.draw_idle()

    def on_click(event):
        if event.inaxes != ax:
            return
        if event.button == 1:  # add
            if state["ap"] is None:
                state["ap"] = (event.xdata, event.ydata)
            else:
                points.append((event.xdata, event.ydata))
            redraw()
        elif event.button == 3:  # undo
            if points:
                points.pop()
            elif state["ap"] is not None:
                state["ap"] = None
            redraw()

    fig.canvas.mpl_connect("button_press_event", on_click)
    print("\n>>> STEP 1: Click once to place the ACCESS POINT (gold star).")
    print(">>> STEP 2: Click each measurement stop in walk order (purple dots).")
    print(">>> Right-click undoes. Close the window when finished.\n")
    plt.tight_layout()
    plt.show()

    return state["ap"], points, img, w_px, h_px


# Backwards-compatible alias (older callers expect points first)
def place_points(floorplan_path):
    ap_xy, points, img, w_px, h_px = place_ap_and_points(floorplan_path)
    return points, img, w_px, h_px


# ===== PHASE 2: MEASUREMENT COLLECTION =====

def measure_point(samples=3, sample_delay=1.0):
    """
    Collect WiFi metrics at the current location by averaging a few samples.

    Returns a dict with averaged RSSI, SNR, MCS, Tx Rate, PHY rate, etc.
    """
    rssi_vals, snr_vals, mcs_vals, tx_vals, cu_vals = [], [], [], [], []
    phy = nss = None

    gi = get_guard_interval()

    for s in range(samples):
        # Take a fresh wdutil snapshot for THIS sample so the averaged samples
        # (and every survey point) reflect real, distinct readings rather than a
        # single cached snapshot.
        refresh_wdutil_info()
        stats = get_wifi_stats()
        if "Error" in stats:
            print(f"   Measurement error: {stats['Error']}")
            break
        rssi = stats.get("RSSI")
        tx = stats.get("Tx Rate")
        mcs = stats.get("MCS Index")
        noise = get_noise_floor()
        cu = get_channel_utilization()
        phy = get_phy()
        nss = get_nss()

        if rssi is not None:
            rssi_vals.append(rssi)
            if noise is not None:
                snr_vals.append(rssi - noise)
        if isinstance(mcs, int):
            mcs_vals.append(mcs)
        if tx is not None:
            tx_vals.append(tx)
        if isinstance(cu, int):
            cu_vals.append(cu)

        if s < samples - 1:
            time.sleep(sample_delay)

    def _avg(v):
        return float(np.mean(v)) if v else None

    avg_rssi = _avg(rssi_vals)
    avg_mcs = _avg(mcs_vals)

    # NSS as int
    nss_int = 1
    if nss:
        import re
        m = re.search(r"\d+", str(nss))
        if m:
            nss_int = int(m.group(0))

    # Bandwidth from channel
    chan = get_wifi_channel()
    bw = 80
    if chan and "160" in str(chan):
        bw = 160
    elif chan and "80" in str(chan):
        bw = 80
    elif chan and "40" in str(chan):
        bw = 40
    else:
        bw = 20

    phy_rate = None
    if avg_mcs is not None:
        calc = calculate_80211ax_phy_rate(int(round(avg_mcs)), nss_int, bw, gi)
        phy_rate = calc.get("phy_rate_mbps")

    avg_snr = _avg(snr_vals)
    avg_tx = _avg(tx_vals)
    # Composite real-world performance score (0-100) from all five metrics
    score, _ = compute_network_score(rssi=avg_rssi, snr=avg_snr, mcs=avg_mcs,
                                     tx_rate=avg_tx, phy_rate=phy_rate)

    # Home / 4K-streaming performance: estimated achievable throughput from
    # (RSSI, SNR, MCS, NSS) graded against the 25 Mbps 4K floor.
    hp = home_performance(
        avg_rssi, avg_snr,
        int(round(avg_mcs)) if avg_mcs is not None else None,
        nss_int, bw, gi)

    return {
        "rssi": avg_rssi,
        "snr": avg_snr,
        "mcs": avg_mcs,
        "tx_rate": avg_tx,
        "channel_util": _avg(cu_vals),
        "phy_rate": phy_rate,
        "score": score,
        "throughput": hp["throughput_mbps"],   # est. achievable Mbps (4K model)
        "home_score": hp["score"],             # 0-100, 60 == 25 Mbps 4K floor
        "streams_4k": hp["streams_4k"],        # simultaneous 25 Mbps 4K streams
        "home_label": hp["label"],
        "capable_4k": hp["capable_4k"],
        "phy_mode": str(phy) if phy else "",
        "nss": nss_int,
        "bw": bw,
        "samples": len(rssi_vals),
    }


def run_survey(points, samples=3, ap_xy=None, img=None, guide=True):
    """
    Walk through each placed point and collect measurements interactively,
    with a live guide map (Ekahau-style).

    The guide window shows the AP, the planned walk path, and every stop:
      - purple  = pending
      - blue    = current stop (walk here now)
      - green   = measured
      - orange  = skipped
    Returns a list of measurement dicts, one per measured point.
    """
    measurements = []
    n = len(points)
    print(f"\n{'='*70}")
    print(f"  MEASUREMENT PHASE — {n} points to survey")
    print(f"  Guide: purple=pending  blue=current  green=done  orange=skipped")
    print(f"{'='*70}\n")

    # status per point: 'pending' | 'current' | 'done' | 'skipped'
    status = ["pending"] * n
    guide_state = _init_guide(points, ap_xy, img) if guide else None

    for i, (x, y) in enumerate(points, 1):
        status[i - 1] = "current"
        _update_guide(guide_state, points, ap_xy, status)
        print(f"--- Point {i} of {n} ---")
        try:
            cmd = input(f"   Walk to point {i} (blue marker), then press Enter "
                        f"to measure (or 's' to skip): ").strip().lower()
        except EOFError:
            cmd = ""
        if cmd == "s":
            status[i - 1] = "skipped"
            _update_guide(guide_state, points, ap_xy, status)
            print("   Skipped.\n")
            continue

        print(f"   Measuring ({samples} samples)...")
        m = measure_point(samples=samples)
        m["point"] = i
        m["x_px"] = x
        m["y_px"] = y
        measurements.append(m)
        status[i - 1] = "done"
        _update_guide(guide_state, points, ap_xy, status)

        rssi_str = f"{m['rssi']:.1f} dBm" if m["rssi"] is not None else "N/A"
        mcs_str = f"{m['mcs']:.0f}" if m["mcs"] is not None else "N/A"
        snr_str = f"{m['snr']:.1f} dB" if m["snr"] is not None else "N/A"
        print(f"   Point {i}: RSSI={rssi_str} | SNR={snr_str} | MCS={mcs_str}\n")

    _close_guide(guide_state)
    n_done = status.count("done")
    n_skip = status.count("skipped")
    print(f"Survey walk complete: {n_done} measured, {n_skip} skipped.")
    return measurements


# ----- Live guide map helpers -----

_GUIDE_COLORS = {
    "pending": "#8E44AD",   # purple
    "current": "#2980B9",   # blue
    "done":    "#27AE60",   # green
    "skipped": "#E67E22",   # orange
}

def _init_guide(points, ap_xy, img):
    """Open a non-blocking live guide figure. Returns (fig, ax) or None."""
    if img is None or len(points) == 0:
        return None
    try:
        plt.ion()
        h_px, w_px = img.shape[0], img.shape[1]
        fig, ax = plt.subplots(figsize=(10, 10 * h_px / w_px))
        ax.imshow(img)
        ax.axis("off")
        ax.set_title("Survey guide — walk to the BLUE marker, then measure",
                     fontsize=11, fontweight="bold")
        fig.canvas.draw()
        plt.pause(0.05)
        return (fig, ax)
    except Exception:
        return None

def _update_guide(guide_state, points, ap_xy, status):
    """Redraw the guide with current per-point status colors."""
    if guide_state is None:
        return
    fig, ax = guide_state
    try:
        # Clear dynamic artists but keep the background image (first artist)
        for art in list(ax.lines) + list(ax.texts) + list(ax.collections):
            art.remove()
        # AP star
        if ap_xy is not None:
            ax.plot(ap_xy[0], ap_xy[1], "*", color="#FFD400", markersize=24,
                    markeredgecolor="black", markeredgewidth=1.5, zorder=8)
            ax.annotate("AP", (ap_xy[0], ap_xy[1]), color="black", fontsize=8,
                        fontweight="bold", ha="center", va="center", zorder=9)
        # Planned path
        xs = [p[0] for p in points]; ys = [p[1] for p in points]
        if len(points) > 1:
            ax.plot(xs, ys, "--", color="#95A5A6", alpha=0.6, linewidth=1.5, zorder=4)
        # Stops colored by status
        for i, (x, y) in enumerate(points):
            c = _GUIDE_COLORS.get(status[i], "#8E44AD")
            size = 18 if status[i] == "current" else 13
            ax.plot(x, y, "o", color=c, markersize=size,
                    markeredgecolor="white", markeredgewidth=2, zorder=5)
            ax.annotate(str(i + 1), (x, y), color="white", fontsize=8,
                        fontweight="bold", ha="center", va="center", zorder=6)
        fig.canvas.draw()
        plt.pause(0.05)
    except Exception:
        pass

def _close_guide(guide_state):
    if guide_state is None:
        return
    try:
        plt.ioff()
    except Exception:
        pass


# ===== PHASE 3 + 4: IDW INTERPOLATION & HEATMAP =====

def idw_interpolate(points_xy, values, grid_x, grid_y, power=2.5, smoothing=1e-6):
    """
    Inverse Distance Weighting interpolation.

    points_xy: array of (x, y) measurement locations
    values:    measured value at each point
    grid_x, grid_y: meshgrid coordinates to interpolate onto
    power:     IDW power parameter (higher = more local influence)

    Returns a 2D array of interpolated values matching grid shape.
    """
    pts = np.asarray(points_xy, dtype=float)
    vals = np.asarray(values, dtype=float)

    gx = grid_x.ravel()
    gy = grid_y.ravel()
    out = np.empty(gx.shape, dtype=float)

    for k in range(gx.size):
        dx = pts[:, 0] - gx[k]
        dy = pts[:, 1] - gy[k]
        dist2 = dx * dx + dy * dy + smoothing
        w = 1.0 / np.power(dist2, power / 2.0)
        out[k] = np.sum(w * vals) / np.sum(w)

    return out.reshape(grid_x.shape)


def interpolate_surface(points_xy, values, grid_x, grid_y):
    """
    Build a smooth coverage surface from scattered measurement points,
    the way pro survey tools (Ekahau / Hamina) do it.

    Uses a Radial Basis Function (thin-plate spline) interpolant, which:
      - passes through every measured value exactly (accurate "stitching"),
      - blends organically between points (no IDW bullseye rings),
      - extrapolates smoothly past the outer points.

    Falls back to a multiquadric RBF, then to IDW, if the spline is unstable
    (e.g. nearly-collinear points) or SciPy is too old.

    Returns a 2D array matching grid_x / grid_y shape.
    """
    pts = np.asarray(points_xy, dtype=float)
    vals = np.asarray(values, dtype=float)
    grid_pts = np.column_stack([grid_x.ravel(), grid_y.ravel()])

    # Need at least 3 non-degenerate points for a 2-D spline
    if len(pts) >= 3:
        # Normalize coordinates so x/y scales don't bias the kernel
        scale = max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1]), 1.0)
        p_n = pts / scale
        g_n = grid_pts / scale
        for kernel, smoothing in (("thin_plate_spline", 0.0),
                                  ("multiquadric", 1e-3)):
            try:
                from scipy.interpolate import RBFInterpolator
                rbf = RBFInterpolator(p_n, vals, kernel=kernel,
                                      smoothing=smoothing)
                zi = rbf(g_n).reshape(grid_x.shape)
                if np.all(np.isfinite(zi)):
                    return zi
            except Exception:
                continue

    # Fallback: inverse-distance weighting
    return idw_interpolate(points_xy, values, grid_x, grid_y)


def coverage_mask(points_xy, grid_x, grid_y, radius_px):
    """
    Return a boolean grid that is True where a cell is farther than
    `radius_px` from EVERY measurement point.

    Survey tools fade/clip coverage away from where you actually sampled,
    rather than inventing confident values in unmeasured areas. We use this
    to make distant cells transparent (NaN) on the heatmap.
    """
    pts = np.asarray(points_xy, dtype=float)
    gx = grid_x.ravel()
    gy = grid_y.ravel()
    nearest = np.full(gx.shape, np.inf)
    for px, py in pts:
        d = np.sqrt((gx - px) ** 2 + (gy - py) ** 2)
        nearest = np.minimum(nearest, d)
    return (nearest > radius_px).reshape(grid_x.shape)


def generate_heatmap(measurements, img, w_px, h_px, output_png,
                     metric="rssi", title="WiFi Coverage Heatmap",
                     ap_xy=None, planned_points=None,
                     info_line=None, mount=None):
    """
    Build a smooth IDW heatmap overlaid on the floor plan and save as PNG.

    If ap_xy / planned_points are given, the AP (gold star), the planned walk
    path, and any skipped stops (orange) are drawn for visual context.

    info_line : optional string (band / channel / SSID) drawn as a subtitle.
    mount     : optional MOUNT_PROFILES key ('ceiling'/'tabletop'); adjusts how
                far interpolation is trusted and adds a caveat to the subtitle.
    """
    valid = [m for m in measurements if m.get(metric) is not None]
    if len(valid) < 2:
        print("   Need at least 2 measured points for a heatmap.")
        return None

    pts_xy = [(m["x_px"], m["y_px"]) for m in valid]
    vals = [m[metric] for m in valid]

    # Interpolation grid (downsampled for speed)
    grid_res = 200
    xi = np.linspace(0, w_px, grid_res)
    yi = np.linspace(0, h_px, int(grid_res * h_px / w_px))
    gx, gy = np.meshgrid(xi, yi)

    # Smooth RBF surface that passes through measured points (Ekahau/Hamina-style)
    zi = interpolate_surface(pts_xy, vals, gx, gy)

    # Fade out areas far from any measurement (don't fabricate coverage).
    # Radius scales with the floor plan size. Mount type tunes how far we trust
    # interpolation: a table-top AP varies sharply around clutter, so we trust a
    # smaller radius; a ceiling AP is smoother, so we trust a wider one.
    radius_frac = mount_profile(mount)["radius_frac"] if mount else 0.18
    radius_px = radius_frac * min(w_px, h_px)
    mask = coverage_mask(pts_xy, gx, gy, radius_px)
    zi = np.where(mask, np.nan, zi)

    fig, ax = plt.subplots(figsize=(14, 14 * h_px / w_px))
    ax.imshow(img, extent=[0, w_px, h_px, 0], zorder=0)

    # Vivid Ekahau-style colormap: red(weak) -> yellow -> green(strong)
    if metric == "score":
        cmap = EKAHAU_CMAP
        vmin, vmax = 0, 100     # composite network performance score
        cbar_label = "Performance Score (0-100)"
    elif metric == "throughput":
        cmap = FOURK_CMAP
        vmin, vmax = 0, FOURK_VMAX_MBPS   # 25 Mbps = 4K floor (yellow breakpoint)
        cbar_label = "Est. Throughput (Mbps) — 4K needs \u2265 25"
    elif metric == "rssi":
        cmap = EKAHAU_CMAP
        vmin, vmax = -80, -45   # -45 dBm+ = best green, -80 dBm = dead red
        cbar_label = "RSSI (dBm)"
    elif metric == "mcs":
        cmap = EKAHAU_CMAP
        vmin, vmax = 2, 11
        cbar_label = "MCS Index"
    elif metric == "phy_rate":
        cmap = EKAHAU_CMAP
        vmin, vmax = 0, max(vals)
        cbar_label = "PHY Rate (Mbps)"
    else:
        cmap = EKAHAU_CMAP
        vmin, vmax = min(vals), max(vals)
        cbar_label = metric

    # Clip the interpolated field to the color range so transitions stay vivid
    zi = np.clip(zi, vmin, vmax)

    # Smooth filled contour overlay — higher opacity for clear zone reading
    cf = ax.contourf(gx, gy, zi, levels=100, cmap=cmap, alpha=0.7,
                     vmin=vmin, vmax=vmax, zorder=1, extend="both")

    # On the 4K map, draw the 25 Mbps boundary so the pass/fail line is explicit.
    if metric == "throughput":
        try:
            cs = ax.contour(gx, gy, zi, levels=[FOURK_MIN_MBPS],
                            colors="#1A1A2E", linewidths=1.4, linestyles="--",
                            zorder=2)
            ax.clabel(cs, fmt={FOURK_MIN_MBPS: "4K floor (25 Mbps)"}, fontsize=7)
        except Exception:
            pass

    # Planned walk path (faint guide line through planned stops, in order)
    if planned_points and len(planned_points) > 1:
        pxs = [p[0] for p in planned_points]
        pys = [p[1] for p in planned_points]
        ax.plot(pxs, pys, "--", color="#34495E", alpha=0.45, linewidth=1.5, zorder=3)

    # Measured points (white dots, numbered)
    measured_pts = set()
    for m in valid:
        measured_pts.add((round(m["x_px"], 1), round(m["y_px"], 1)))
        ax.plot(m["x_px"], m["y_px"], "o", color="white",
                markersize=12, markeredgecolor="black", markeredgewidth=1.5, zorder=5)
        ax.annotate(str(m["point"]), (m["x_px"], m["y_px"]),
                    color="black", fontsize=8, fontweight="bold",
                    ha="center", va="center", zorder=6)

    # Skipped stops (planned but not measured) -> orange markers
    if planned_points:
        for i, (px, py) in enumerate(planned_points, 1):
            if (round(px, 1), round(py, 1)) not in measured_pts:
                ax.plot(px, py, "X", color="#E67E22", markersize=12,
                        markeredgecolor="black", markeredgewidth=1.2, zorder=5)
                ax.annotate(str(i), (px, py), color="black", fontsize=7,
                            fontweight="bold", ha="center", va="bottom", zorder=6)

    # AP marker (gold star)
    if ap_xy is not None:
        ax.plot(ap_xy[0], ap_xy[1], "*", color="#FFD400", markersize=26,
                markeredgecolor="black", markeredgewidth=1.5, zorder=8)
        ax.annotate("AP", (ap_xy[0], ap_xy[1]), color="black", fontsize=8,
                    fontweight="bold", ha="center", va="center", zorder=9)

    cbar = fig.colorbar(cf, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label(cbar_label, fontsize=11)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=26)

    # Subtitle: frequency band / channel (feature 1) + AP mount caveat (feature 3)
    sub_parts = []
    if info_line:
        sub_parts.append(info_line)
    if mount:
        sub_parts.append(mount_profile(mount)["label"])
    if sub_parts:
        ax.text(0.5, 1.015, "   ·   ".join(sub_parts), transform=ax.transAxes,
                ha="center", va="bottom", fontsize=10, color="#34495E",
                fontweight="bold")
    if mount:
        ax.text(0.5, -0.02, mount_profile(mount)["note"], transform=ax.transAxes,
                ha="center", va="top", fontsize=7.5, color="#7F8C8D",
                style="italic", wrap=True)

    ax.axis("off")
    ax.set_xlim(0, w_px)
    ax.set_ylim(h_px, 0)

    plt.tight_layout()
    fig.savefig(output_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"   Heatmap saved: {output_png}")
    return output_png


def save_survey_data(measurements, img_path, w_px, h_px, output_json):
    """Save survey measurements + floor plan reference to a JSON file."""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("ascii")

    data = {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "floorplan_width_px": w_px,
        "floorplan_height_px": h_px,
        "floorplan_image_b64": img_b64,
        "measurements": measurements,
    }
    with open(output_json, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"   Survey data saved: {output_json}")
    return output_json


# ===== SURVEY PDF REPORT =====

# Composite-score quality bands (must match the score colormap legend)
_SCORE_BANDS = [
    ("Excellent", 85, 100, "#27AE60"),
    ("Good",      65,  85, "#9ACD32"),
    ("Fair",      40,  65, "#F1C40F"),
    ("Poor",       0,  40, "#E74C3C"),
]

def _band_for_score(s):
    for name, lo, hi, color in _SCORE_BANDS:
        if s is None:
            return ("N/A", "#BDC3C7")
        if s >= lo and (s <= hi if name == "Excellent" else s < hi):
            return (name, color)
    return ("Poor", "#E74C3C")

def _stats(vals):
    """Return (avg, mn, mx, median) for a list, ignoring None."""
    v = [x for x in vals if x is not None]
    if not v:
        return (None, None, None, None)
    arr = np.array(v, dtype=float)
    return (float(arr.mean()), float(arr.min()), float(arr.max()),
            float(np.median(arr)))

def _overall_grade(avg_score):
    if avg_score is None:
        return "N/A"
    return _band_for_score(avg_score)[0]


def generate_survey_pdf(measurements, name, out_dir, output_pdf,
                        ap_xy=None, planned_points=None, meta=None,
                        heatmap_paths=None):
    """
    Generate a professional PDF survey report.

    measurements:   list of measured point dicts (rssi/snr/mcs/tx_rate/phy_rate/score)
    meta:           optional dict: site, ap_model, tester, ssid, band, notes
    heatmap_paths:  optional dict of {"score":path, "rssi":path, "mcs":path}
                    to embed; missing ones are skipped.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, Image, PageBreak)
    except Exception as e:
        print(f"   ReportLab not available — skipping PDF ({e})")
        return None

    meta = meta or {}
    measured = [m for m in measurements if m.get("score") is not None]
    n_planned = len(planned_points) if planned_points else len(measurements)
    n_measured = len(measured)
    n_skipped = max(0, n_planned - n_measured)

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18,
                        textColor=colors.HexColor("#1a1a2e"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13,
                        textColor=colors.HexColor("#2C3E50"), spaceBefore=10)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                          textColor=colors.HexColor("#7F8C8D"))

    doc = SimpleDocTemplate(output_pdf, pagesize=letter,
                            topMargin=0.6*inch, bottomMargin=0.6*inch,
                            leftMargin=0.7*inch, rightMargin=0.7*inch)
    story = []

    # ---- Cover / header ----
    story.append(Paragraph("WiFi Site Survey Report", h1))
    story.append(Paragraph(f"<b>{meta.get('site', name)}</b>", body))
    story.append(Spacer(1, 0.15*inch))

    info = [
        ["Survey name", name, "Date", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["AP model", meta.get("ap_model", "—"), "AP mount", meta.get("mount_label", "—")],
        ["SSID", meta.get("ssid", "—"), "Band / channel", meta.get("band", "—")],
        ["Points planned", str(n_planned), "Points measured", str(n_measured)],
        ["Points skipped", str(n_skipped), "Samples/point", meta.get("samples", "—")],
    ]
    t = Table(info, colWidths=[1.3*inch, 2.2*inch, 1.3*inch, 2.0*inch])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#7F8C8D")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#7F8C8D")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#ECECEC")),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.2*inch))

    # ---- Executive summary ----
    story.append(Paragraph("Executive Summary", h2))
    sc_avg, sc_min, sc_max, sc_med = _stats([m.get("score") for m in measured])
    grade = _overall_grade(sc_avg)
    grade_color = _band_for_score(sc_avg)[1] if sc_avg is not None else "#BDC3C7"
    story.append(Paragraph(
        f"Overall network performance score: <b>{sc_avg:.0f}/100</b> "
        f"(<font color='{grade_color}'><b>{grade}</b></font>), "
        f"ranging {sc_min:.0f}–{sc_max:.0f} across {n_measured} measured points."
        if sc_avg is not None else "No scored measurements collected.", body))
    story.append(Spacer(1, 0.1*inch))

    # AP mount context (feature 3) — how to read the coverage shape.
    if meta.get("mount_note"):
        story.append(Paragraph(
            f"<i>AP mount: <b>{meta.get('mount_label', '—')}</b> — "
            f"{meta['mount_note']}</i>", small))
        story.append(Spacer(1, 0.1*inch))

    # Band distribution
    band_counts = {b[0]: 0 for b in _SCORE_BANDS}
    for m in measured:
        band_counts[_band_for_score(m["score"])[0]] += 1
    rows = [["Quality band", "Score range", "Points", "% of measured"]]
    for nm, lo, hi, col in _SCORE_BANDS:
        cnt = band_counts[nm]
        pct = (100.0 * cnt / n_measured) if n_measured else 0
        rows.append([nm, f"{lo}–{hi}", str(cnt), f"{pct:.0f}%"])
    bt = Table(rows, colWidths=[1.6*inch, 1.4*inch, 1.2*inch, 1.6*inch])
    band_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]
    for i, (nm, lo, hi, col) in enumerate(_SCORE_BANDS, 1):
        band_style.append(("TEXTCOLOR", (0, i), (0, i), colors.HexColor(col)))
        band_style.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
    bt.setStyle(TableStyle(band_style))
    story.append(bt)
    story.append(Spacer(1, 0.15*inch))

    # ---- Home / 4K streaming performance (feature 2) ----
    story.append(Paragraph("Home Performance — 4K Streaming Readiness", h2))
    story.append(Paragraph(
        "Smooth 4K (UHD) video needs a sustained <b>25 Mbps</b>. We estimate the "
        "achievable TCP throughput at each point as a function of RSSI, SNR, MCS "
        "and NSS (PHY rate × efficiency × signal-reliability), then check it "
        "against that 4K floor:", body))
    tputs = [m.get("throughput") for m in measured if m.get("throughput") is not None]
    n_tput = len(tputs)
    if n_tput:
        n_4k = sum(1 for t in tputs if t >= FOURK_MIN_MBPS)
        pct_4k = 100.0 * n_4k / n_tput
        avg_tput = sum(tputs) / n_tput
        min_tput = min(tputs)
        max_tput = max(tputs)
        story.append(Paragraph(
            f"<b>{n_4k}/{n_tput}</b> measured points ({pct_4k:.0f}%) can stream 4K "
            f"(\u2265 25 Mbps). Estimated throughput averages <b>{avg_tput:.0f} Mbps</b> "
            f"(range {min_tput:.0f}–{max_tput:.0f} Mbps).", body))
        if pct_4k < 100:
            weak4k = [m for m in measured
                      if m.get("throughput") is not None and m["throughput"] < FOURK_MIN_MBPS]
            ids = ", ".join(f"#{m['point']}" for m in weak4k)
            story.append(Paragraph(
                f"⚠ Points below the 4K floor: {ids}.", body))
    else:
        story.append(Paragraph("No throughput estimates available.", body))
    story.append(Spacer(1, 0.15*inch))

    # Key findings
    findings = []
    weak = [m for m in measured if m["score"] < 40]
    if weak:
        ids = ", ".join(str(m["point"]) for m in weak)
        findings.append(f"⚠ {len(weak)} point(s) scored Poor (&lt;40): #{ids}.")
    snr_avg = _stats([m.get("snr") for m in measured])[0]
    if snr_avg is not None and snr_avg < 25:
        findings.append(f"⚠ Average SNR {snr_avg:.0f} dB is below the 25 dB target for high MCS.")
    if n_skipped:
        findings.append(f"ℹ {n_skipped} planned point(s) were skipped during the walk.")
    if not findings:
        findings.append("✓ No critical coverage issues detected across measured points.")
    for f in findings:
        story.append(Paragraph(f, body))

    # ---- Metric statistics table ----
    story.append(Paragraph("Measured Metric Statistics", h2))
    def _row(label, key, unit, fmt="{:.1f}"):
        a, mn, mx, md = _stats([m.get(key) for m in measured])
        if a is None:
            return [label, "—", "—", "—", "—"]
        return [label, fmt.format(a), fmt.format(md), fmt.format(mn), fmt.format(mx)]
    stat_rows = [["Metric", "Avg", "Median", "Min", "Max"],
                 _row("Score (0-100)", "score", "", "{:.0f}"),
                 _row("RSSI (dBm)", "rssi", "dBm"),
                 _row("SNR (dB)", "snr", "dB"),
                 _row("MCS", "mcs", "", "{:.0f}"),
                 _row("Tx rate (Mbps)", "tx_rate", "Mbps", "{:.0f}"),
                 _row("PHY rate (Mbps)", "phy_rate", "Mbps", "{:.0f}"),
                 _row("Est. 4K throughput (Mbps)", "throughput", "Mbps", "{:.0f}")]
    st = Table(stat_rows, colWidths=[1.7*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.0*inch])
    st.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FA")]),
    ]))
    story.append(st)

    # ---- Heatmaps ----
    heatmap_paths = heatmap_paths or {}
    titles = {"score": "Network Performance Score",
              "throughput": "Home Performance — 4K Streaming (\u2265 25 Mbps)",
              "rssi": "RSSI Coverage", "mcs": "MCS Coverage"}
    for key in ("score", "throughput", "rssi", "mcs"):
        p = heatmap_paths.get(key)
        if p and os.path.exists(p):
            story.append(PageBreak())
            story.append(Paragraph(titles[key], h2))
            try:
                img_w = 6.8 * inch
                story.append(Image(p, width=img_w, height=img_w * 0.62))
            except Exception:
                pass

    # ---- Per-point table ----
    story.append(PageBreak())
    story.append(Paragraph("Per-Point Measurements", h2))
    ph = ["#", "RSSI", "SNR", "MCS", "Tx", "PHY", "Score", "Grade"]
    prows = [ph]
    for m in sorted(measured, key=lambda x: x.get("point", 0)):
        def fmt(v, f="{:.0f}"):
            return f.format(v) if v is not None else "—"
        prows.append([
            str(m.get("point", "")),
            fmt(m.get("rssi"), "{:.0f}"), fmt(m.get("snr"), "{:.0f}"),
            fmt(m.get("mcs"), "{:.0f}"), fmt(m.get("tx_rate"), "{:.0f}"),
            fmt(m.get("phy_rate"), "{:.0f}"), fmt(m.get("score"), "{:.0f}"),
            _band_for_score(m.get("score"))[0],
        ])
    pt = Table(prows, colWidths=[0.5*inch, 0.85*inch, 0.8*inch, 0.7*inch,
                                 0.9*inch, 0.9*inch, 0.8*inch, 1.1*inch])
    pstyle = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]
    for i, m in enumerate(sorted(measured, key=lambda x: x.get("point", 0)), 1):
        col = _band_for_score(m.get("score"))[1]
        pstyle.append(("TEXTCOLOR", (7, i), (7, i), colors.HexColor(col)))
        pstyle.append(("FONTNAME", (7, i), (7, i), "Helvetica-Bold"))
    pt.setStyle(TableStyle(pstyle))
    story.append(pt)

    # ---- Recommendations ----
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("Recommendations", h2))
    recs = []
    if weak:
        recs.append("Investigate the Poor-scoring zones: relocate the AP, add a "
                    "mesh node, or remove obstructions near those points.")
    if snr_avg is not None and snr_avg < 25:
        recs.append("Low average SNR suggests interference or distance issues — "
                    "consider a cleaner channel or a closer/6 GHz-capable AP.")
    mcs_avg = _stats([m.get("mcs") for m in measured])[0]
    if mcs_avg is not None and mcs_avg < 7:
        recs.append(f"Average MCS {mcs_avg:.1f} is below 7 (256-QAM) — the link is "
                    "not reaching high modulation; check RF conditions.")
    if meta.get("mount") == "tabletop":
        recs.append("AP is desk/table-top mounted — raising it higher or moving to a "
                    "ceiling/wall mount usually removes furniture shadow zones and "
                    "gives more uniform radial coverage.")
    # 4K-specific recommendation
    _t = [m.get("throughput") for m in measured if m.get("throughput") is not None]
    if _t and any(t < FOURK_MIN_MBPS for t in _t):
        recs.append("Some areas fall below the 25 Mbps 4K-streaming floor — consider "
                    "a mesh node or a 5/6 GHz, wider-channel link to lift throughput "
                    "in those zones.")
    if not recs:
        recs.append("Coverage looks healthy. Re-survey periodically to catch drift.")
    for r in recs:
        story.append(Paragraph(f"• {r}", body))

    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(
        f"Generated by WiFi Diagnostic Suite — Site Survey · {datetime.now():%Y-%m-%d %H:%M}",
        small))

    try:
        doc.build(story)
        print(f"   PDF report saved: {output_pdf}")
        return output_pdf
    except Exception as e:
        print(f"   Failed to build PDF: {e}")
        return None


# ===== INTERACTIVE HTML HEATMAP =====

# Metric configs: key -> (label, colorscale_reversed, vmin, vmax, unit)
_METRIC_CFG = {
    "score":      ("Performance",     False,   0, 100, ""),
    "throughput": ("Home 4K Mbps",    False,   0, 100, "Mbps"),
    "rssi":       ("RSSI",            False, -80, -45, "dBm"),
    "snr":        ("SNR",             False,  15,  35, "dB"),
    "mcs":        ("MCS Index",       False,   2,  11, ""),
    "tx_rate":    ("Tx Rate",         False,   0, None, "Mbps"),
    "phy_rate":   ("PHY Rate",        False,   0, None, "Mbps"),
}


def _build_metric_grid(measurements, w_px, h_px, metric, grid_res=120):
    """Return (x_axis, y_axis, z_grid) IDW-interpolated for one metric, or None."""
    valid = [m for m in measurements if m.get(metric) is not None]
    if len(valid) < 2:
        return None
    pts_xy = [(m["x_px"], m["y_px"]) for m in valid]
    vals = [m[metric] for m in valid]

    xi = np.linspace(0, w_px, grid_res)
    yi = np.linspace(0, h_px, int(grid_res * h_px / w_px))
    gx, gy = np.meshgrid(xi, yi)
    zi = interpolate_surface(pts_xy, vals, gx, gy)
    # Fade unmeasured areas to transparent (NaN -> null in JSON for Plotly)
    radius_px = 0.18 * min(w_px, h_px)
    mask = coverage_mask(pts_xy, gx, gy, radius_px)
    zi = np.where(mask, np.nan, zi)
    return xi.tolist(), yi.tolist(), zi.tolist()


def generate_interactive_html(measurements, img_path, w_px, h_px,
                              output_html, title="WiFi Survey Heatmap", ap_xy=None,
                              info_line=None):
    """
    Generate a self-contained interactive HTML heatmap (Hamina-style).

    Floor plan as background, smooth IDW contour overlay, metric switcher,
    hover-to-read values, and numbered measurement points.
    """
    import plotly

    # Embed floor plan as base64
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("ascii")

    # Build IDW grids for each available metric
    grids = {}
    for key in _METRIC_CFG:
        g = _build_metric_grid(measurements, w_px, h_px, key)
        if g is not None:
            label, rev, vmin, vmax, unit = _METRIC_CFG[key]
            if vmax is None:
                vals = [m[key] for m in measurements if m.get(key) is not None]
                vmax = max(vals) if vals else 1
            grids[key] = {
                "x": g[0], "y": g[1], "z": g[2],
                "label": label, "vmin": vmin, "vmax": vmax, "unit": unit,
                "colorscale": (FOURK_PLOTLY if key == "throughput" else EKAHAU_PLOTLY),
            }

    if not grids:
        print("   No metrics available for interactive heatmap.")
        return None

    # Measurement points
    pts = [{
        "point": m["point"], "x": m["x_px"], "y": m["y_px"],
        "rssi": m.get("rssi"), "snr": m.get("snr"), "mcs": m.get("mcs"),
        "tx_rate": m.get("tx_rate"), "phy_rate": m.get("phy_rate"),
        "throughput": m.get("throughput"), "home_label": m.get("home_label"),
    } for m in measurements]

    # Plotly.js source for offline embedding
    plotly_js = ""
    try:
        js_path = os.path.join(os.path.dirname(plotly.__file__),
                               "package_data", "plotly.min.js")
        if os.path.exists(js_path):
            with open(js_path) as f:
                plotly_js = f.read()
    except Exception:
        pass

    payload = json.dumps({
        "grids": grids, "points": pts,
        "img_b64": img_b64, "w_px": w_px, "h_px": h_px,
        "colorscale": EKAHAU_PLOTLY,
        "ap": ({"x": ap_xy[0], "y": ap_xy[1]} if ap_xy is not None else None),
    }, default=str)

    import html as _html
    safe_title = _html.escape(title)

    html_doc = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<script>__PLOTLY_JS__</script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f8f9fa;color:#2c3e50}
.header{background:#1a1a2e;color:#fff;padding:16px 24px;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:18px;font-weight:600}
.header .subtitle{font-size:12px;color:#9fb3c8;margin-top:3px;font-weight:500}
.controls{display:flex;gap:8px}
.controls button{padding:8px 16px;border:none;border-radius:20px;background:#34495e;color:#fff;cursor:pointer;font-size:13px;font-weight:500}
.controls button.active{background:#3498db}
.controls label{display:flex;align-items:center;gap:6px;color:#bdc3c7;font-size:13px;margin-left:12px}
.content{padding:20px;max-width:1300px;margin:0 auto}
.card{background:#fff;border-radius:8px;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}
#heatmap{width:100%}
</style></head><body>
<div class="header">
  <div><h1>__TITLE__</h1><div class="subtitle">__SUBTITLE__</div></div>
  <div class="controls" id="metric-buttons"></div>
</div>
<div class="content">
  <div class="card"><div id="heatmap"></div></div>
</div>
<script>
const DATA = __PAYLOAD__;
let currentMetric = Object.keys(DATA.grids)[0];
let showPoints = true;

function render() {
  const g = DATA.grids[currentMetric];
  const traces = [];

  // Smooth IDW contour overlay
  traces.push({
    type: 'contour', x: g.x, y: g.y, z: g.z,
    colorscale: (g.colorscale || DATA.colorscale), zmin: g.vmin, zmax: g.vmax,
    opacity: 0.75, contours: {coloring: 'heatmap'},
    line: {width: 0}, ncontours: 80, zsmooth: 'best',
    colorbar: {title: g.label + (g.unit ? ' (' + g.unit + ')' : ''), len: 0.7},
    hovertemplate: g.label + ': %{z:.1f} ' + g.unit + '<extra></extra>',
  });

  // Measurement points
  if (showPoints) {
    traces.push({
      type: 'scatter', mode: 'markers+text',
      x: DATA.points.map(p => p.x), y: DATA.points.map(p => p.y),
      text: DATA.points.map(p => String(p.point)),
      textposition: 'middle center',
      textfont: {color: '#000', size: 10, family: 'Arial Black'},
      marker: {size: 22, color: '#fff', line: {color: '#000', width: 2}},
      hovertemplate: DATA.points.map(p =>
        'Point ' + p.point + '<br>' +
        'RSSI: ' + (p.rssi!=null?p.rssi.toFixed(1)+' dBm':'N/A') + '<br>' +
        'SNR: ' + (p.snr!=null?p.snr.toFixed(1)+' dB':'N/A') + '<br>' +
        'MCS: ' + (p.mcs!=null?p.mcs.toFixed(0):'N/A') + '<br>' +
        'Tx: ' + (p.tx_rate!=null?p.tx_rate.toFixed(0)+' Mbps':'N/A') + '<br>' +
        'Home 4K: ' + (p.throughput!=null?p.throughput.toFixed(0)+' Mbps':'N/A') +
        (p.home_label?' ('+p.home_label+')':'') +
        '<extra></extra>'),
      showlegend: false,
    });
  }

  // AP marker (gold star)
  if (DATA.ap) {
    traces.push({
      type: 'scatter', mode: 'markers+text',
      x: [DATA.ap.x], y: [DATA.ap.y],
      text: ['AP'], textposition: 'top center',
      textfont: {color: '#000', size: 12, family: 'Arial Black'},
      marker: {symbol: 'star', size: 26, color: '#FFD400',
               line: {color: '#000', width: 1.5}},
      hovertemplate: 'Access Point<extra></extra>', showlegend: false,
    });
  }

  const layout = {
    images: [{
      source: 'data:image/png;base64,' + DATA.img_b64,
      xref: 'x', yref: 'y',
      x: 0, y: 0, sizex: DATA.w_px, sizey: DATA.h_px,
      sizing: 'stretch', layer: 'below', opacity: 1.0,
    }],
    xaxis: {range: [0, DATA.w_px], visible: false, constrain: 'domain'},
    yaxis: {range: [DATA.h_px, 0], visible: false,
            scaleanchor: 'x', scaleratio: 1},
    margin: {t: 10, b: 10, l: 10, r: 10},
    height: Math.min(820, 1100 * DATA.h_px / DATA.w_px),
    plot_bgcolor: '#fff', paper_bgcolor: '#fff',
  };

  Plotly.newPlot('heatmap', traces, layout, {responsive: true, displayModeBar: true});
}

function buildButtons() {
  const c = document.getElementById('metric-buttons');
  Object.keys(DATA.grids).forEach(key => {
    const b = document.createElement('button');
    b.textContent = DATA.grids[key].label;
    b.onclick = () => { currentMetric = key; updateActive(); render(); };
    b.dataset.key = key;
    c.appendChild(b);
  });
  const lbl = document.createElement('label');
  const cb = document.createElement('input');
  cb.type = 'checkbox'; cb.checked = true;
  cb.onchange = () => { showPoints = cb.checked; render(); };
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode('Show points'));
  c.appendChild(lbl);
  updateActive();
}

function updateActive() {
  document.querySelectorAll('#metric-buttons button').forEach(b =>
    b.classList.toggle('active', b.dataset.key === currentMetric));
}

buildButtons();
render();
</script>
</body></html>"""

    html_doc = (html_doc
                .replace("__TITLE__", safe_title)
                .replace("__SUBTITLE__", _html.escape(info_line or ""))
                .replace("__PLOTLY_JS__", plotly_js)
                .replace("__PAYLOAD__", payload))

    with open(output_html, "w") as f:
        f.write(html_doc)
    print(f"   Interactive heatmap saved: {output_html}")
    return output_html


# ===== MAIN WORKFLOW =====

def _default_floorplan_path():
    """Path to the bundled default floor plan (next to this script)."""
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "default_floorplan.png")
    return cand if os.path.exists(cand) else "default_floorplan.png"


def _convert_pdf_to_png(pdf_path):
    """Best-effort convert the first page of a PDF floor plan to PNG (macOS).

    Tries PyMuPDF, then poppler's pdftoppm, then macOS sips. Returns the PNG
    path on success, or None if no converter is available.
    """
    out_png = os.path.splitext(pdf_path)[0] + "_page1.png"
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        pix = doc.load_page(0).get_pixmap(dpi=150)
        pix.save(out_png)
        return out_png if os.path.exists(out_png) else None
    except Exception:
        pass
    try:
        import subprocess
        base = os.path.splitext(pdf_path)[0]
        subprocess.run(["pdftoppm", "-png", "-singlefile", "-r", "150", pdf_path, base],
                       check=True, capture_output=True, timeout=30)
        if os.path.exists(base + ".png"):
            return base + ".png"
    except Exception:
        pass
    try:
        import subprocess
        subprocess.run(["sips", "-s", "format", "png", pdf_path, "--out", out_png],
                       check=True, capture_output=True, timeout=30)
        return out_png if os.path.exists(out_png) else None
    except Exception:
        pass
    return None


def _native_file_picker():
    """Open the native macOS Finder file chooser; return a POSIX path or None."""
    import subprocess
    script = (
        'POSIX path of (choose file with prompt '
        '"Select a floor plan image (PNG, JPG or PDF)" '
        'of type {"public.image", "com.adobe.pdf"})'
    )
    try:
        out = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=120)
        return out.stdout.strip() or None
    except Exception:
        return None


def choose_floorplan():
    """
    Let the user pick a floor plan the easy way.

    On a Mac the default is a native Finder dialog (no path typing). Also
    supports the bundled default plan, or dragging a file into Terminal
    (macOS pastes its path). PDFs are auto-converted to PNG.

    Returns a usable image path, or None if the user backs out.
    """
    default_path = _default_floorplan_path()
    has_default = os.path.exists(default_path)

    print("\nFloor plan:")
    print("  1. Browse…  (open a Finder window to pick the image/PDF)")
    if has_default:
        print("  2. Use the built-in default plan")
    print("  3. Type or drag-and-drop a file path")

    try:
        choice = input("Select (1/2/3, Enter = Browse): ").strip()
    except EOFError:
        choice = ""

    fp = None
    if choice in ("", "1"):
        print("  Opening Finder… (pick your floor plan)")
        fp = _native_file_picker()
        if not fp:
            print("  No file chosen from Finder.")
    elif choice == "2" and has_default:
        fp = default_path
    elif choice == "3":
        try:
            raw = input("  Path (drag the file here, then press Enter): ").strip()
        except EOFError:
            raw = ""
        fp = raw.strip().strip("'\"").replace("\\ ", " ").replace("\\", "")
    else:
        fp = default_path if has_default else None

    if not fp:
        return None
    fp = os.path.expanduser(fp)
    if not os.path.exists(fp):
        print(f"  File not found: {fp}")
        return None

    if fp.lower().endswith(".pdf"):
        print("  Converting PDF to image…")
        png = _convert_pdf_to_png(fp)
        if png:
            print(f"  Using: {png}")
            return png
        print("  Could not convert the PDF. Please export it to PNG/JPG and retry.")
        return None
    return fp


def _render_survey_outputs(measurements, fp, img, w_px, h_px, name, out_dir,
                           open_browser=True, ap_xy=None, planned_points=None,
                           meta=None):
    """Render all heatmaps + JSON + interactive HTML + PDF for one measurement set."""
    meta = meta or {}
    mount = meta.get("mount")
    # Band / channel + SSID line shown on top of every plot (feature 1).
    info_bits = []
    if meta.get("band") and meta["band"] != "—":
        info_bits.append(meta["band"])
    if meta.get("ssid") and meta["ssid"] != "—":
        info_bits.append(f"SSID {meta['ssid']}")
    info_line = "   ·   ".join(info_bits) if info_bits else None

    print(f"\nGenerating heatmaps for '{name}'...")
    score_png = os.path.join(out_dir, f"heatmap_score_{name}.png")
    home_png = os.path.join(out_dir, f"heatmap_home4k_{name}.png")
    rssi_png = os.path.join(out_dir, f"heatmap_rssi_{name}.png")
    mcs_png = os.path.join(out_dir, f"heatmap_mcs_{name}.png")
    generate_heatmap(measurements, img, w_px, h_px, score_png,
                     metric="score", title=f"Network Performance Score — {name}",
                     ap_xy=ap_xy, planned_points=planned_points,
                     info_line=info_line, mount=mount)
    generate_heatmap(measurements, img, w_px, h_px, home_png,
                     metric="throughput",
                     title=f"Home Performance — 4K Streaming (\u2265 25 Mbps) — {name}",
                     ap_xy=ap_xy, planned_points=planned_points,
                     info_line=info_line, mount=mount)
    generate_heatmap(measurements, img, w_px, h_px, rssi_png,
                     metric="rssi", title=f"RSSI Coverage — {name}",
                     ap_xy=ap_xy, planned_points=planned_points,
                     info_line=info_line, mount=mount)
    generate_heatmap(measurements, img, w_px, h_px, mcs_png,
                     metric="mcs", title=f"MCS Coverage — {name}",
                     ap_xy=ap_xy, planned_points=planned_points,
                     info_line=info_line, mount=mount)
    save_survey_data(measurements, fp, w_px, h_px,
                     os.path.join(out_dir, f"survey_{name}.json"))

    # Professional PDF report
    generate_survey_pdf(
        measurements, name, out_dir,
        os.path.join(out_dir, f"survey_report_{name}.pdf"),
        ap_xy=ap_xy, planned_points=planned_points, meta=meta,
        heatmap_paths={"score": score_png, "throughput": home_png,
                       "rssi": rssi_png, "mcs": mcs_png})

    html_path = generate_interactive_html(
        measurements, fp, w_px, h_px,
        os.path.join(out_dir, f"survey_{name}.html"),
        title=f"WiFi Survey — {name}", ap_xy=ap_xy, info_line=info_line)
    if html_path and open_browser:
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(html_path)}")
        print("Opening interactive heatmap in browser...")
    return html_path


def generate_delta_heatmap(meas_a, meas_b, img, w_px, h_px, output_png,
                           name_a="A", name_b="B", ap_xy=None):
    """
    Render a difference heatmap of composite score: (B - A) at each point.

    Green = device B performs better here, red = device B performs worse.
    Both measurement lists must share the same point order/positions.
    """
    from matplotlib.colors import LinearSegmentedColormap
    pairs = [(a, b) for a, b in zip(meas_a, meas_b)
             if a.get("score") is not None and b.get("score") is not None]
    if len(pairs) < 2:
        print("   Not enough paired points for a difference map.")
        return None

    pts_xy = [(a["x_px"], a["y_px"]) for a, _ in pairs]
    deltas = [b["score"] - a["score"] for a, b in pairs]

    grid_res = 200
    xi = np.linspace(0, w_px, grid_res)
    yi = np.linspace(0, h_px, int(grid_res * h_px / w_px))
    gx, gy = np.meshgrid(xi, yi)
    zi = interpolate_surface(pts_xy, deltas, gx, gy)
    radius_px = 0.18 * min(w_px, h_px)
    zi = np.where(coverage_mask(pts_xy, gx, gy, radius_px), np.nan, zi)
    zi = np.clip(zi, -40, 40)

    delta_cmap = LinearSegmentedColormap.from_list("delta", [
        (0.0, "#B00000"), (0.35, "#FF7A00"), (0.5, "#FFFFFF"),
        (0.65, "#46C300"), (1.0, "#00A300"),
    ])

    fig, ax = plt.subplots(figsize=(14, 14 * h_px / w_px))
    ax.imshow(img, extent=[0, w_px, h_px, 0], zorder=0)
    cf = ax.contourf(gx, gy, zi, levels=100, cmap=delta_cmap, alpha=0.7,
                     vmin=-40, vmax=40, zorder=1, extend="both")
    for (a, b) in pairs:
        d = b["score"] - a["score"]
        ax.plot(a["x_px"], a["y_px"], "o", color="white", markersize=12,
                markeredgecolor="black", markeredgewidth=1.5, zorder=5)
        ax.annotate(f"{d:+.0f}", (a["x_px"], a["y_px"]), color="black",
                    fontsize=7, fontweight="bold", ha="center", va="center", zorder=6)
    if ap_xy is not None:
        ax.plot(ap_xy[0], ap_xy[1], "*", color="#FFD400", markersize=26,
                markeredgecolor="black", markeredgewidth=1.5, zorder=8)
        ax.annotate("AP", (ap_xy[0], ap_xy[1]), color="black", fontsize=8,
                    fontweight="bold", ha="center", va="center", zorder=9)
    cbar = fig.colorbar(cf, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label(f"Score difference ({name_b} − {name_a})", fontsize=11)
    ax.set_title(f"Performance Difference: {name_b} vs {name_a}\n"
                 f"green = {name_b} better · red = {name_b} worse",
                 fontsize=14, fontweight="bold")
    ax.axis("off"); ax.set_xlim(0, w_px); ax.set_ylim(h_px, 0)
    plt.tight_layout()
    fig.savefig(output_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"   Difference map saved: {output_png}")
    return output_png


def run_comparison(points, img, w_px, h_px, fp, samples, base_name, ap_xy=None,
                   meta=None):
    """
    Hamina-style A/B comparison (e.g. KGU vs DUT) on the SAME points.

    Measures device A across all points, then device B across the same points,
    and renders both heatmaps plus a difference map.
    """
    meta = dict(meta or {})
    name_a = input("  Device A name (e.g. KGU): ").strip() or "DeviceA"
    print(f"\n=== Measuring {name_a} — ensure ONLY this device is powered on ===")
    input(f"  Press Enter when ready to survey {name_a}...")
    meas_a = run_survey(points, samples=samples, ap_xy=ap_xy, img=img)

    name_b = input("\n  Device B name (e.g. DUT): ").strip() or "DeviceB"
    print(f"\n=== Now power OFF {name_a}, power ON {name_b} ===")
    input(f"  Press Enter when ready to survey {name_b} (same points)...")
    meas_b = run_survey(points, samples=samples, ap_xy=ap_xy, img=img)

    if len(meas_a) < 2 or len(meas_b) < 2:
        print("Not enough measurements collected. Exiting.")
        return

    out_dir = f"SURVEY_COMPARE_{base_name}"
    os.makedirs(out_dir, exist_ok=True)
    meta_a = dict(meta, ap_model=name_a, site=meta.get("site", base_name))
    meta_b = dict(meta, ap_model=name_b, site=meta.get("site", base_name))
    _render_survey_outputs(meas_a, fp, img, w_px, h_px, name_a, out_dir,
                           open_browser=False, ap_xy=ap_xy, planned_points=points,
                           meta=meta_a)
    _render_survey_outputs(meas_b, fp, img, w_px, h_px, name_b, out_dir,
                           open_browser=False, ap_xy=ap_xy, planned_points=points,
                           meta=meta_b)
    generate_delta_heatmap(meas_a, meas_b, img, w_px, h_px,
                           os.path.join(out_dir, f"heatmap_delta_{base_name}.png"),
                           name_a=name_a, name_b=name_b, ap_xy=ap_xy)

    # Score summary
    import numpy as _np
    avg_a = _np.mean([m["score"] for m in meas_a if m.get("score") is not None])
    avg_b = _np.mean([m["score"] for m in meas_b if m.get("score") is not None])
    print(f"\n=== Comparison summary ===")
    print(f"  {name_a}: avg score {avg_a:.1f}/100")
    print(f"  {name_b}: avg score {avg_b:.1f}/100")
    print(f"  Difference ({name_b} − {name_a}): {avg_b - avg_a:+.1f}")
    print(f"\nResults in: {out_dir}/")


def main():
    print("\n" + "=" * 70)
    print("  WiFi SITE SURVEY — Point-Based Heatmap Generator")
    print("=" * 70)

    if not _HAVE_TOOL:
        print(f"\nWARNING: Could not import measurement functions from wl_tool12.py")
        print(f"  ({_IMPORT_ERR})")
        print("  Measurement phase will not work. Exiting.")
        return

    # --- Mode ---
    print("\nMode:")
    print("  1. Single device survey")
    print("  2. Comparison survey (Device A vs B — e.g. KGU vs DUT)")
    try:
        mode = input("Select (1/2, Enter = 1): ").strip()
    except EOFError:
        mode = "1"

    # --- Floor plan (native Finder picker) ---
    fp = choose_floorplan()
    if not fp:
        print("No floor plan selected. Exiting.")
        return

    test_name = input("Survey name: ").strip() or "survey"

    # --- Optional report metadata ---
    ap_model = input("AP model (e.g. eero Max 7, or Enter to skip): ").strip()

    # AP mount type — changes the expected coverage shape on the map.
    print("\nAP mount type (affects how coverage is interpreted):")
    print("  1. Ceiling / overhead  — radiates evenly, roughly circular coverage")
    print("  2. Table-top / desk    — blocked by furniture/screens, shadow zones")
    try:
        mount_in = input("Select (1/2, Enter = 1): ").strip()
    except EOFError:
        mount_in = "1"
    mount_key = "tabletop" if mount_in == "2" else "ceiling"
    mprof = mount_profile(mount_key)
    print(f"  → {mprof['label']}: {mprof['note']}")

    tester = input("Tester name (or Enter to skip): ").strip()
    site = input("Site/location (or Enter to use survey name): ").strip()
    ssid = ""
    chan_raw = ""
    try:
        if _HAVE_TOOL:
            ssid = get_ssid() or ""
            chan_raw = str(get_wifi_channel() or "")
    except Exception:
        pass
    band_label, channel_num, bw_mhz = band_channel_label(chan_raw)
    meta = {
        "ap_model": ap_model or "—",
        "tester": tester or "—",
        "site": site or test_name,
        "ssid": ssid or "—",
        "band": band_channel_summary(chan_raw) if chan_raw else "—",
        "band_label": band_label,
        "channel": channel_num,
        "bw": bw_mhz,
        "mount": mount_key,
        "mount_label": mprof["label"],
        "mount_note": mprof["note"],
    }

    # --- Phase 1: place AP + points (shared by both devices in comparison mode) ---
    ap_xy, points, img, w_px, h_px = place_ap_and_points(fp)
    if len(points) < 2:
        print("Need at least 2 measurement points. Exiting.")
        return
    ap_note = "AP placed" if ap_xy else "no AP marked"
    print(f"\n{len(points)} measurement points placed ({ap_note}).")

    try:
        samples = int(input("Samples per point (default 3): ").strip() or "3")
    except ValueError:
        samples = 3
    meta["samples"] = str(samples)

    # --- Comparison flow (Hamina-style A/B on the same points) ---
    if mode == "2":
        run_comparison(points, img, w_px, h_px, fp, samples, test_name,
                       ap_xy=ap_xy, meta=meta)
        return

    # --- Single-device flow ---
    measurements = run_survey(points, samples=samples, ap_xy=ap_xy, img=img)
    if len(measurements) < 2:
        print("Not enough measurements collected. Exiting.")
        return

    out_dir = f"SURVEY_{test_name}"
    os.makedirs(out_dir, exist_ok=True)
    _render_survey_outputs(measurements, fp, img, w_px, h_px, test_name, out_dir,
                           open_browser=True, ap_xy=ap_xy, planned_points=points,
                           meta=meta)
    print(f"\nSurvey complete. Results in: {out_dir}/")


if __name__ == "__main__":
    main()
