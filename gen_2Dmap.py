#!/usr/bin/env python3
import subprocess
import re
import argparse
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from matplotlib.colors import ListedColormap, BoundaryNorm
import matplotlib.patches as mpatches

def get_mcs_index():
    """Return MCS index (integer) via wdutil."""
    try:
        out = subprocess.check_output(
            "sudo wdutil info | grep 'MCS Index' | cut -d ':' -f2",
            shell=True,
            universal_newlines=True,
            timeout=5
        ).strip()
        m = re.search(r"\d+", out)
        return int(m.group(0)) if m else None
    except Exception:
        return None

def scan_rssi():
    """Scan and return RSSI (dBm) using wdutil info pipeline."""
    try:
        rssi_str = subprocess.check_output(
            "sudo wdutil info | egrep RSSI | cut -d ':' -f2",
            shell=True,
            universal_newlines=True,
            timeout=5
        ).strip()
        match = re.search(r"-?\d+", rssi_str)
        if match:
            return int(match.group(0))
        else:
            print(f"Could not parse numeric RSSI from: '{rssi_str}'")
    except subprocess.CalledProcessError:
        print("Failed to run wdutil info. Ensure wdutil is installed and you have sudo privileges.")
    except Exception as e:
        print(f"Unexpected error reading RSSI: {e}")
    return None

def estimate_distance(rssi, p0, n):
    """Estimate distance from RSSI, reference RSSI p0 at 1m, path‑loss exponent n."""
    return 10 ** ((p0 - rssi) / (10 * n))

def collect_measurements(p0, n):
    """
    Walk‑around data collection.  
    Press Enter to take a reading, or 'q'+Enter to quit.
    """
    data = []
    print(">>> Debug: Starting measurements. Ensure you run with sudo privileges.")
    while True:
        try:
            cmd = input("Scan? [Enter to scan, q+Enter to finish]: ")
        except EOFError:
            print(">>> Debug: No more input (EOF). Ending collection.")
            break

        if cmd.strip().lower() == 'q':
            print(">>> Debug: Received quit command.")
            break

        # read RSSI & MCS
        rssi = scan_rssi()
        mcs  = get_mcs_index()

        # debug prints
        print(f">>> Debug: scan_rssi() → {rssi}, get_mcs_index() → {mcs}")

        if rssi is None or mcs is None:
            print("  ❗ Failed to read RSSI or MCS. Retrying...")
            continue

        d = estimate_distance(rssi, p0, n)
        data.append((d, rssi, mcs))
        print(f"  ✔ Recorded: RSSI={rssi} dBm, MCS={mcs}, dist={d:.2f} m")

    return data

def generate_coords(distances):
    """Generate (x,y) coordinates evenly spaced in angle around the AP."""
    N = len(distances)
    angles = np.linspace(0, 2*np.pi, N, endpoint=False)
    xs = distances * np.cos(angles)
    ys = distances * np.sin(angles)
    return xs, ys

def plot_maps(xs, ys, rssis, mcs_vals,
              good_rssi, excellent_rssi,
              good_mcs, excellent_mcs,
              p0, output_prefix):
    """Plot 2D heatmap, combined coverage with movement vectors, and 3D surface."""
    # interpolate RSSI
    xi = np.linspace(xs.min(), xs.max(), 200)
    yi = np.linspace(ys.min(), ys.max(), 200)
    xi, yi = np.meshgrid(xi, yi)
    zi = griddata((xs, ys), rssis, (xi, yi), method='cubic',
                  fill_value=good_rssi - 20)

    # classify samples
    sample_class = np.zeros_like(rssis, dtype=int)
    for i, (r, m) in enumerate(zip(rssis, mcs_vals)):
        if r >= excellent_rssi and m >= excellent_mcs:
            sample_class[i] = 2
        elif r >= good_rssi and m >= good_mcs:
            sample_class[i] = 1

    # grid the classifications
    class_grid = griddata((xs, ys), sample_class, (xi, yi),
                          method='nearest', fill_value=0)

    # compute movement vectors
    dx = np.diff(xs)
    dy = np.diff(ys)
    bx = xs[:-1]
    by = ys[:-1]
    dots = dx * bx + dy * by
    arrow_colors = ['green' if d>0 else 'red' for d in dots]

    fig = plt.figure(figsize=(20, 6))

    # 1) 2D RSSI heatmap + path + arrows
    ax1 = fig.add_subplot(1, 3, 1)
    hm = ax1.contourf(xi, yi, zi, levels=50, cmap='viridis')
    ax1.plot(xs, ys, '--', lw=2, alpha=0.7, label='Path')
    ax1.quiver(bx, by, dx, dy,
               color=arrow_colors,
               scale_units='xy', angles='xy', scale=1, width=0.005,
               label='Movement')
    ax1.scatter(xs[0], ys[0], c='blue', marker='o', s=80, label='Start')
    ax1.scatter(xs[-1], ys[-1], c='magenta', marker='X', s=80, label='End')
    ax1.scatter(0, 0, c='white', edgecolor='k', s=120, marker='*', label='AP')
    ax1.set(title='RSSI Heatmap with Movement',
            xlabel='X (m)', ylabel='Y (m)')
    ax1.legend(loc='upper right')
    fig.colorbar(hm, ax=ax1, label='RSSI (dBm)')

    # 2) 2D Combined coverage + overlays
    ax2 = fig.add_subplot(1, 3, 2)
    colors = ['red','yellow','green']
    cmap_cov = ListedColormap(colors)
    norm_cov = BoundaryNorm([0,1,2,3], cmap_cov.N)
    cm2 = ax2.contourf(xi, yi, class_grid,
                       levels=[-0.5,0.5,1.5,2.5],
                       cmap=cmap_cov, norm=norm_cov)
    ax2.plot(xs, ys, '--', lw=2, alpha=0.7)
    ax2.quiver(bx, by, dx, dy,
               color=arrow_colors,
               scale_units='xy', angles='xy', scale=1, width=0.005)
    ax2.scatter(xs[0], ys[0], c='blue', marker='o', s=80)
    ax2.scatter(xs[-1], ys[-1], c='magenta', marker='X', s=80)
    ax2.scatter(0, 0, c='k', edgecolor='w', s=120, marker='*')
    ax2.set(
        title=f"Coverage Map\n(RSSI ≥ {good_rssi}/{excellent_rssi} dBm & MCS ≥ {good_mcs}/{excellent_mcs})",
        xlabel='X (m)', ylabel='Y (m)'
    )
    patches = [mpatches.Patch(color=colors[i], label=l)
               for i,l in enumerate(['Bad','Good','Excellent'])]
    ax2.legend(handles=patches, loc='upper right')
    fig.colorbar(cm2, ax=ax2, ticks=[0,1,2], label='Coverage')

    # 3) 3D RSSI surface
    ax3 = fig.add_subplot(1, 3, 3, projection='3d')
    surf = ax3.plot_surface(xi, yi, zi, cmap='viridis', edgecolor='none')
    ax3.scatter(0, 0, p0, c='r', s=60, marker='*', label='AP')
    ax3.set(title='3D RSSI Surface',
            xlabel='X (m)', ylabel='Y (m)', zlabel='RSSI (dBm)')
    fig.colorbar(surf, ax=ax3, shrink=0.5, aspect=10)

    plt.tight_layout()
    out_png = f"{output_prefix}_vectorized.png"
    fig.savefig(out_png, dpi=300)
    print(f"Saved enriched coverage & vector map → {out_png}")

if __name__ == '__main__':
    # One‑shot sanity check
    print(">>> One‑shot test of RSSI & MCS readers:")
    print("    RSSI:", scan_rssi())
    print("    MCS: ", get_mcs_index())
    print()

    parser = argparse.ArgumentParser("WiFi Coverage with Vectorized Paths")
    parser.add_argument('-p0', type=float, default=-40, help="RSSI @1m (dBm)")
    parser.add_argument('-n',  type=float, default=2.0, help="Path-loss exponent")
    parser.add_argument('-g', '--good',      type=float, default=-65, help="RSSI threshold for Good")
    parser.add_argument('-e', '--excellent', type=float, default=-50, help="RSSI threshold for Excellent")
    parser.add_argument('--mcs-good',      type=int, default=3, help="MCS index threshold for Good")
    parser.add_argument('--mcs-excellent', type=int, default=7, help="MCS index threshold for Excellent")
    parser.add_argument('-o', '--output', default='wifi_maps', help="Output filename prefix")
    args = parser.parse_args()

    measurements = collect_measurements(args.p0, args.n)
    if not measurements:
        print("No measurements collected; exiting.")
        exit(1)

    dists, rssis, mcs_vals = zip(*measurements)
    xs, ys = generate_coords(np.array(dists))

    plot_maps(xs, ys,
              np.array(rssis),
              np.array(mcs_vals),
              args.good, args.excellent,
              args.mcs_good, args.mcs_excellent,
              args.p0, args.output)
