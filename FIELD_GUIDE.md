# 🎯 Field Engineer's Quick Reference Guide

## 🚀 Quick Start Checklist

```bash
□ Connect to WiFi network to test
□ Open Terminal
□ Navigate to tool directory
□ Run: python3 wl_tool12.py
□ Enter test name (e.g., "office_floor2")
□ Set sample interval (2-5 seconds recommended)
□ Wait for sanity check to pass
□ Monitor live output
□ Press 'q' + Enter when done
```

## 📊 Reading the Output

### Signal Strength (RSSI)
```
-30 to -50 dBm  → Excellent ✅
-50 to -65 dBm  → Good ✓
-65 to -75 dBm  → Fair ⚠️
-75 to -85 dBm  → Poor ❌
Below -85 dBm   → Very Poor ❌❌
```

### Signal-to-Noise Ratio (SNR)
```
> 40 dB  → Excellent ✅
25-40 dB → Good ✓
15-25 dB → Fair ⚠️
< 15 dB  → Poor ❌
```

### Channel Utilization (CU)
```
0-30%   → Low congestion ✅
30-60%  → Moderate ✓
60-80%  → High ⚠️
> 80%   → Critical ❌
```

### MCS Index
```
11-9  → Excellent (256-QAM) ✅
8-7   → Very Good (64-QAM) ✓
6-4   → Good (16-QAM) ⚠️
3-0   → Poor (BPSK/QPSK) ❌
```

## 🔍 Common Issues & Quick Fixes

### Issue: Low RSSI but close to AP
**Possible Causes:**
- Physical obstruction (walls, metal)
- AP antenna misalignment
- Client device antenna issue
- Wrong frequency band

**Quick Checks:**
1. Move to line-of-sight
2. Check AP antenna orientation
3. Try different band (2.4/5/6 GHz)
4. Test with different device

### Issue: Good RSSI but low throughput
**Possible Causes:**
- Channel congestion
- Interference
- AP overload
- Client capability mismatch

**Quick Checks:**
1. Check channel utilization (CU)
2. Scan for interferers
3. Check number of clients on AP
4. Verify client PHY mode (ac/ax)

### Issue: High latency spikes
**Possible Causes:**
- Wireless interference
- AP CPU overload
- Backhaul congestion
- QoS misconfiguration

**Quick Checks:**
1. Monitor SNR during spikes
2. Check for roaming events
3. Test wired connection
4. Review AP logs

### Issue: Frequent roaming
**Possible Causes:**
- Overlapping coverage
- Aggressive roaming thresholds
- Weak signal at edges
- AP power imbalance

**Quick Checks:**
1. Map RSSI at roaming points
2. Check AP transmit power
3. Review roaming thresholds
4. Verify coverage overlap

## 📡 Channel Selection Guide

### 2.4 GHz Band
**Non-overlapping channels:** 1, 6, 11
```
Use channel 1  → If 6 & 11 are crowded
Use channel 6  → If 1 & 11 are crowded
Use channel 11 → If 1 & 6 are crowded
```

### 5 GHz Band
**Preferred channels (DFS-free):**
- 36, 40, 44, 48 (UNII-1)
- 149, 153, 157, 161, 165 (UNII-3)

**Use DFS channels if:**
- Non-DFS channels are congested
- No radar in area
- Client devices support DFS

### 6 GHz Band
**All channels non-overlapping**
- Preferred: 37, 53, 69, 85, 101, 117, 133, 149
- Use any available channel
- Least interference

## 🎯 Site Survey Workflow

### 1. Pre-Survey
```bash
□ Identify test locations
□ Prepare floor plan
□ Note expected coverage areas
□ List critical applications
```

### 2. During Survey
```bash
□ Run tool at each location
□ Record test name with location
□ Note physical environment
□ Test at client height
□ Check all bands (2.4/5/6)
□ Document issues
```

### 3. Post-Survey
```bash
□ Review all CSV exports
□ Compare RSSI across locations
□ Identify dead zones
□ Check roaming behavior
□ Generate PDF reports
□ Create heat map (external tool)
```

## 📈 Performance Benchmarks

### Residential
```
RSSI:     > -65 dBm
SNR:      > 25 dB
Latency:  < 30 ms
Tx Rate:  > 200 Mbps
```

### Office/Enterprise
```
RSSI:     > -67 dBm
SNR:      > 25 dB
Latency:  < 20 ms
Tx Rate:  > 400 Mbps
Roaming:  < 100 ms
```

### High-Density (Stadium/Conference)
```
RSSI:     > -70 dBm
SNR:      > 20 dB
Latency:  < 50 ms
CU:       < 70%
```

### Voice/Video (Critical)
```
RSSI:     > -65 dBm
SNR:      > 30 dB
Latency:  < 30 ms
Jitter:   < 10 ms
```

## 🔧 Troubleshooting Decision Tree

```
Low Performance?
├─ Check RSSI
│  ├─ Low? → Move closer / Check obstructions
│  └─ Good? → Check SNR
│     ├─ Low? → Find interference source
│     └─ Good? → Check CU
│        ├─ High? → Change channel
│        └─ Low? → Check AP load / backhaul
│
├─ Check Latency
│  ├─ High? → Check for interference / AP CPU
│  └─ Spikes? → Monitor roaming events
│
└─ Check Tx Rate
   ├─ Low? → Verify client capabilities
   └─ Fluctuating? → Check MCS index stability
```

## 📱 Band Selection Strategy

### Use 2.4 GHz when:
- Maximum range needed
- Penetration through walls required
- Legacy device support
- Outdoor coverage

### Use 5 GHz when:
- High throughput needed
- Less congestion required
- Indoor environment
- Modern devices only

### Use 6 GHz when:
- Maximum performance needed
- WiFi 6E devices
- Minimal interference required
- High-density environment

## 🎨 Interpreting the Plots

### Plot 1: RSSI & MCS
- **Stable lines** = Good connection
- **Drops** = Coverage issues
- **MCS follows RSSI** = Normal
- **MCS low despite good RSSI** = Interference

### Plot 2: Tx Rate & Latency
- **High Tx, Low Latency** = Excellent
- **Low Tx, High Latency** = Problem
- **Spikes in latency** = Interference/congestion

### Plot 3: RSSI vs MCS
- **Tight cluster** = Stable connection
- **Scattered** = Unstable environment
- **Low MCS at high RSSI** = Interference

### Plot 4: Network Count
- **High 2.4 GHz** = Congestion likely
- **Low 5/6 GHz** = Good opportunity
- **Use least crowded band**

### Plot 5: SNR
- **Above 20 dB** = Good
- **Below 20 dB** = Interference
- **Fluctuating** = Intermittent interference

## 💾 Data Export Tips

### CSV Export
- Import into Excel/Google Sheets
- Create custom charts
- Calculate statistics
- Compare multiple tests

### JSON Export
- Parse with scripts
- Integrate with monitoring tools
- Analyze roaming patterns
- Track interference over time

### PDF Report
- Share with clients
- Document issues
- Include in reports
- Archive for compliance

## 🚨 Red Flags

Watch for these warning signs:

```
⚠️  RSSI < -75 dBm → Coverage issue
⚠️  SNR < 15 dB → Interference
⚠️  CU > 70% → Congestion
⚠️  Latency > 100 ms → Network issue
⚠️  Frequent roaming → Coverage gaps
⚠️  MCS < 5 → Poor modulation
⚠️  Tx Rate < 100 Mbps → Throughput issue
```

## 📞 Emergency Troubleshooting

### Network Down
1. Check SSID connection
2. Verify RSSI > -85 dBm
3. Test ping to gateway
4. Check DNS resolution

### Intermittent Issues
1. Monitor for 10+ minutes
2. Look for patterns
3. Check roaming events
4. Correlate with interference

### Slow Performance
1. Run speedtest
2. Compare to baseline
3. Check channel utilization
4. Test different band

## 🎓 Pro Tips

1. **Always establish baseline** - Run test during off-hours
2. **Test at client height** - Don't test at AP height
3. **Multiple samples** - One test isn't enough
4. **Document everything** - Photos + data
5. **Compare bands** - Test 2.4/5/6 GHz at same location
6. **Check time of day** - Interference varies
7. **Use consistent naming** - location_band_time format
8. **Archive results** - Keep historical data
9. **Verify with multiple devices** - Client matters
10. **Read the logs** - Automated analysis isn't perfect

---

**Keep this guide handy in the field! 📡🔧**
