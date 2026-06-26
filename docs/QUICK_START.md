# ⚡ Quick Start Guide

## 🚀 Get Started in 3 Minutes

### Step 1: Install (One-time setup)
```bash
chmod +x setup.sh
./setup.sh
```

### Step 2: Run
```bash
sudo python3 wl_tool12.py
```

### Step 3: Follow Prompts
```
What is the test name? office_test
Enter the sample interval in seconds: 2
```

### Step 4: Monitor
Watch the live output and plots. Press `q` + Enter when done.

---

## 📊 What You'll See

### Console Output
```
Iteration: 1
SSID: MyNetwork | Channel: 36 | RSSI: -65dB | SNR: 25dB
Tx: 866Mbps | Latency: 15ms | MCS: 9

⚠️  INTERFERENCE: High channel utilization (75%)
```

### Every 10 Iterations
```
📊 COMPREHENSIVE ANALYSIS
🏥 Network Health: Good
📡 Nearby Networks: 2.4GHz: 23 | 5GHz: 8 | 6GHz: 2
💡 RECOMMENDATIONS: Consider switching to 5GHz band
🔧 TROUBLESHOOTING: [If issues detected]
```

### Live Plots (5 panels)
1. RSSI & MCS Index over time
2. Tx Rate & Latency over time
3. RSSI vs MCS correlation
4. Network count by band
5. SNR over time

---

## 📁 Output Files

After the test, find in `RUN_<testname>/`:

| File | Use For |
|------|---------|
| `*.txt` | Detailed logs |
| `*.png` | Visual analysis |
| `*.csv` | Excel/data analysis |
| `*.json` | Integration/scripting |
| `*.pdf` | Reports (optional) |

---

## 🎯 Common Commands

### Basic Test
```bash
sudo python3 wl_tool12.py
# Enter: test1, 2
```

### Quick 1-Minute Test
```bash
sudo python3 wl_tool12.py
# Enter: quick_test, 1
# Wait 60 seconds, press q + Enter
```

### Long Monitoring
```bash
sudo python3 wl_tool12.py
# Enter: monitoring, 5
# Let run for 30+ minutes
```

---

## 🔍 Quick Interpretation

### Good Connection ✅
```
RSSI: > -65 dBm
SNR: > 25 dB
Latency: < 30 ms
MCS: 7-11
Network Health: Excellent/Good
```

### Problem Connection ❌
```
RSSI: < -75 dBm
SNR: < 15 dB
Latency: > 100 ms
MCS: < 5
Network Health: Bad
```

### Check These First
1. **RSSI** - Signal strength (higher is better)
2. **SNR** - Signal quality (> 20 dB needed)
3. **Latency** - Response time (< 50 ms good)
4. **Roaming Events** - Frequent = coverage issues

---

## 💡 Pro Tips

### Tip 1: Name Tests Descriptively
```
✅ office_floor2_desk5_5ghz
❌ test1
```

### Tip 2: Test All Bands
Run separate tests for 2.4 GHz, 5 GHz, and 6 GHz at same location.

### Tip 3: Test at Client Height
Don't test at ceiling height where APs are mounted.

### Tip 4: Run Long Enough
Minimum 2-5 minutes per location for reliable data.

### Tip 5: Follow Recommendations
The tool tells you what to fix - listen to it!

---

## 🆘 Troubleshooting

### "SSID Not Found"
→ Connect to WiFi first

### "Permission denied"
→ Use `sudo python3 wl_tool12.py`

### "Unknown" metrics
→ Run with sudo

### Speedtest fails
→ Normal, tool continues anyway

### Plot doesn't show
→ Check matplotlib installation

---

## 📚 Learn More

| Document | When to Read |
|----------|--------------|
| **README.md** | Full documentation |
| **FIELD_GUIDE.md** | Before field work |
| **FAQ.md** | When stuck |
| **FEATURES_COMPARISON.md** | What's new in v2.0 |

---

## 🎓 5-Minute Tutorial

### Scenario: Office WiFi is slow

1. **Connect to the WiFi**
   ```bash
   # Join the network in System Preferences
   ```

2. **Run diagnostic**
   ```bash
   sudo python3 wl_tool12.py
   # Enter: office_slow, 2
   ```

3. **Watch for 5 minutes**
   - Note RSSI (should be > -65)
   - Check SNR (should be > 20)
   - Monitor channel utilization
   - Look for interference alerts

4. **Read the analysis** (every 10 iterations)
   - Network Health score
   - Recommendations
   - Troubleshooting steps

5. **Stop and review**
   - Press `q` + Enter
   - Open the PNG plot
   - Check CSV for patterns
   - Read PDF report

6. **Take action**
   - Follow troubleshooting steps
   - Try recommended channel/band
   - Move closer if RSSI low
   - Reduce interference if SNR low

---

## 🎯 Cheat Sheet

### Signal Strength (RSSI)
```
-30 to -50 dBm  → Excellent ✅
-50 to -65 dBm  → Good ✓
-65 to -75 dBm  → Fair ⚠️
-75 to -85 dBm  → Poor ❌
Below -85 dBm   → Very Poor ❌❌
```

### Signal Quality (SNR)
```
> 40 dB  → Excellent ✅
25-40 dB → Good ✓
15-25 dB → Fair ⚠️
< 15 dB  → Poor ❌
```

### Channel Utilization
```
0-30%   → Low ✅
30-60%  → Moderate ✓
60-80%  → High ⚠️
> 80%   → Critical ❌
```

### Latency
```
< 20 ms   → Excellent ✅
20-50 ms  → Good ✓
50-100 ms → Fair ⚠️
> 100 ms  → Poor ❌
```

---

## 🚀 Ready to Go!

You now know enough to:
- ✅ Run basic diagnostics
- ✅ Interpret results
- ✅ Follow recommendations
- ✅ Export data
- ✅ Troubleshoot issues

**Start diagnosing! 📡✨**

---

## 📞 Need Help?

1. Check **FAQ.md** for common issues
2. Review **FIELD_GUIDE.md** for detailed reference
3. Read **README.md** for complete documentation
4. Examine log files in `RUN_<testname>/` folder

**Happy diagnosing! 🎉**
