# CSV Format Reference - Quick Guide

## Version 2.9.3 - Updated Format

---

## What Was Fixed

### 🔴 Critical Issues (FIXED)
1. **Channel field had newlines** → Breaking CSV rows
2. **Channel Util had "37 %"** → Should be "37"
3. **MCS not validated** → Now enforces 0-12 range

### ✅ All Issues Resolved
- Channel: Newlines removed
- Channel Util: Clean numbers only (no spaces or %)
- MCS: Validated to 0-12 range
- PHY Mode: Standardized (11ax/11ac/11n)
- NSS: Clean numbers (1-4)
- Latency: 2 decimal places

---

## Expected CSV Format

### Header Row
```
Iteration,Timestamp_s,SSID,Channel,BSSID,RSSI_dBm,SNR_dB,Noise_dBm,TxRate_Mbps,Latency_ms,MCS_Index,PHY_Mode,NSS,ChannelUtil_%,Distance_m,Health_Status
```

### Sample Data Rows
```
1,0.37,MyNetwork,6g69/160,AA:BB:CC:DD:EE:FF,-53,38,-91,1152,41.36,4,11ax,2,37,7.11,Good
2,7.90,MyNetwork,6g69/160,AA:BB:CC:DD:EE:FF,-56,36,-92,1152,41.99,5,11ax,2,37,9.18,Good
3,15.43,MyNetwork,44,AA:BB:CC:DD:EE:FF,-45,35,-80,866,12.50,11,11ax,2,45,2.15,Excellent
```

---

## Field Formats

| Field | Format | Example | Notes |
|-------|--------|---------|-------|
| Iteration | Integer | 1, 2, 3 | Sequential |
| Timestamp_s | Float | 0.37, 7.90 | 2 decimals |
| SSID | String | MyNetwork | No commas |
| Channel | String | 6g69/160, 44 | No newlines |
| BSSID | MAC | AA:BB:CC:DD:EE:FF | Standard format |
| RSSI_dBm | Integer | -53, -45 | Negative values |
| SNR_dB | Integer | 38, 35 | Positive values |
| Noise_dBm | Integer | -91, -80 | Negative values |
| TxRate_Mbps | Integer | 1152, 866 | Positive values |
| Latency_ms | Float | 41.36, 12.50 | 2 decimals |
| MCS_Index | Integer | 0-12 or N/A | Valid range only |
| PHY_Mode | String | 11ax, 11ac, 11n | Standardized |
| NSS | Integer | 1, 2, 3, 4 | Clean numbers |
| ChannelUtil_% | Integer | 37, 45 | No % sign |
| Distance_m | Float | 7.11, 2.15 | 2 decimals |
| Health_Status | String | Good, Excellent | Status |

---

## Key Changes from Previous Version

### Before (v2.9.2)
```csv
1,0.37,Anish_test_001,6g69/160
,Unknown,-53,38,-91,1152,41.356,4,11ax,2,37 %,7.11,Good
```
❌ Broken across multiple lines  
❌ Channel Util has space and %

### After (v2.9.3)
```csv
1,0.37,Anish_test_001,6g69/160,Unknown,-53,38,-91,1152,41.36,4,11ax,2,37,7.11,Good
```
✅ Single line per row  
✅ Channel Util clean number  
✅ All fields properly formatted

---

## Validation Rules

### MCS Index
- **Valid**: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
- **Invalid**: Any value outside 0-12 → Shows as "N/A"

### PHY Mode
- **Valid**: 11ax, 11ac, 11n, 11a, 11g, 11b
- **Format**: Standardized (no "802.11" prefix)

### NSS (Spatial Streams)
- **Valid**: 1, 2, 3, 4
- **Format**: Clean integer only

### Channel Utilization
- **Valid**: 0-100
- **Format**: Integer only (no % sign or spaces)

---

## Excel/Google Sheets Import

### Excel
1. Open Excel
2. File → Open
3. Select CSV file
4. Data imports with correct column types
5. Ready for analysis

### Google Sheets
1. File → Import
2. Upload CSV file
3. Select "Import data"
4. All columns properly formatted

---

## Common Issues (NOW FIXED)

### ❌ Issue 1: Rows Breaking Across Lines
**Cause**: Newlines in Channel field  
**Fix**: All newlines removed from fields  
**Status**: ✅ FIXED

### ❌ Issue 2: Channel Util Not Numeric
**Cause**: "37 %" format with space and %  
**Fix**: Extract number only  
**Status**: ✅ FIXED

### ❌ Issue 3: Invalid MCS Values
**Cause**: No validation on MCS range  
**Fix**: Validate 0-12, show N/A for invalid  
**Status**: ✅ FIXED

---

## Testing Your CSV

### Quick Checks
1. ✅ Open in Excel - should import cleanly
2. ✅ All rows on single lines
3. ✅ Channel Util column is numeric (no %)
4. ✅ MCS values are 0-12 or N/A
5. ✅ PHY Mode shows 11ax/11ac/11n
6. ✅ NSS shows 1, 2, 3, or 4

### Data Analysis
1. ✅ Sort by any column - works correctly
2. ✅ Create pivot tables - no errors
3. ✅ Generate charts - proper data types
4. ✅ Filter data - all columns filterable

---

## Summary

**Version**: 2.9.3 (UPDATED)  
**Status**: All CSV issues fixed  
**Format**: Excel/Google Sheets compatible  
**Validation**: MCS 0-12, clean formatting  

Your CSV exports are now production-ready! 🎉
