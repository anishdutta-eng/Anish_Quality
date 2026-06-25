# 🧪 Testing Guide - v2.4 Features

## Quick Start Testing

### Prerequisites
```bash
# Ensure you have all dependencies
pip3 install speedtest-cli matplotlib reportlab pyobjc

# Verify script loads
python3 -c "import wl_tool12; print('✓ Ready')"
```

---

## Test 1: Quick Functionality Test (5 minutes)

**Purpose:** Verify basic functionality and BSSID retrieval

```bash
# Run the tool
sudo python3 wl_tool12.py

# When prompted, enter:
Test name: quick_test
AP Model: [Your AP model, e.g., "Eero Pro 6"]
SSID: [Your network name]
Sample interval: 2

# Let it run for 30 seconds (15 iterations)
# Watch the terminal output

# Stop: Type 'q' then press Enter

# Generate PDF: y
```

**What to Check:**
1. ✅ BSSID in terminal shows MAC address (not `<redacted>`)
2. ✅ All metrics display correctly (RSSI, SNR, Tx Rate, etc.)
3. ✅ At iteration 10, comprehensive analysis appears
4. ✅ PDF file is generated in `RUN_quick_test/` folder

**Open the PDF:**
```bash
open RUN_quick_test/network_report_quick_test.pdf
```

**Verify in PDF:**
- [ ] Test Information shows your AP Model
- [ ] Test Information shows your SSID
- [ ] Sanity Check shows PASSED or FAILED
- [ ] Overall Performance Summary has real numbers (not all N/A)
- [ ] Detailed Iteration Analysis shows iteration 10 summary
- [ ] Recommendations section has content

---

## Test 2: Extended Test (30 minutes)

**Purpose:** Test all features including multiple iteration summaries

```bash
sudo python3 wl_tool12.py

# Enter:
Test name: extended_test
AP Model: [Your AP model]
SSID: [Your network]
Sample interval: 2

# Let it run for 5+ minutes (150+ iterations)
# This will give you summaries at iterations 10, 20, 30, 40, 50...

# Stop when ready: 'q' + Enter
# Generate PDF: y
```

**What to Check:**
1. ✅ Multiple comprehensive analyses (every 10 iterations)
2. ✅ Speedtest runs at iterations 10, 20, 30, etc.
3. ✅ PDF has multiple iteration summaries
4. ✅ CSV file has all 16 columns
5. ✅ JSON file has mesh analysis

**Files to Check:**
```bash
cd RUN_extended_test/
ls -la

# Should see:
# - network_report_extended_test.pdf
# - diagnostics_extended_test.csv
# - diagnostics_extended_test.json
# - network_diagnostics_extended_test.txt
# - network_diagnostics_plot_extended_test.png
```

---

## Test 3: Mesh Network Test (if available)

**Purpose:** Test roaming detection and mesh node tracking

**Requirements:** Mesh WiFi network (e.g., Eero, Google WiFi, UniFi mesh)

```bash
sudo python3 wl_tool12.py

# Enter:
Test name: mesh_test
AP Model: [Your mesh system]
SSID: [Your network]
Sample interval: 2

# While running:
# - Walk around your space
# - Move between rooms
# - Try to trigger roaming between mesh nodes

# Run for 5+ minutes
# Stop: 'q' + Enter
# Generate PDF: y
```

**What to Check:**
1. ✅ Terminal shows "ROAMING EVENT" messages when you move
2. ✅ BSSID changes are detected
3. ✅ PDF shows "Mesh network detected"
4. ✅ PDF shows number of unique nodes
5. ✅ JSON file has mesh topology analysis

**Check JSON for mesh data:**
```bash
cat RUN_mesh_test/diagnostics_mesh_test.json | grep -A 10 "mesh_analysis"
```

---

## Test 4: CSV Export Verification

**Purpose:** Verify all 16 KPIs are exported correctly

```bash
# After any test, check the CSV file
open RUN_[test_name]/diagnostics_[test_name].csv

# Or view in terminal:
head -20 RUN_[test_name]/diagnostics_[test_name].csv
```

**Verify Columns:**
1. Iteration
2. Timestamp_s
3. SSID
4. Channel
5. BSSID
6. RSSI_dBm
7. SNR_dB
8. Noise_dBm
9. TxRate_Mbps
10. Latency_ms
11. MCS_Index
12. PHY_Mode
13. NSS
14. ChannelUtil_%
15. Distance_m
16. Health_Status

**All columns should have data (not all N/A)**

---

## Test 5: PDF Report Sections

**Purpose:** Verify all 7 sections are present and populated

**Open any generated PDF and check:**

### Section 1: Test Information ✅
- [ ] Test Name
- [ ] Date/Time
- [ ] AP Model (your input)
- [ ] SSID (your input)
- [ ] Channel
- [ ] Total Iterations
- [ ] Test Duration

### Section 2: Network Sanity Check ✅
- [ ] Shows ✓ PASSED or ✗ FAILED
- [ ] Color-coded (green or red)

### Section 3: Overall Performance Summary ✅
- [ ] Table with 5 metrics
- [ ] Average, Min, Max columns
- [ ] Status column (Good/Fair)
- [ ] Real numbers (not N/A)

### Section 4: Roaming & Mesh Analysis ✅
- [ ] Total roaming events
- [ ] Unique nodes/APs
- [ ] Network type
- [ ] Analysis text

### Section 5: Interference & Issues ✅
- [ ] Count of incidents
- [ ] List of issue types
- [ ] Frequency of each

### Section 6: Detailed Iteration Analysis ✅
- [ ] Summaries at iterations 10, 20, 30...
- [ ] Each shows: RSSI, SNR, Tx, Latency, MCS, Health, CU
- [ ] Issues listed (if any)
- [ ] Recommendations listed (if any)

### Section 7: Recommendations & Conclusions ✅
- [ ] Intelligent recommendations
- [ ] Based on actual data
- [ ] Actionable advice

---

## Common Issues & Solutions

### Issue: BSSID still shows `<redacted>`
**Solution:**
- Ensure you're running with `sudo`
- Check macOS privacy settings
- Try: `sudo wdutil info | grep BSSID` manually

### Issue: PDF says "no data to report"
**Solution:**
- This should be fixed in v2.4
- If still occurs, check that `iteration_summaries` list is being populated
- Run for at least 10 iterations

### Issue: Speedtest fails
**Solution:**
- This is expected in some environments
- Tool will continue without speedtest
- Basic connectivity check will still work

### Issue: No roaming events detected
**Solution:**
- This is normal if you're not moving
- Or if you have a single AP (not mesh)
- Try walking around to trigger roaming

---

## Success Criteria

### ✅ v2.4 is working correctly if:

1. **BSSID Retrieval:**
   - Shows real MAC address (not `<redacted>`)
   - Format: `xx:xx:xx:xx:xx:xx`

2. **PDF Report:**
   - All 7 sections present
   - Test Information shows your inputs
   - Statistics have real numbers
   - Iteration summaries appear every 10 iterations
   - No "no data to report" message

3. **User Inputs:**
   - AP Model appears in PDF
   - SSID appears in PDF
   - Both used in analysis

4. **Iteration Summaries:**
   - Appear at iterations 10, 20, 30...
   - Show all metrics
   - Include issues and recommendations

5. **Mesh Detection:**
   - Roaming events detected (if moving)
   - Multiple BSSIDs tracked
   - Mesh analysis in JSON

---

## Quick Verification Commands

```bash
# Check BSSID retrieval manually
sudo wdutil info | grep BSSID

# Verify script syntax
python3 -c "import wl_tool12; print('✓ OK')"

# Check dependencies
python3 -c "import speedtest, matplotlib, reportlab; print('✓ All installed')"

# List test results
ls -la RUN_*/

# View CSV headers
head -1 RUN_*/diagnostics_*.csv

# Check PDF exists
ls -la RUN_*/network_report_*.pdf

# Open latest PDF
open $(ls -t RUN_*/network_report_*.pdf | head -1)
```

---

## Reporting Issues

If you find any issues during testing, please note:

1. **What you were testing:** (Test 1, 2, 3, etc.)
2. **What you expected:** (from "What to Check" section)
3. **What actually happened:** (error message, unexpected behavior)
4. **Terminal output:** (copy relevant lines)
5. **Files generated:** (list files in RUN_* folder)

---

## Next Steps After Testing

### If all tests pass ✅
- Tool is ready for production use
- Share with team/clients
- Use for real network diagnostics

### If issues found ⚠️
- Document the issue
- Check "Common Issues & Solutions" above
- Report findings for debugging

---

**Happy Testing! 🎉**

*Testing Guide v2.4 - February 5, 2026*
