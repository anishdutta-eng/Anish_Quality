# 🔬 Comparative Testing Mode Guide (KGU vs DUT)

## Overview

Version 2.9 introduces **Comparative Testing Mode** - a production-grade feature for comparing a Known Good Unit (KGU) against a Device Under Test (DUT). This mode enables objective, scientific pass/fail decisions for quality assurance and NTF (No Trouble Found) detection.

---

## What is Comparative Testing?

Comparative testing runs two identical tests back-to-back:
1. **Phase 1: KGU Test** - Establish baseline performance from a known-good reference unit
2. **Phase 2: DUT Test** - Test the suspect unit under identical conditions
3. **Phase 3: Comparison** - Automated analysis with scientific pass/fail criteria

---

## Key Features

### ✅ Scientific Pass/Fail Criteria
Based on industry standards and research:
- **Throughput**: ±10% acceptable, ±15% warning, >15% fail
- **RSSI**: ±3dB acceptable, ±5dB warning, >5dB fail  
- **MCS Index**: ±1 acceptable, ±2 warning, >2 fail
- **Latency**: ±20% acceptable, ±30% warning, >30% fail
- **RSSI-to-MCS Correlation**: Degradation curves must match within ±1.5 MCS

### 📊 Comprehensive Metrics Compared
- Peak throughput (Tx Rate)
- Peak MCS vs RSSI
- RSSI ramp down to MCS ramp down (correlation analysis)
- Average RSSI, SNR, latency
- Roaming events and connection stability
- Overall performance score (0-100)

### 📄 Professional Reports
- Side-by-side comparison tables
- Pass/fail status for each metric
- Critical failures, warnings, and passed criteria
- Test disposition with recommendations
- Actionable root cause analysis

---

## How to Use Comparative Testing Mode

### Prerequisites
- **Two routers**: One KGU (known good), one DUT (device under test)
- **Same configuration**: Both routers should have identical settings
- **Same test environment**: Run tests in same location
- **IMPORTANT**: Only ONE router powered on at a time!

### Step-by-Step Workflow

#### 1. Start the Tool
```bash
sudo python3 wl_tool12.py
```

#### 2. Select Comparative Mode
```
Select test mode (1 or 2): 2
```

#### 3. Phase 1: Test KGU
- Ensure KGU is the ONLY router powered on
- Connect your laptop to KGU
- Enter test information:
  - Test name (e.g., `ProductionTest_001`)
  - AP Model (e.g., `Eero Pro 6`)
  - SSID
  - Sample interval (e.g., `2.0` seconds)
- Let the test run (press 'q' + Enter to stop)
- Tool stores KGU baseline data

#### 4. Transition to DUT
- **POWER OFF the KGU router** ⚠️
- **POWER ON the DUT router**
- Connect your laptop to DUT
- Press Enter when ready

#### 5. Phase 2: Test DUT
- Enter DUT information:
  - AP Model
  - SSID
- Test runs with same parameters as KGU
- Tool stores DUT test data

#### 6. Phase 3: Automated Comparison
- Tool automatically compares KGU vs DUT
- Displays results in terminal:
  - Overall PASS/FAIL status
  - Score (0-100)
  - Metric-by-metric comparison
  - Failures, warnings, passed criteria
- Generate PDF report (optional)

---

## Test Criteria Explained

### Criterion 1: Peak Throughput
**What it tests**: Maximum data rate achieved during test

**Thresholds**:
- ✅ **PASS**: DUT within ±10% of KGU
- ⚠️ **WARN**: DUT within ±15% of KGU
- ❌ **FAIL**: DUT >±15% deviation

**Example**:
- KGU Peak: 866 Mbps
- DUT Peak: 820 Mbps
- Delta: -5.3% → **PASS**

**Why it matters**: Throughput directly impacts user experience. Large deviations indicate hardware or RF issues.

---

### Criterion 2: Peak MCS vs RSSI
**What it tests**: Maximum modulation/coding scheme achieved

**Thresholds**:
- ✅ **PASS**: DUT within ±1 MCS index
- ⚠️ **WARN**: DUT within ±2 MCS index
- ❌ **FAIL**: DUT >±2 MCS deviation

**Example**:
- KGU Peak MCS: 11
- DUT Peak MCS: 10
- Delta: -1 → **PASS**

**Why it matters**: MCS indicates RF quality. Lower MCS suggests signal degradation or interference.

---

### Criterion 3: RSSI-to-MCS Correlation
**What it tests**: How MCS degrades as RSSI decreases (rate vs range curve)

**Thresholds**:
- ✅ **PASS**: Curves match within ±1.5 MCS
- ⚠️ **WARN**: Curves match within ±2.5 MCS
- ❌ **FAIL**: Curves deviate >±2.5 MCS

**Example**:
```
RSSI Bucket  | KGU MCS | DUT MCS | Diff
-------------|---------|---------|------
-45 dBm      | 11.0    | 10.8    | -0.2  ✅
-55 dBm      | 9.5     | 9.2     | -0.3  ✅
-65 dBm      | 7.0     | 6.8     | -0.2  ✅
-75 dBm      | 4.5     | 4.3     | -0.2  ✅
Max Deviation: 0.3 → PASS
```

**Why it matters**: This tests the fundamental RF performance curve. Mismatched curves indicate antenna, calibration, or hardware issues.

---

### Additional Metrics

#### Average RSSI
- ✅ **PASS**: ±3dB
- ⚠️ **WARN**: ±5dB
- ❌ **FAIL**: >±5dB

#### Average Latency
- ✅ **PASS**: ±20%
- ⚠️ **WARN**: ±30%
- ❌ **FAIL**: >±30%

#### Roaming Events
- ✅ **PASS**: ≤2 extra events
- ⚠️ **WARN**: ≤5 extra events
- ❌ **FAIL**: >5 extra events

---

## Scoring System

### Overall Score Calculation
- Start with 100 points
- Deduct points for failures and warnings:
  - **Critical failure** (throughput, MCS, correlation): -25 points
  - **Major failure** (RSSI, latency): -15 points
  - **Minor failure** (roaming): -15 points
  - **Warning**: -5 to -10 points

### Pass/Fail Decision
- **PASS**: Score ≥ 75 AND no critical failures
- **FAIL**: Score < 75 OR any critical failure

---

## Interpreting Results

### ✅ PASS - Unit Acceptable
```
Overall Result: PASS (Score: 95/100)

✅ Peak Throughput within ±10% (+2.3%)
✅ Peak MCS within ±1 index (-1)
✅ RSSI-MCS correlation matches (max diff: 0.8)
✅ Average RSSI within ±3dB (+1.2dB)
✅ Average Latency within ±20% (+5.1%)
✅ Roaming events comparable (+1)

DISPOSITION: PASS - Unit Acceptable
Recommendation: Approve for shipment
```

**Action**: Ship the unit. Performance is within acceptable tolerances.

---

### ❌ FAIL - Unit Rejected
```
Overall Result: FAIL (Score: 45/100)

❌ Peak Throughput deviation -22.5% (>±15% threshold)
❌ RSSI-MCS correlation mismatch 3.2 (>2.5 threshold)
⚠️ Average RSSI deviation -4.2dB (±3dB expected)
✅ Average Latency within ±20% (+8.3%)
❌ Excessive roaming events: +7 (>5 threshold)

DISPOSITION: FAIL - Unit Rejected
Recommendation: Do not ship. Investigate root cause.

Possible Issues:
• Antenna connection problems
• RF calibration needed
• Hardware defect
• Firmware mismatch
```

**Action**: Do NOT ship. Investigate and fix issues before retesting.

---

## Best Practices

### 1. KGU Selection
- Use a unit with **verified good performance**
- Test KGU periodically to ensure it hasn't degraded
- Keep KGU in controlled environment
- Document KGU serial number and test date

### 2. Test Environment
- **Same location** for both tests
- **Same distance** from router (don't move laptop)
- **Same time of day** (avoid interference changes)
- **Minimize interference** (turn off other WiFi devices)
- **Stable power** (use same power outlet)

### 3. Test Duration
- **Minimum**: 30 seconds (quick check)
- **Recommended**: 2-5 minutes (standard test)
- **Thorough**: 10+ minutes (stress test)
- Use same duration for both KGU and DUT

### 4. Router Configuration
- **Identical settings** on both routers:
  - Same channel
  - Same channel width (20/40/80/160 MHz)
  - Same transmit power
  - Same security settings
  - Same firmware version (if possible)

### 5. Troubleshooting Failures

#### High Throughput Deviation
- Check antenna connections
- Verify channel settings match
- Test with wired connection to isolate WiFi issue

#### MCS Correlation Mismatch
- Antenna orientation/placement issue
- RF calibration needed
- Hardware defect in RF chain

#### Excessive Roaming
- Mesh configuration mismatch
- Firmware bug
- Interference causing instability

---

## Example Test Session

```bash
$ sudo python3 wl_tool12.py

╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║          WIRELESS ENGINEER'S DIAGNOSTIC SUITE v2.9                           ║
║                                                                              ║
║                    Professional WiFi Analysis Tool                           ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Test Mode Selection
1. Standard Diagnostic Test
2. Comparative Test (KGU vs DUT)

Select test mode (1 or 2): 2

🔬 COMPARATIVE TESTING MODE
ℹ This mode compares a Known Good Unit (KGU) against a Device Under Test (DUT)
ℹ You will run two tests back-to-back with a pause between them

⚠ IMPORTANT: Only ONE router should be powered on at a time!
⚠   1. Test KGU first, then power it OFF
⚠   2. Power ON DUT, then test it

Press Enter to continue...

📊 PHASE 1: Known Good Unit (KGU) Test
ℹ Connect to your Known Good Unit (KGU) and ensure it's the ONLY router powered on
Press Enter when ready to start KGU test...

Test name (e.g., ProductionTest_001): Batch_A_001
AP Model (e.g., Eero Pro 6, UniFi AP AC Pro): Eero Pro 6
SSID you're connected to: TestNetwork_KGU
✓ Results will be saved in: /path/to/RUN_KGU_Batch_A_001
Enter the sample interval in seconds: 2.0

[... KGU test runs ...]

✓ KGU test complete!

📊 PHASE 2: Device Under Test (DUT)
⚠ Now POWER OFF the KGU router
ℹ Then POWER ON the DUT router
ℹ Connect your laptop to the DUT

Press Enter when connected to DUT and ready to start test...

DUT AP Model: Eero Pro 6
DUT SSID: TestNetwork_DUT

[... DUT test runs ...]

✓ DUT test complete!

📊 PHASE 3: Comparative Analysis
ℹ Comparing KGU vs DUT...

🎯 COMPARATIVE TEST RESULTS

Overall Result: PASS
Overall Score: 92/100

Test Criteria Results:

✅ Peak Throughput: PASS
   KGU: 866.5 Mbps | DUT: 845.2 Mbps | Delta: -2.5%
   Threshold: ±10% acceptable, ±15% warning

✅ Peak Mcs: PASS
   KGU: 11 | DUT: 10 | Delta: -1
   Threshold: ±1 index acceptable, ±2 warning

✅ Rssi Mcs Correlation: PASS
   Max Deviation: 1.2 MCS
   Threshold: ±1.5 MCS acceptable, ±2.5 warning

✅ Avg Rssi: PASS
   KGU: -45.3 dBm | DUT: -46.8 dBm | Delta: -1.5dB
   Threshold: ±3dB acceptable, ±5dB warning

✅ Avg Latency: PASS
   KGU: 12.5 ms | DUT: 14.2 ms | Delta: +13.6%
   Threshold: ±20% acceptable, ±30% warning

✅ Roaming Events: PASS
   KGU: 2 | DUT: 3 | Delta: +1
   Threshold: ≤2 extra events acceptable, ≤5 warning

Passed Criteria:
  ✅ Peak Throughput within ±10% (-2.5%)
  ✅ Peak MCS within ±1 index (-1)
  ✅ RSSI-MCS correlation matches (max diff: 1.2)
  ✅ Average RSSI within ±3dB (-1.5dB)
  ✅ Average Latency within ±20% (+13.6%)
  ✅ Roaming events comparable (+1)

Generate comparative PDF report? (y/n): y
✓ Comparative report generated: comparative_report_20260210_143022.pdf

🏁 TEST DISPOSITION
✅ PASS - Device Under Test is acceptable
ℹ The DUT performs within acceptable tolerances compared to KGU
ℹ Recommendation: Approve for shipment

✅ Diagnostics Complete!
✓ KGU results: /path/to/RUN_KGU_Batch_A_001
✓ DUT results: /path/to/RUN_DUT_Batch_A_001
ℹ Returned to: /path/to/working/directory
```

---

## Tolerance Justification

The tolerances used in this tool are based on:

### Industry Standards
- **TR-398** (Broadband Forum): WiFi performance testing standard
- **IEEE 802.11**: WiFi specifications and expected performance
- **Production testing best practices**: Golden unit comparison methodologies

### Research Sources
- Wireless RF production testing guides (Doodle Labs, Cisco)
- WiFi performance metrics standards (NetBeez, WLAN Professionals)
- RF calibration and testing procedures (SemiEngineering, EE Times)

### Practical Considerations
- **±10% throughput**: Accounts for environmental variation, measurement uncertainty
- **±3dB RSSI**: Standard RF measurement tolerance
- **±1 MCS**: Allows for minor RF variations while catching significant issues
- **±20% latency**: Network latency naturally varies, but large deviations indicate problems

---

## Limitations

1. **Environmental sensitivity**: Results depend on test environment consistency
2. **Single test snapshot**: One test may not catch intermittent issues
3. **Configuration dependency**: Assumes both routers configured identically
4. **Distance estimation**: RSSI-based distance is approximate (±2-3m accuracy)
5. **No automated speedtest comparison**: Peak download/upload speeds not automatically captured (requires manual speedtest during test)

---

## Future Enhancements

Potential improvements for future versions:
- Automated speedtest integration for download/upload comparison
- Multiple KGU baseline averaging
- Statistical confidence intervals
- Automated test repetition (3x tests, average results)
- Database integration for historical tracking
- Barcode/QR scanning for unit IDs
- Multi-unit parallel testing

---

## Troubleshooting

### "Cannot continue without network connectivity"
- Ensure router is powered on and broadcasting
- Check laptop WiFi is enabled
- Verify correct SSID/password

### "Speedtest failed after all attempts"
- Check internet connectivity
- Try running test without speedtest (tool will continue)
- Verify firewall not blocking speedtest

### Results show FAIL but unit seems fine
- Verify KGU is actually a good unit (test it multiple times)
- Check test environment consistency
- Ensure both routers have identical configuration
- Consider if tolerances are too strict for your use case

### KGU and DUT on different channels
- This will cause failures! Ensure same channel configuration
- Channel affects performance significantly

---

## Support

For questions or issues:
1. Check this guide first
2. Review test logs in RUN_* folders
3. Examine PDF reports for detailed analysis
4. Verify test environment and configuration

---

**Version**: 2.9  
**Last Updated**: February 10, 2026  
**Author**: Anish Dutta
