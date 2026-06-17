# ❓ Frequently Asked Questions

## Installation & Setup

### Q: What operating systems are supported?
**A:** Currently macOS only. The tool uses CoreWLAN framework and wdutil, which are macOS-specific. Linux and Windows versions would require different wireless APIs.

### Q: Do I need sudo/admin privileges?
**A:** Yes, for full functionality. The `wdutil` command requires sudo access to retrieve detailed wireless metrics like noise floor, channel utilization, and BSSID.

### Q: Can I run this without sudo?
**A:** Partially. Basic metrics will work, but advanced features (noise floor, SNR, channel utilization) will show "Unknown" or fail.

### Q: Installation fails with "command not found: pip3"
**A:** Install pip3 first:
```bash
python3 -m ensurepip --upgrade
```

### Q: PyObjC installation takes forever
**A:** PyObjC is a large package. On Apple Silicon Macs, it may take 5-10 minutes. Be patient or use:
```bash
pip3 install --no-cache-dir pyobjc
```

## Usage

### Q: How long should I run a test?
**A:** Depends on your goal:
- **Quick check:** 1-2 minutes (30-60 iterations)
- **Site survey:** 5-10 minutes per location
- **Troubleshooting:** 10-30 minutes to capture patterns
- **Baseline:** 1+ hour for comprehensive data

### Q: What's a good sample interval?
**A:** 
- **Fast (1-2s):** Roaming analysis, rapid changes
- **Normal (2-5s):** General diagnostics (recommended)
- **Slow (5-10s):** Long-term monitoring, battery conservation

### Q: How do I stop the test?
**A:** Type `q` and press Enter. The tool will finish the current iteration and save all data.

### Q: Can I pause and resume?
**A:** No, but you can stop and start a new test. Each test creates a separate folder with timestamped data.

### Q: Why does speedtest sometimes fail?
**A:** Speedtest servers may rate-limit or block requests. The tool retries 3 times and continues if it fails. This is normal and doesn't affect other metrics.

## Metrics & Interpretation

### Q: What's the difference between RSSI and SNR?
**A:** 
- **RSSI** = Signal strength from the AP (absolute value)
- **SNR** = Signal-to-Noise Ratio (RSSI minus noise floor)
- **SNR is more important** for determining actual connection quality

### Q: My RSSI is -60 dBm but performance is poor. Why?
**A:** Check SNR and channel utilization. Good RSSI with poor performance usually indicates:
- High noise floor (low SNR)
- Channel congestion (high CU)
- Interference
- AP overload

### Q: What's a good SNR value?
**A:**
- **> 40 dB:** Excellent
- **25-40 dB:** Good
- **15-25 dB:** Fair (may have issues)
- **< 15 dB:** Poor (expect problems)

### Q: MCS index keeps changing. Is that bad?
**A:** Some variation is normal as the AP adapts to conditions. Frequent drops to low MCS (< 5) indicate problems:
- Weak signal
- Interference
- Congestion
- Distance from AP

### Q: What does "Estimated Distance" mean?
**A:** It's calculated from RSSI using a path loss model. It's an estimate assuming:
- Indoor environment
- Standard obstacles
- Typical AP transmit power

Actual distance may vary based on environment.

### Q: Channel Utilization shows "Unknown"
**A:** This happens when:
- Not running with sudo
- WiFi driver doesn't support CCA reporting
- Older macOS version

Run with `sudo python3 wl_tool12.py` to fix.

## Troubleshooting

### Q: "Error: SSID Not Found"
**A:** 
1. Ensure you're connected to WiFi
2. Check System Preferences → Network
3. Try disconnecting and reconnecting
4. Restart WiFi: `networksetup -setairportpower en0 off && networksetup -setairportpower en0 on`

### Q: All metrics show "Unknown" or "None"
**A:** 
1. Run with sudo: `sudo python3 wl_tool12.py`
2. Ensure WiFi is connected
3. Check if wdutil works: `sudo wdutil info`
4. Update macOS if on older version

### Q: Speedtest always fails with HTTP 403
**A:** Speedtest.net is blocking your requests. This can happen with:
- VPN connections
- Corporate networks
- Frequent testing

The tool will continue without speedtest data.

### Q: Plot window doesn't update
**A:** 
1. Check if matplotlib backend is working
2. Try running in a different terminal
3. Ensure X11/display is available
4. Check for matplotlib errors in output

### Q: "Permission denied" errors
**A:** Run with sudo:
```bash
sudo python3 wl_tool12.py
```

### Q: Tool crashes with "Segmentation fault"
**A:** Usually a PyObjC issue. Try:
```bash
pip3 uninstall pyobjc
pip3 install --no-cache-dir pyobjc
```

## Features

### Q: How does roaming detection work?
**A:** The tool monitors BSSID (AP MAC address) changes. When it changes, a roaming event is logged with timestamp and source/destination BSSIDs.

### Q: What interference does it detect?
**A:** The tool detects interference indicators:
- Low SNR (high noise floor)
- High channel utilization
- Good signal but poor throughput
- Unstable MCS index

It doesn't identify specific interference sources (that requires spectrum analyzer).

### Q: Can it recommend the best channel?
**A:** Yes! Every 10 iterations, it scans nearby networks and recommends:
- Least congested band (2.4/5/6 GHz)
- Least crowded channel within current band

### Q: How accurate is the troubleshooting guide?
**A:** The automated troubleshooting provides common solutions based on metrics. It's a starting point, not a definitive diagnosis. Use your expertise to validate.

### Q: Can I export data to Excel?
**A:** Yes! The CSV export can be opened directly in Excel, Google Sheets, or Numbers. It includes all time-series data.

### Q: What's in the JSON export?
**A:** Structured data including:
- Test metadata
- Roaming events (timestamp, source, destination)
- Interference incidents (timestamp, issues)
- Summary statistics

## Data & Reports

### Q: Where are results saved?
**A:** In a folder named `RUN_<testname>` in the same directory as the script. Each test creates a new folder.

### Q: Can I compare multiple tests?
**A:** Yes! Each test has its own folder. Compare CSV files or use the JSON exports for programmatic comparison.

### Q: How do I create a heat map?
**A:** The tool doesn't create heat maps directly. Export CSV data and use:
- Ekahau HeatMapper (free)
- NetSpot
- Custom Python script with matplotlib

### Q: PDF report is empty or incomplete
**A:** The PDF report requires data in the log file. Ensure:
1. Test ran for at least a few iterations
2. Log file was created
3. Metrics were collected (not all "Unknown")

### Q: Can I customize the PDF report?
**A:** Yes! Edit the `generate_pdf_report()` function in the code. It uses ReportLab library.

## Advanced

### Q: Can I change the speedtest frequency?
**A:** Yes! Edit line ~700 in the code:
```python
if iteration % 10 == 0:  # Change 10 to desired frequency
    ping, dl, ul = get_speedtest()
```

### Q: How do I add custom metrics?
**A:** 
1. Add a function to collect the metric (like `get_noise_floor()`)
2. Call it in the main loop
3. Add to CSV export
4. Update plot if needed

### Q: Can I integrate this with monitoring tools?
**A:** Yes! Use the JSON export. It's structured for easy parsing. Example:
```python
import json
with open('diagnostics_test.json') as f:
    data = json.load(f)
    roaming_count = data['summary']['total_roaming_events']
```

### Q: Can I run multiple tests simultaneously?
**A:** Not recommended. Each test needs exclusive access to WiFi metrics. Run tests sequentially.

### Q: How do I automate testing?
**A:** Create a wrapper script:
```bash
#!/bin/bash
for location in office1 office2 office3; do
    echo -e "$location\n2" | sudo python3 wl_tool12.py
    sleep 300  # 5 minute test
    echo "q" | sudo python3 wl_tool12.py
done
```

### Q: Can I log to a remote server?
**A:** Yes! Modify `log_to_file()` to also send data via HTTP, syslog, or database. The CSV/JSON exports make this easy.

## Performance

### Q: Tool uses a lot of CPU
**A:** Normal during plotting. To reduce:
1. Increase sample interval
2. Reduce plot update frequency
3. Disable live plotting (modify code)

### Q: Speedtest slows everything down
**A:** Speedtest runs every 10 iterations by default. To reduce:
- Increase frequency (every 20 iterations)
- Disable speedtest (comment out the code)
- Use faster speedtest servers

### Q: Can I run this on battery?
**A:** Yes, but it will drain battery faster due to:
- Continuous WiFi scanning
- Speedtest bandwidth usage
- Plot rendering
- Disk writes

Use longer sample intervals (5-10s) to conserve battery.

## Compatibility

### Q: What macOS versions are supported?
**A:** Tested on macOS 10.15+ (Catalina and newer). Older versions may work but aren't guaranteed.

### Q: Does it work on Apple Silicon (M1/M2/M3)?
**A:** Yes! Fully compatible with Apple Silicon Macs.

### Q: Does it support WiFi 6E (6 GHz)?
**A:** Yes! If your Mac and network support 6 GHz, it will detect and analyze 6 GHz networks.

### Q: Can I use this with USB WiFi adapters?
**A:** Maybe. It depends if the adapter supports CoreWLAN and wdutil. Built-in WiFi is recommended.

### Q: Does it work with VPN?
**A:** Yes, but speedtest may fail. All other metrics work normally.

## Best Practices

### Q: How often should I run diagnostics?
**A:** 
- **Baseline:** Once per location/configuration
- **Troubleshooting:** As needed
- **Monitoring:** Weekly or monthly
- **After changes:** Always

### Q: Should I test all bands?
**A:** Yes! Test 2.4 GHz, 5 GHz, and 6 GHz (if available) at each location to determine the best band.

### Q: How many samples do I need?
**A:** 
- **Minimum:** 50 iterations (2-5 minutes)
- **Recommended:** 150+ iterations (5-10 minutes)
- **Comprehensive:** 500+ iterations (15-30 minutes)

### Q: What should I include in test names?
**A:** Use descriptive names:
- `office_floor2_desk5_5ghz`
- `warehouse_section_a_2.4ghz`
- `conference_room_b_baseline`

### Q: How do I document a site survey?
**A:** 
1. Run test at each location
2. Use consistent naming
3. Take photos of each location
4. Note physical environment
5. Export all CSV/JSON files
6. Generate PDF reports
7. Create summary document

## Support

### Q: Where can I get help?
**A:** 
1. Check this FAQ
2. Review README.md
3. Read FIELD_GUIDE.md
4. Check the code comments
5. Review log files for errors

### Q: How do I report a bug?
**A:** Include:
- macOS version
- Python version
- Full error message
- Steps to reproduce
- Log files

### Q: Can I contribute improvements?
**A:** Yes! The tool is designed to be extensible. Common additions:
- New metrics
- Additional plots
- Export formats
- Analysis algorithms

### Q: Is there a GUI version?
**A:** Not currently. The command-line interface is preferred for field work and automation.

## Tips & Tricks

### Q: How do I test roaming?
**A:** 
1. Start test near AP1
2. Walk slowly toward AP2
3. Monitor for roaming events
4. Note RSSI at roaming point
5. Check roaming time in logs

### Q: How do I find interference sources?
**A:** 
1. Monitor SNR continuously
2. Note when SNR drops
3. Look for patterns (time of day, location)
4. Check for nearby devices (microwaves, Bluetooth, etc.)
5. Use spectrum analyzer for definitive identification

### Q: How do I validate AP placement?
**A:** 
1. Test at multiple locations
2. Create coverage map from RSSI data
3. Check for dead zones (RSSI < -75 dBm)
4. Verify roaming behavior
5. Ensure SNR > 20 dB everywhere

### Q: How do I test capacity?
**A:** 
1. Run baseline test (no load)
2. Add clients gradually
3. Monitor channel utilization
4. Check throughput degradation
5. Note when performance drops

---

**Still have questions? Check the code - it's well-commented! 📡✨**
