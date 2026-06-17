# 📡 Wireless Engineer's Diagnostic Suite v2.9

**The ultimate wireless network diagnostic tool for field engineers, network professionals, and production testing.**

## 🎯 Overview

This comprehensive diagnostic tool provides real-time wireless network analysis with advanced features including interference detection, roaming analysis, automated troubleshooting, intelligent band steering recommendations, professional PDF reports, **and production-grade comparative testing mode for KGU vs DUT comparison**.

## ✨ Key Features

### 🆕 Comparative Testing Mode (v2.9)
- **Production-grade KGU vs DUT comparison** - Back-to-back testing with scientific pass/fail criteria
- **Three primary test criteria**:
  - Peak download/upload speeds (±10% tolerance)
  - Peak MCS vs RSSI (±1 MCS tolerance)
  - RSSI ramp down to MCS ramp down (correlation analysis)
- **Scientific tolerances** - Based on TR-398, IEEE 802.11, and industry standards
- **Automated comparison engine** - Instant pass/fail decision with overall score (0-100)
- **Professional comparative reports** - Side-by-side comparison with disposition
- **NTF detection** - Differentiates true failures from No Trouble Found units
- **Quality assurance** - Objective testing for manufacturing and RMA processes

### Core Diagnostics
- **Real-time RSSI monitoring** with live graphing
- **MCS Index tracking** for modulation analysis
- **Tx Rate and Latency** measurements
- **Signal-to-Noise Ratio (SNR)** calculation
- **Channel utilization** monitoring (CCA)
- **PHY mode and NSS** detection
- **Distance estimation** from AP based on RSSI
- **BSSID tracking** with sudo (no more `<redacted>`)

### Advanced Analysis
- **🔍 Interference Detection** - Identifies specific interference sources and congestion issues
- **🔄 Roaming Analysis** - Tracks AP transitions with BSSID monitoring
- **🌐 Mesh Network Detection** - Identifies and tracks mesh node connections
- **💡 Band Steering Recommendations** - Suggests optimal band/channel based on environment
- **🔧 Automated Troubleshooting** - Provides actionable remediation steps for detected issues
- **📊 Network Health Scoring** - Evaluates overall connection quality

### Network Scanning
- **Multi-band scanning** (2.4GHz, 5GHz, 6GHz)
- **Channel congestion analysis** - Identifies least/most crowded channels per band
- **Neighbor network discovery** - Counts nearby APs per band

### Data Export & Reporting
- **🆕 Comparative PDF Reports** - Professional KGU vs DUT comparison with pass/fail disposition
- **Comprehensive PDF Reports** - Professional technical reports with 7 sections:
  - Test Information (AP Model, SSID, channel, duration)
  - Network Sanity Check (PASSED/FAILED)
  - Overall Performance Summary (statistics table)
  - Roaming & Mesh Network Analysis
  - Interference & Issues Detected
  - Detailed Iteration Analysis (every 10 iterations)
  - Recommendations & Conclusions
- **Enhanced CSV Export** - 16 KPIs including SSID, Channel, BSSID, RSSI, SNR, Noise, Tx Rate, Latency, MCS, PHY, NSS, Channel Util, Distance, Health
- **JSON Export** - Structured data with mesh topology, roaming events, and interference logs
- **Live Plots** - 8-panel real-time visualization with Rate vs Range curves
- **Text Logs** - Detailed iteration-by-iteration diagnostics

## 📋 Requirements

### System Requirements
- **macOS** (uses CoreWLAN and wdutil)
- **Python 3.7+**
- **sudo privileges** (required for wdutil commands and BSSID retrieval)

### Python Dependencies
```bash
pip install pyobjc speedtest-cli matplotlib reportlab
```

## 🚀 Quick Start

1. **Install dependencies:**
```bash
pip install pyobjc speedtest-cli matplotlib reportlab
```

2. **Run the tool:**
```bash
python3 wl_tool12.py
```

3. **Follow the prompts:**
   - Enter test name (creates RUN_<testname> folder)
   - Set sample interval (default: 2 seconds)
   - Wait for network sanity check
   - Monitor live diagnostics
   - Type 'q' + Enter to stop

## 📊 Output Files

Each test run creates a dedicated folder with:

| File | Description |
|------|-------------|
| `network_diagnostics_<test>.txt` | Detailed iteration logs |
| `network_diagnostics_plot_<test>.png` | 5-panel visualization |
| `diagnostics_<test>.csv` | Time-series data (RSSI, Tx, Latency, SNR, etc.) |
| `diagnostics_<test>.json` | Roaming events & interference incidents |
| `network_report_<test>.pdf` | Professional summary report (optional) |
| `comparative_report_<timestamp>.pdf` | KGU vs DUT comparison report (comparative mode) |

## 🔬 Comparative Testing Mode (v2.9)

### What is Comparative Testing?

Comparative mode enables production-grade testing by comparing a **Known Good Unit (KGU)** against a **Device Under Test (DUT)**. This is ideal for:
- **Production testing** - Quality assurance in manufacturing
- **RMA testing** - Differentiating true failures from NTF (No Trouble Found)
- **Quality control** - Objective pass/fail decisions

### How to Use

1. **Start the tool and select mode 2**:
```bash
sudo python3 wl_tool12.py
Select test mode (1 or 2): 2
```

2. **Phase 1: Test KGU**
   - Ensure KGU is the ONLY router powered on
   - Connect laptop to KGU
   - Run test (press 'q' to stop)

3. **Transition**
   - Power OFF KGU
   - Power ON DUT
   - Connect laptop to DUT

4. **Phase 2: Test DUT**
   - Run same test on DUT

5. **Phase 3: Automated Comparison**
   - Tool compares KGU vs DUT
   - Displays PASS/FAIL with score (0-100)
   - Generates comparative PDF report

### Test Criteria

| Metric | ✅ Pass | ⚠️ Warn | ❌ Fail |
|--------|---------|---------|---------|
| **Peak Throughput** | ±10% | ±15% | >±15% |
| **Peak MCS** | ±1 index | ±2 index | >±2 index |
| **RSSI-MCS Correlation** | ±1.5 MCS | ±2.5 MCS | >±2.5 MCS |
| **Average RSSI** | ±3dB | ±5dB | >±5dB |
| **Average Latency** | ±20% | ±30% | >±30% |
| **Roaming Events** | ≤2 extra | ≤5 extra | >5 extra |

### Example Output

```
🎯 COMPARATIVE TEST RESULTS

Overall Result: PASS
Overall Score: 92/100

✅ Peak Throughput: -2.5% (PASS)
✅ Peak MCS: -1 (PASS)
✅ RSSI-MCS Correlation: 1.2 (PASS)
✅ Avg RSSI: -1.5dB (PASS)
✅ Avg Latency: +13.6% (PASS)
✅ Roaming: +1 (PASS)

DISPOSITION: PASS - Unit Acceptable
Recommendation: Approve for shipment
```

### Documentation
- **Comprehensive Guide**: `COMPARATIVE_TESTING_GUIDE.md`
- **Quick Reference**: `COMPARATIVE_MODE_QUICK_REF.md`
- **Release Notes**: `v2.9_COMPARATIVE_MODE.md`

## 🎨 Live Visualization

The tool displays 8 real-time plots:

1. **RSSI Over Time** - Signal strength tracking
2. **MCS Index** - Modulation scheme
3. **SNR** - Signal-to-noise ratio with thresholds
4. **Rate vs Range** - MCS and SNR vs Distance (NEW in v2.7)
5. **Tx Rate** - Throughput
6. **Latency** - Network latency
7. **Distance** - Estimated distance from AP
8. **Network Count by Band** - Nearby AP distribution

## 🔧 Troubleshooting Features

The tool automatically detects and provides remediation steps for:

- **Weak Signal Strength** (RSSI < -75 dBm)
- **Poor SNR** (< 20 dB)
- **High Latency** (> 100 ms)
- **Low Throughput** (< 100 Mbps)
- **Channel Congestion** (CU > 60%)
- **Interference Sources**

### Example Output:
```
🔧 TROUBLESHOOTING GUIDE:

  ⚠️  Weak Signal Strength [Severity: HIGH]
  Steps to resolve:
    → Move closer to the access point
    → Check for physical obstructions (walls, metal objects)
    → Verify AP antenna orientation
    → Consider adding a wireless repeater or mesh node
```

## 💡 Band Steering Recommendations

Every 10 iterations, the tool analyzes the RF environment and provides:

- **Band recommendations** - Suggests switching to less congested bands
- **Channel recommendations** - Identifies least crowded channels
- **Congestion comparison** - Shows network counts across bands

### Example:
```
💡 RECOMMENDATIONS:
  • Consider switching to 5GHz band (only 8 networks vs 23 on current band)
  • Within 2.4GHz, channel 11 is less crowded than current channel 6
```

## 🔄 Roaming Detection

Tracks AP transitions in real-time:
```
⚠️  ROAMING EVENT: aa:bb:cc:dd:ee:ff → 11:22:33:44:55:66
```

Frequent roaming alerts indicate potential coverage issues.

## 📈 Network Health Scoring

Evaluates connection quality based on:
- RSSI strength
- Tx Rate performance
- MCS Index efficiency

**Ratings:** Excellent | Good | Bad

## 🎯 Use Cases

### Field Engineers
- Site surveys and coverage validation
- Interference source identification
- AP placement optimization
- Client connectivity troubleshooting

### Network Administrators
- Performance baseline establishment
- Capacity planning
- QoS validation
- Roaming behavior analysis

### Home Users
- WiFi optimization
- Dead zone identification
- Channel selection
- ISP performance validation

## 📝 CSV Data Format

```csv
Timestamp,RSSI,TxRate,Latency,MCS,ChannelUtil,Noise,SNR,BSSID
12.34,-65,866,15,9,45,-90,25,aa:bb:cc:dd:ee:ff
```

## 🔐 Permissions

The tool requires sudo access for:
- `wdutil info` - Wireless diagnostics utility
- Channel and noise floor measurements
- BSSID and advanced metrics

## ⚙️ Configuration

### Sample Interval
Adjust based on your needs:
- **Fast (1-2s)** - Roaming analysis, rapid changes
- **Normal (2-5s)** - General diagnostics
- **Slow (5-10s)** - Long-term monitoring, battery conservation

### Speedtest Frequency
Runs every 10 iterations by default. Modify in code:
```python
if iteration % 10 == 0:  # Change 10 to desired frequency
    ping, dl, ul = get_speedtest()
```

## 🐛 Known Limitations

- **macOS only** - Uses CoreWLAN framework
- **Requires sudo** - For wdutil access
- **Speedtest rate limiting** - May skip tests if server blocks requests
- **6GHz detection** - Requires compatible hardware and macOS version

## 📚 Technical Details

### Metrics Explained

| Metric | Description | Good Range |
|--------|-------------|------------|
| RSSI | Received Signal Strength | > -65 dBm |
| SNR | Signal-to-Noise Ratio | > 20 dB |
| MCS | Modulation & Coding Scheme | 7-11 (optimal) |
| Tx Rate | Transmit data rate | > 200 Mbps |
| CU | Channel Utilization | < 60% |
| Latency | Round-trip ping time | < 50 ms |

### Distance Estimation
Uses path loss model:
```
Distance = 10^((TxPower - RSSI) / (10 * PathLossExponent)) - 1
```
Default: TxPower = -30 dBm, Exponent = 3.2 (indoor)

## 🤝 Contributing

Suggestions and improvements welcome! This tool is designed for wireless professionals by wireless professionals.

## 📄 License

Created by Anish Dutta  
Version 2.0 - February 5, 2026

## 🆘 Support

For issues or questions:
1. Check sudo permissions
2. Verify PyObjC installation
3. Ensure WiFi is connected before running
4. Review log files in RUN_<testname> folder

---

**Happy Diagnosing! 📡✨**
