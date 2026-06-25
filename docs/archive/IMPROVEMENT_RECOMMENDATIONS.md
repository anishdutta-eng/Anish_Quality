# Wireless Diagnostic Tool — Improvement Recommendations

## Competitive Landscape Analysis

Your tool was compared against these industry solutions:

| Tool | Price | Key Strength | Your Tool's Gap |
|------|-------|-------------|-----------------|
| Ekahau Pro | ~$5,000/yr | Floor plan overlay heatmaps, AI-powered AP placement, spectrum analysis | No floor plan support, no spectrum analysis |
| NetSpot Pro | ~$500 | Visual heatmap on floor plan, multi-floor, zone planning | No floor plan overlay |
| WiFi Explorer Pro | ~$100 | Deep 802.11 frame analysis, channel overlap visualization | No frame-level analysis |
| WLAN Pi | ~$200 (hw) | iperf3 integration, packet capture, portable | No iperf3 integration |
| Cisco DNA Spaces | Enterprise | Cloud analytics, historical trending, client tracking | No cloud/historical |

Your tool's unique advantage: **free, single-script, macOS-native, real-time comparative testing (KGU vs DUT) with automated pass/fail disposition** — no commercial tool does this out of the box for consumer AP field returns.

---

## Recommendations (Prioritized)

### HIGH IMPACT — Technical Capabilities

#### 1. iperf3 Integration for Real Throughput Measurement
**Why:** Your current "Tx Rate" is the PHY rate reported by the driver — not actual application throughput. A client showing 2401 Mbps PHY rate might only deliver 400 Mbps real throughput due to protocol overhead, retransmissions, and airtime contention. Ekahau and WLAN Pi both use iperf3 for this.

**How:** Run an iperf3 server on a wired machine behind the AP. The tool connects as iperf3 client and measures actual TCP/UDP throughput. This gives you real-world numbers instead of theoretical PHY rates.

**Impact:** Transforms the report from "what the radio says" to "what the user actually gets." This is the single biggest technical gap.

#### 2. Floor Plan Overlay Heatmap
**Why:** Every professional WiFi survey tool (Ekahau, NetSpot, WiFi Explorer) overlays measurements on a floor plan image. Your radial heatmap is useful but doesn't show real spatial context — walls, rooms, hallways.

**How:** Let the user load a floor plan image (PNG/JPG). On each iteration, the user clicks their approximate position on the floor plan. RSSI/MCS data is plotted at that position. Use scipy interpolation to fill in the gaps, exactly like your current heatmap but on a real map.

**Impact:** Makes the report immediately understandable to non-technical stakeholders. "The signal is weak in the bedroom" vs "the signal is weak at 15m estimated distance."

#### 3. 802.11 Retransmission & Frame Error Rate
**Why:** Retransmissions are the #1 hidden cause of WiFi performance problems. A link can show MCS 11 and -30 dBm RSSI but still perform terribly if 20% of frames are being retransmitted. macOS exposes Tx/Rx error counters via `netstat -I en0` and `networksetup`.

**How:** Sample `netstat -I en0` at each iteration to get Tx/Rx packet counts and error counts. Calculate retransmission rate as `(errors / total_packets) * 100`. Add to the report as a key metric.

**Impact:** Catches problems that RSSI/MCS alone cannot detect — interference, hidden node issues, driver bugs.

#### 4. Jitter Measurement
**Why:** Latency alone doesn't tell the full story. Jitter (variation in latency) is critical for VoIP and video. A connection with 25ms average latency but 50ms jitter is worse than 40ms with 2ms jitter.

**How:** You already run `ping -c 5`. Parse the min/avg/max/stddev from the output. Jitter = stddev. Add to CSV, plots, and PDF report.

**Impact:** Completes the latency picture. Important for VoIP/video quality assessment.

---

### MEDIUM IMPACT — User Interface

#### 5. Rich Terminal UI (TUI) Dashboard
**Why:** Your current output is sequential print statements that scroll off screen. Professional tools like `htop`, `btop`, and `wifitui` use terminal UI frameworks to show a persistent dashboard with live-updating panels.

**How:** Use Python's `rich` library (or `textual` for full TUI). Create a dashboard layout with panels for: current metrics, mini sparkline charts, health status, alerts. All updating in-place without scrolling.

**Impact:** Dramatically improves the live monitoring experience. The tester can see everything at a glance instead of scrolling through output.

#### 6. Non-Blocking Input (No More "Press q + Enter")
**Why:** Currently the user must type 'q' + Enter to stop, which requires switching focus from the matplotlib window to the terminal. This is clunky.

**How:** Use `select.select()` on stdin (Unix) or a keyboard listener thread to detect keypress without blocking. The user just presses 'q' — no Enter needed.

**Impact:** Smoother workflow, especially during walk tests where the tester is moving.

#### 7. Progress Bar & ETA for Long Operations
**Why:** Speedtest and network sanity check can take 30+ seconds with no feedback. The user doesn't know if it's working or hung.

**How:** Use `rich.progress` or a simple spinner animation during speedtest and sanity check.

**Impact:** Better user experience during wait times.

---

### MEDIUM IMPACT — Technical Depth

#### 8. Channel Overlap & Co-Channel Interference Visualization
**Why:** Your tool scans nearby networks but only shows counts per band. Professional tools show which specific channels are congested and how much overlap exists.

**How:** Parse the full scan output to get each neighbor's channel and signal strength. Plot a channel utilization chart showing signal levels per channel (like WiFi Explorer's channel graph). Identify co-channel and adjacent-channel interference.

**Impact:** Gives actionable channel selection recommendations backed by data.

#### 9. Historical Trend Database
**Why:** Currently each test run is independent. There's no way to compare "how did this AP perform last week vs today?" or track degradation over time.

**How:** Store results in a SQLite database (one file, no server needed). Add a "trend" mode that plots historical RSSI/MCS/throughput for a given SSID over multiple test sessions.

**Impact:** Enables longitudinal analysis — critical for detecting gradual degradation or validating that a fix actually worked.

#### 10. OFDMA & BSS Color Detection (802.11ax specific)
**Why:** 802.11ax introduced OFDMA (multi-user frequency division) and BSS Coloring (spatial reuse). These are key differentiators of Wi-Fi 6 but your tool doesn't report them.

**How:** macOS `wdutil info` may expose some of this. Alternatively, parse the `system_profiler SPAirPortDataType` output which shows more detailed 802.11ax capabilities.

**Impact:** Makes the report truly 802.11ax-aware, not just "it says 11ax in the PHY field."

---

### LOWER IMPACT — Polish & Packaging

#### 11. Single Binary Distribution (PyInstaller)
**Why:** Currently requires Python 3, pip, and manual dependency installation. Non-technical testers struggle with setup.

**How:** Package with PyInstaller into a single `.app` (macOS) or executable. Include all dependencies.

**Impact:** Zero-install deployment for field testers.

#### 12. Configuration File
**Why:** Hardcoded thresholds (-50/-65 dBm, path loss exponent 2.7, etc.) may not suit every environment. An office with concrete walls needs different parameters than an open-plan space.

**How:** YAML/JSON config file for thresholds, path loss model parameters, speedtest server, iperf3 server address, etc.

**Impact:** Adaptable to different environments without code changes.

#### 13. Multi-AP Mesh Topology Visualization
**Why:** You detect roaming events but don't visualize the mesh topology. For mesh networks (eero, Google WiFi, UniFi), showing which node the client connected to and when is valuable.

**How:** Plot a timeline showing BSSID transitions with signal strength at each node. Show a simple topology diagram (node A → node B → node C).

**Impact:** Helps diagnose mesh handoff issues and sticky client problems.

#### 14. Automated Test Profiles
**Why:** Every test requires manual input (AP model, SSID, test name). For repetitive testing (e.g., testing 50 field return units), this is tedious.

**How:** Save test profiles (AP model, SSID, thresholds, duration) to a config file. Load with `--profile field_return_5ghz`.

**Impact:** Faster repetitive testing workflows.

---

## Priority Roadmap

### Phase 1 (Highest ROI)
1. iperf3 integration — real throughput measurement
2. Retransmission rate from netstat
3. Jitter from ping stddev

### Phase 2 (User Experience)
4. Rich TUI dashboard
5. Non-blocking keyboard input
6. Floor plan overlay heatmap

### Phase 3 (Technical Depth)
7. Channel overlap visualization
8. Historical SQLite database
9. OFDMA/BSS Color detection

### Phase 4 (Polish)
10. PyInstaller packaging
11. Config file for thresholds
12. Automated test profiles

---

## What You Already Do Better Than Most

- **Comparative KGU vs DUT testing** — unique to your tool, no commercial equivalent
- **Automated pass/fail disposition** — scientific criteria, not subjective
- **Kalman-filtered coverage heatmap** — more accurate than raw RSSI plotting
- **802.11ax MCS reference table in PDF** — professional-grade documentation
- **Per-iteration data table** — full audit trail
- **Zero cost, single script** — no license fees, no hardware required

The tool is already production-grade for its intended use case (consumer AP field return diagnostics). The recommendations above would elevate it from a field diagnostic tool to a comprehensive wireless engineering platform.
