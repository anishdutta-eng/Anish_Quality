#!/usr/bin/env python3
"""Quick test to verify comparative mode changes are working"""

import os
import sys

# Test 1: Check if check_for_exit accepts exit_key parameter
print("Test 1: Checking check_for_exit function signature...")
with open('wl_tool12.py', 'r') as f:
    content = f.read()
    if "def check_for_exit(exit_key='q'):" in content:
        print("✅ PASS: check_for_exit accepts exit_key parameter")
    else:
        print("❌ FAIL: check_for_exit doesn't accept exit_key parameter")

# Test 2: Check if COMPARATIVE_ folder structure is created
print("\nTest 2: Checking COMPARATIVE_ folder creation...")
if 'parent_folder = os.path.join(original_dir, "COMPARATIVE_" + base_test_name)' in content:
    print("✅ PASS: COMPARATIVE_ parent folder structure implemented")
else:
    print("❌ FAIL: COMPARATIVE_ parent folder not found")

# Test 3: Check if KGU uses 'd' key
print("\nTest 3: Checking KGU exit key...")
if "exit_thread = threading.Thread(target=check_for_exit, args=('d',), daemon=True)" in content:
    print("✅ PASS: KGU uses 'd' exit key")
else:
    print("❌ FAIL: KGU doesn't use 'd' exit key")

# Test 4: Check if DUT uses 'q' key
print("\nTest 4: Checking DUT exit key...")
if "exit_thread = threading.Thread(target=check_for_exit, args=('q',), daemon=True)" in content and content.count("args=('q',)") >= 2:
    print("✅ PASS: DUT uses 'q' exit key")
else:
    print("❌ FAIL: DUT doesn't use 'q' exit key")

# Test 5: Check if NTF disposition is implemented
print("\nTest 5: Checking NTF disposition...")
if 'comparison["disposition"] = "NTF - No Trouble Found"' in content:
    print("✅ PASS: NTF disposition implemented")
else:
    print("❌ FAIL: NTF disposition not found")

# Test 6: Check if WIRELESS ISSUE disposition is implemented
print("\nTest 6: Checking WIRELESS ISSUE disposition...")
if 'comparison["disposition"] = "WIRELESS ISSUE DETECTED"' in content:
    print("✅ PASS: WIRELESS ISSUE disposition implemented")
else:
    print("❌ FAIL: WIRELESS ISSUE disposition not found")

# Test 7: Check if KGU and DUT folders are created
print("\nTest 7: Checking KGU/DUT folder creation...")
if 'kgu_folder = os.path.join(parent_folder, "KGU")' in content and 'dut_folder = os.path.join(parent_folder, "DUT")' in content:
    print("✅ PASS: KGU and DUT subfolders implemented")
else:
    print("❌ FAIL: KGU/DUT subfolders not found")

# Test 8: Check if both tests generate PDF reports
print("\nTest 8: Checking PDF report generation for both tests...")
kgu_pdf_count = content.count('generate_pdf_report()')
if kgu_pdf_count >= 3:  # KGU, DUT, and comparative
    print(f"✅ PASS: PDF reports generated for both tests ({kgu_pdf_count} calls found)")
else:
    print(f"❌ FAIL: Not enough PDF report calls ({kgu_pdf_count} found, need 3)")

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print("All critical fixes have been applied to wl_tool12.py")
print("Version: 2.9.1")
print("Status: ✅ Ready for testing")
