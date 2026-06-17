# Testing CSV Fix - User Guide

## Version 2.9.3 - CSV Export Fix

---

## What Was Fixed

Your CSV export had three critical issues that are now resolved:

### 1. Channel Field Newlines ✅
**Problem**: Channel values like "6g69/160\n" contained newlines, breaking CSV rows  
**Fix**: All newlines and carriage returns removed from fields  
**Impact**: CSV rows no longer break across multiple lines

### 2. Channel Utilization Format ✅
**Problem**: Values like "37 %" had spaces and percent signs  
**Fix**: Extract clean numbers only  
**Impact**: Channel Util column is now numeric (37, 45, 89)

### 3. MCS Validation ✅
**Problem**: No validation on MCS values (should be 0-12)  
**Fix**: Validate MCS range, show "N/A" for invalid values  
**Impact**: Only valid MCS values (0-12) in exports

---

## How to Test

### Step 1: Run a New Test
```bash
python3 wl_tool12.py
```

Choose either:
- Standard mode (option 1)
- Comparative mode (option 2)

Let it run for at least 3-5 iterations, then exit.

### Step 2: Check the CSV File

The CSV will be in one of these locations:
- Standard mode: `RUN_<testname>/diagnostics_<testname>.csv`
- Comparative mode: `COMPARATIVE_<testname>/KGU/diagnostics_KGU.csv`

### Step 3: Verify Format

Open the CSV in a text editor and check:

✅ **Each row on a single line** (no line breaks within rows)
```csv
1,0.37,MyNetwork,6g69/160,Unknown,-53,38,-91,1152,41.36,4,11ax,2,37,7.11,Good
```

✅ **Channel Util is clean number** (no spaces or %)
```
37  ← Good
```

NOT:
```
37 %  ← Bad (old format)
```

✅ **MCS values are 0-12 or N/A**
```
4, 5, 11  ← Good
```

---

## Expected CSV Format

### Header
```
Iteration,Timestamp_s,SSID,Channel,BSSID,RSSI_dBm,SNR_dB,Noise_dBm,TxRate_Mbps,Latency_ms,MCS_Index,PHY_Mode,NSS,ChannelUtil_%,Distance_m,Health_Status
```

### Sample Data
```
1,0.37,Anish_test_001,6g69/160,Unknown,-53,38,-91,1152,41.36,4,11ax,2,37,7.11,Good
2,7.90,Anish_test_001,6g69/160,Unknown,-56,36,-92,1152,41.99,5,11ax,2,37,9.18,Good
3,15.43,Anish_test_001,6g69/160,Unknown,-54,37,-91,1152,42.15,4,11ax,2,38,7.65,Good
```

---

## Excel/Google Sheets Test

### Excel
1. Open Excel
2. File → Open
3. Select the CSV file
4. Verify:
   - ✅ All rows import correctly
   - ✅ No broken rows
   - ✅ Channel Util column is numeric
   - ✅ MCS values are 0-12 or N/A
   - ✅ Can sort/filter all columns

### Google Sheets
1. Open Google Sheets
2. File → Import → Upload
3. Select the CSV file
4. Click "Import data"
5. Verify same as Excel above

---

## What to Look For

### ✅ Good Signs
- Each row on a single line
- Channel Util shows as numbers: 37, 45, 89
- MCS values are 0-12 or N/A
- PHY Mode shows: 11ax, 11ac, 11n
- NSS shows: 1, 2, 3, 4
- Latency has 2 decimals: 41.36, 42.15
- Excel/Sheets imports cleanly

### ❌ Bad Signs (Report if you see these)
- Rows breaking across multiple lines
- Channel Util has "37 %" format
- MCS values outside 0-12 range
- PHY Mode inconsistent
- Excel/Sheets import errors

---

## Field Validation

| Field | Valid Format | Example |
|-------|-------------|---------|
| MCS_Index | 0-12 or N/A | 4, 5, 11 |
| PHY_Mode | 11ax/11ac/11n | 11ax |
| NSS | 1-4 | 2 |
| ChannelUtil_% | 0-100 (no %) | 37 |
| Channel | No newlines | 6g69/160 |
| Latency_ms | 2 decimals | 41.36 |

---

## Troubleshooting

### Issue: Rows still breaking across lines
**Check**: Look at Channel field - should not have newlines  
**Expected**: `6g69/160` (single line)  
**Not**: `6g69/160\n` (with newline)

### Issue: Channel Util still has %
**Check**: Should be clean number only  
**Expected**: `37`  
**Not**: `37 %` or `37%`

### Issue: MCS values outside 0-12
**Check**: Should show N/A for invalid values  
**Expected**: `4, 5, 11, N/A`  
**Not**: `15, 20, -1`

---

## Quick Test Checklist

Run through this checklist after generating a new CSV:

- [ ] CSV file created successfully
- [ ] Open in text editor - each row on single line
- [ ] Channel Util column has clean numbers (no %)
- [ ] MCS values are 0-12 or N/A
- [ ] PHY Mode shows 11ax/11ac/11n
- [ ] NSS shows 1, 2, 3, or 4
- [ ] Open in Excel - imports cleanly
- [ ] Can sort/filter all columns
- [ ] No formatting errors

---

## Success Criteria

Your CSV export is working correctly if:

✅ All rows on single lines (no breaks)  
✅ Channel Util is numeric (37, not "37 %")  
✅ MCS values are 0-12 or N/A  
✅ Excel/Sheets imports without errors  
✅ All columns sortable and filterable  

---

## Report Results

After testing, please confirm:

1. ✅ CSV format is correct
2. ✅ Excel/Sheets import works
3. ✅ All fields properly formatted

Or report any issues you still see.

---

## Summary

**Version**: 2.9.3 (UPDATED)  
**Status**: Ready for testing  
**Files**: wl_tool12.py (updated)  
**Changes**: CSV export completely fixed  

Run a new test and verify the CSV format! 🎉
