#!/usr/bin/env python3
"""
BSSID Extraction Test Script
Tests all three methods for retrieving BSSID on macOS
"""

import subprocess
import sys

print("=" * 80)
print("BSSID EXTRACTION TEST - v2.4")
print("=" * 80)
print()

# Check if connected to WiFi
print("1. Checking WiFi connection status...")
try:
    result = subprocess.check_output(
        "networksetup -getairportnetwork en0 2>/dev/null || networksetup -getairportnetwork en1 2>/dev/null",
        shell=True, universal_newlines=True
    ).strip()
    
    if "not associated" in result.lower():
        print("   ✗ NOT CONNECTED to WiFi")
        print("   → Please connect to a WiFi network and run this test again")
        sys.exit(1)
    else:
        print(f"   ✓ Connected: {result}")
except Exception as e:
    print(f"   ✗ Error checking connection: {e}")
    sys.exit(1)

print()

# Method 1: wdutil with sudo
print("2. Testing Method 1: sudo wdutil info")
try:
    bssid = subprocess.check_output(
        "sudo wdutil info | grep 'BSSID' | awk '{print $3}'",
        shell=True, universal_newlines=True, timeout=5
    ).strip()
    
    if bssid and bssid != "<redacted>" and len(bssid) > 5:
        print(f"   ✓ SUCCESS: {bssid}")
        print(f"   → BSSID is NOT redacted!")
    elif bssid == "<redacted>":
        print(f"   ✗ FAILED: {bssid}")
        print(f"   → BSSID is still redacted (macOS privacy restriction)")
    else:
        print(f"   ✗ FAILED: Empty or invalid BSSID")
except Exception as e:
    print(f"   ✗ ERROR: {e}")

print()

# Method 2: airport command (if available)
print("3. Testing Method 2: airport command")
try:
    bssid = subprocess.check_output(
        "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I | awk '/ BSSID/ {print $2}'",
        shell=True, universal_newlines=True, timeout=5
    ).strip()
    
    if bssid and len(bssid) > 5:
        print(f"   ✓ SUCCESS: {bssid}")
    else:
        print(f"   ✗ FAILED: Command not available or returned empty")
except Exception as e:
    print(f"   ✗ ERROR: {e}")

print()

# Method 3: CoreWLAN Python API
print("4. Testing Method 3: CoreWLAN Python API")
try:
    import CoreWLAN
    iface = CoreWLAN.CWInterface.interface()
    
    if iface:
        bssid = iface.bssid()
        ssid = iface.ssid()
        
        if bssid:
            print(f"   ✓ SUCCESS: {bssid}")
            print(f"   → SSID: {ssid}")
        else:
            print(f"   ✗ FAILED: BSSID is None")
    else:
        print(f"   ✗ FAILED: No WiFi interface found")
except ImportError:
    print(f"   ✗ ERROR: CoreWLAN not available (install pyobjc)")
except Exception as e:
    print(f"   ✗ ERROR: {e}")

print()
print("=" * 80)
print("TEST COMPLETE")
print("=" * 80)
print()

# Summary
print("SUMMARY:")
print("--------")
print("If Method 1 shows '<redacted>':")
print("  → macOS privacy restrictions are blocking BSSID even with sudo")
print("  → This is a macOS 14.5+ limitation")
print("  → Try Methods 2 or 3 as fallbacks")
print()
print("If Method 3 (CoreWLAN) works:")
print("  → The tool will use this as fallback")
print("  → BSSID tracking will work correctly")
print()
print("If all methods fail:")
print("  → BSSID will show as 'Unknown' in the tool")
print("  → Other features will still work normally")
print()
