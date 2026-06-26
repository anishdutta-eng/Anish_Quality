# 📡 Wireless Engineer's Diagnostic Suite v2.0

## 🎯 Project Overview

**The most comprehensive wireless network diagnostic tool for macOS.**

Built for wireless engineers, network administrators, and IT professionals who need deep insights into WiFi performance, interference, and connectivity issues.

---

## 📦 What's Included

### Core Application
- **wl_tool12.py** (30KB) - Main diagnostic tool with all features

### Documentation
- **QUICK_START.md** (4.8KB) - Get started in 3 minutes
- **README.md** (7.0KB) - Complete documentation
- **FIELD_GUIDE.md** (7.2KB) - Quick reference for field work
- **FAQ.md** (11KB) - Answers to common questions
- **FEATURES_COMPARISON.md** (9.2KB) - v1.2 vs v2.0 comparison

### Setup
- **setup.sh** (1.9KB) - Automated dependency installer

---

## ✨ Key Features at a Glance

### Real-Time Monitoring
- ✅ RSSI (Signal Strength)
- ✅ SNR (Signal-to-Noise Ratio)
- ✅ MCS Index (Modulation Scheme)
- ✅ Tx Rate (Throughput)
- ✅ Latency (Ping Time)
- ✅ Channel Utilization
- ✅ PHY Mode & NSS
- ✅ Distance Estimation

### Advanced Analysis
- 🔍 **Interference Detection** - Identifies noise and congestion
- 🔄 **Roaming Analysis** - Tracks AP transitions
- 💡 **Band Steering** - Recommends optimal band/channel
- 🔧 **Auto Troubleshooting** - Provides remediation steps
- 📊 **Health Scoring** - Evaluates connection quality

### Network Scanning
- 📡 Multi-band scanning (2.4/5/6 GHz)
- 📊 Channel congestion analysis
- 🔍 Neighbor network discovery
- 📈 Least/most crowded channels

### Data Export
- 📄 CSV - Time-series data
- 📋 JSON - Structured events
- 📊 PDF - Professional reports
- 📈 PNG - Live visualizations
- 📝 TXT - Detailed logs

---

## 🎨 Visual Output

### 5-Panel Live Dashboard
```
┌─────────────────────────────────────┐
│  Panel 1: RSSI & MCS Index         │
│  Real-time signal & modulation     │
├─────────────────────────────────────┤
│  Panel 2: Tx Rate & Latency        │
│  Throughput and response time      │
├─────────────────────────────────────┤
│  Panel 3: RSSI vs MCS Correlation  │
│  Signal quality analysis           │
├─────────────────────────────────────┤
│  Panel 4: Network Count by Band    │
│  RF environment overview           │
├─────────────────────────────────────┤
│  Panel 5: SNR Tracking             │
│  Signal quality over time          │
└─────────────────────────────────────┘
```

### Console Output
```
================================================================================
📊 COMPREHENSIVE ANALYSIS - Iteration 10
================================================================================
🏥 Network Health: Good

📡 Nearby Wi-Fi Networks:
  2.4GHz: 23 networks | Least crowded: Ch 11 | Most crowded: Ch 6
  5GHz: 8 networks | Least crowded: Ch 149 | Most crowded: Ch 36
  6GHz: 2 networks | Least crowded: Ch 37 | Most crowded: Ch 53

💡 RECOMMENDATIONS:
  • Consider switching to 5GHz band (only 8 networks vs 23 on current band)

🔧 TROUBLESHOOTING GUIDE:
  ⚠️  High Latency [Severity: MEDIUM]
  Steps to resolve:
    → Check for bandwidth-heavy applications
    → Verify QoS settings on router

🔄 Roaming Events: 2 total
================================================================================
```

---

## 🎯 Use Cases

### 1. Site Surveys
- Map coverage across locations
- Identify dead zones
- Validate AP placement
- Optimize channel selection

### 2. Troubleshooting
- Diagnose connectivity issues
- Identify interference sources
- Analyze roaming behavior
- Validate fixes

### 3. Performance Baseline
- Establish normal metrics
- Track changes over time
- Capacity planning
- SLA validation

### 4. Client Issues
- Isolate wireless vs wired problems
- Verify client capabilities
- Check signal quality
- Analyze roaming patterns

### 5. Network Optimization
- Find best channels
- Optimize band steering
- Reduce interference
- Improve coverage

---

## 📊 Technical Specifications

### System Requirements
- **OS:** macOS 10.15+ (Catalina or newer)
- **Python:** 3.7+
- **Privileges:** sudo access required
- **Hardware:** Built-in WiFi or compatible adapter

### Dependencies
- **pyobjc** - CoreWLAN framework access
- **speedtest-cli** - Bandwidth testing
- **matplotlib** - Data visualization
- **reportlab** - PDF generation

### Performance
- **CPU Usage:** Low (5-10% typical)
- **Memory:** ~100-200 MB
- **Disk:** ~1-5 MB per test
- **Network:** Minimal (except speedtest)

### Data Collection
- **Sample Rate:** 1-10 seconds (configurable)
- **Metrics:** 9 primary + derived
- **Speedtest:** Every 10 iterations (configurable)
- **Network Scan:** Every 10 iterations

---

## 🚀 Quick Comparison

### Before v2.0
```
❌ Manual interpretation required
❌ No interference detection
❌ No roaming analysis
❌ Limited export options
❌ Basic troubleshooting
❌ No recommendations
```

### With v2.0
```
✅ Automated analysis
✅ Advanced interference detection
✅ Real-time roaming tracking
✅ CSV/JSON/PDF exports
✅ Step-by-step troubleshooting
✅ Intelligent recommendations
```

---

## 📈 Metrics Collected

### Primary Metrics
| Metric | Unit | Update Rate | Source |
|--------|------|-------------|--------|
| RSSI | dBm | Every iteration | wdutil |
| Noise | dBm | Every iteration | wdutil |
| SNR | dB | Calculated | RSSI - Noise |
| Tx Rate | Mbps | Every iteration | wdutil |
| MCS Index | 0-11 | Every iteration | wdutil |
| Latency | ms | Every iteration | ping |
| Channel | Number | Every 5 iterations | wdutil |
| CU | % | Every iteration | wdutil |
| BSSID | MAC | Every iteration | wdutil |

### Derived Metrics
- Distance estimation (meters)
- Network health score
- Interference indicators
- Roaming frequency
- Band congestion

### Periodic Tests
- Speedtest (every 10 iterations)
- Network scan (every 10 iterations)
- Comprehensive analysis (every 10 iterations)

---

## 🎓 Learning Path

### Beginner (Day 1)
1. Read **QUICK_START.md**
2. Run first test
3. Understand RSSI and SNR
4. Follow recommendations

### Intermediate (Week 1)
1. Read **FIELD_GUIDE.md**
2. Conduct site survey
3. Export and analyze CSV data
4. Interpret all metrics

### Advanced (Month 1)
1. Read **README.md** fully
2. Customize for your needs
3. Integrate with other tools
4. Develop troubleshooting workflows

### Expert (Ongoing)
1. Contribute improvements
2. Share best practices
3. Train others
4. Build automation

---

## 🔧 Customization Options

### Easy (No coding)
- Sample interval
- Test naming
- Export selection
- Report generation

### Medium (Basic coding)
- Speedtest frequency
- Analysis thresholds
- Plot appearance
- Log format

### Advanced (Python knowledge)
- New metrics
- Custom analysis
- Additional plots
- Integration APIs

---

## 📊 Output Examples

### CSV Export
```csv
Timestamp,RSSI,TxRate,Latency,MCS,ChannelUtil,Noise,SNR,BSSID
12.34,-65,866,15,9,45,-90,25,aa:bb:cc:dd:ee:ff
14.56,-67,780,18,8,48,-89,22,aa:bb:cc:dd:ee:ff
```

### JSON Export
```json
{
  "test_name": "office_test",
  "timestamp": "2026-02-05 14:30:00",
  "roaming_events": [
    {
      "timestamp": 45.2,
      "from_bssid": "aa:bb:cc:dd:ee:ff",
      "to_bssid": "11:22:33:44:55:66"
    }
  ],
  "interference_log": [
    {
      "timestamp": 23.4,
      "issues": ["Low SNR (12dB) - High noise floor detected"]
    }
  ]
}
```

---

## 🎯 Success Metrics

### What Good Looks Like
```
✅ RSSI: > -65 dBm
✅ SNR: > 25 dB
✅ Latency: < 30 ms
✅ Tx Rate: > 400 Mbps
✅ MCS: 7-11
✅ CU: < 50%
✅ Roaming: < 100ms
✅ Health: Excellent/Good
```

### Red Flags
```
⚠️ RSSI: < -75 dBm
⚠️ SNR: < 15 dB
⚠️ Latency: > 100 ms
⚠️ Tx Rate: < 100 Mbps
⚠️ MCS: < 5
⚠️ CU: > 70%
⚠️ Frequent roaming
⚠️ Health: Bad
```

---

## 🌟 What Makes This Special

### Comprehensive
- 9 primary metrics + derived data
- Multi-band scanning
- Real-time and periodic analysis
- Multiple export formats

### Intelligent
- Automated interference detection
- Smart recommendations
- Health scoring
- Troubleshooting guides

### Professional
- Field-tested workflows
- Industry-standard metrics
- Detailed documentation
- Export for reporting

### User-Friendly
- Clear visual output
- Emoji indicators
- Step-by-step guides
- Automated analysis

---

## 📚 Documentation Structure

```
📁 Wireless Engineer's Diagnostic Suite
├── 📄 QUICK_START.md ........... 3-minute getting started
├── 📄 README.md ................ Complete documentation
├── 📄 FIELD_GUIDE.md ........... Quick reference card
├── 📄 FAQ.md ................... Common questions
├── 📄 FEATURES_COMPARISON.md ... v1.2 vs v2.0
├── 📄 PROJECT_OVERVIEW.md ...... This file
├── 🔧 setup.sh ................. Dependency installer
└── 🐍 wl_tool12.py ............. Main application
```

### Reading Order
1. **First time?** → QUICK_START.md
2. **Going to field?** → FIELD_GUIDE.md
3. **Need details?** → README.md
4. **Have questions?** → FAQ.md
5. **Upgrading?** → FEATURES_COMPARISON.md

---

## 🎉 Bottom Line

**This is not just a diagnostic tool - it's a complete wireless engineering suite.**

### You Get:
- ✅ Professional-grade diagnostics
- ✅ Automated analysis
- ✅ Intelligent recommendations
- ✅ Multiple export formats
- ✅ Comprehensive documentation
- ✅ Field-tested workflows

### You Can:
- 🎯 Conduct site surveys
- 🔍 Troubleshoot issues
- 📊 Establish baselines
- 🔧 Optimize networks
- 📈 Track performance
- 📝 Generate reports

### You'll Save:
- ⏱️ Time (automated analysis)
- 💰 Money (free tool)
- 🧠 Effort (guided workflows)
- 📊 Data (comprehensive exports)

---

## 🚀 Get Started Now

```bash
# 1. Install dependencies
./setup.sh

# 2. Run your first test
sudo python3 wl_tool12.py

# 3. Follow the prompts
# 4. Review the results
# 5. Take action!
```

---

## 📞 Support

- 📖 Read the documentation
- 🔍 Check the FAQ
- 📊 Review log files
- 🎓 Study the examples

---

## 🎓 Final Thoughts

This tool represents hundreds of hours of wireless engineering experience distilled into an automated diagnostic suite. It's designed to make your job easier, your troubleshooting faster, and your networks better.

**Use it. Learn from it. Improve it. Share it.**

---

**Built for wireless professionals, by wireless professionals. 📡✨**

*Version 2.0 - February 5, 2026*
*Created by Anish Dutta*
