# 🔬 Comparative Mode Quick Reference

## Start Command
```bash
sudo python3 wl_tool12.py
```
Select **mode 2** for Comparative Testing

---

## Workflow

### 1️⃣ Phase 1: KGU Test
- ✅ Power ON KGU only
- ✅ Connect laptop to KGU
- ✅ Enter test info
- ✅ Run test (press 'q' to stop)

### 2️⃣ Transition
- ⚠️ Power OFF KGU
- ✅ Power ON DUT
- ✅ Connect laptop to DUT
- ✅ Press Enter

### 3️⃣ Phase 2: DUT Test
- ✅ Enter DUT info
- ✅ Run test (same duration as KGU)

### 4️⃣ Results
- 📊 Automatic comparison
- 📄 Generate PDF report
- ✅ PASS or ❌ FAIL decision

---

## Pass/Fail Criteria

| Metric | ✅ Pass | ⚠️ Warn | ❌ Fail |
|--------|---------|---------|---------|
| **Throughput** | ±10% | ±15% | >±15% |
| **MCS** | ±1 | ±2 | >±2 |
| **RSSI-MCS Curve** | ±1.5 | ±2.5 | >±2.5 |
| **RSSI** | ±3dB | ±5dB | >±5dB |
| **Latency** | ±20% | ±30% | >±30% |
| **Roaming** | ≤2 extra | ≤5 extra | >5 extra |

---

## Critical Rules

⚠️ **ONE ROUTER ON AT A TIME**  
⚠️ **IDENTICAL CONFIGURATION**  
⚠️ **SAME LOCATION**  
⚠️ **SAME TEST DURATION**

---

## Interpreting Results

### ✅ PASS (Score ≥75)
- All metrics within tolerance
- Approve for shipment
- Unit is acceptable

### ❌ FAIL (Score <75)
- One or more critical failures
- Do NOT ship
- Investigate root cause:
  - Antenna issues
  - RF calibration
  - Hardware defect
  - Firmware mismatch

---

## Test Duration

- **Quick**: 30 seconds
- **Standard**: 2-5 minutes ⭐ Recommended
- **Thorough**: 10+ minutes

---

## Output Files

### KGU Test
- `RUN_KGU_<testname>/`
  - CSV, JSON, PNG, PDF

### DUT Test
- `RUN_DUT_<testname>/`
  - CSV, JSON, PNG, PDF

### Comparison
- `comparative_report_<timestamp>.pdf`

---

## Common Issues

### "Cannot continue without network connectivity"
→ Check router is on and broadcasting

### Results show FAIL but unit seems fine
→ Verify KGU is actually good
→ Check identical configuration
→ Ensure same test environment

### Different channels
→ Will cause FAIL! Use same channel

---

## Example Session

```
Select test mode: 2

Phase 1: KGU Test
Test name: Batch_A_001
AP Model: Eero Pro 6
SSID: TestNetwork
Sample interval: 2.0
[... test runs ...]

Phase 2: DUT Test
[Power OFF KGU, Power ON DUT]
DUT AP Model: Eero Pro 6
DUT SSID: TestNetwork
[... test runs ...]

Phase 3: Comparison
Overall Result: PASS (92/100)
✅ Peak Throughput: -2.5%
✅ Peak MCS: -1
✅ RSSI-MCS Correlation: 1.2
✅ Avg RSSI: -1.5dB
✅ Avg Latency: +13.6%
✅ Roaming: +1

DISPOSITION: PASS
Recommendation: Approve for shipment
```

---

## Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Speedtest fails | Continue without it (tool will work) |
| High throughput deviation | Check antenna connections |
| MCS correlation mismatch | RF calibration or antenna issue |
| Excessive roaming | Firmware or interference issue |

---

**Version**: 2.9  
**For detailed guide**: See `COMPARATIVE_TESTING_GUIDE.md`
