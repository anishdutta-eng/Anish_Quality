# This is the corrected main block for wl_tool12.py v2.9.1
# Replace the existing main block (from "if __name__ == '__main__':" to end of file) with this code

if __name__ == "__main__":
    # Print beautiful banner
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                              ║")
    print("║          WIRELESS ENGINEER'S DIAGNOSTIC SUITE v2.9.1                         ║")
    print("║                                                                              ║")
    print("║                    Professional WiFi Analysis Tool                           ║")
    print("║                                                                              ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}\n")
    
    # Ask for test mode
    print_header("Test Mode Selection")
    print(f"{Colors.BOLD}1.{Colors.ENDC} Standard Diagnostic Test")
    print(f"{Colors.BOLD}2.{Colors.ENDC} Comparative Test (KGU vs DUT)")
    print()
    
    mode_choice = input(f"{Colors.BOLD}{Colors.PURPLE}Select test mode (1 or 2): {Colors.ENDC}").strip()
    
    if mode_choice == "2":
        comparative_mode = True
        print_header("🔬 COMPARATIVE TESTING MODE")
        print_info("This mode compares a Known Good Unit (KGU) against a Device Under Test (DUT)")
        print_info("You will run two tests back-to-back with a pause between them")
        print()
        print_warning("IMPORTANT: Only ONE router should be powered on at a time!")
        print_warning("  1. Test KGU first (press 'd' to end), then power it OFF")
        print_warning("  2. Power ON DUT, test it (press 'q' to end)")
        print()
        
        # Get base test name for the comparative test
        base_test_name = input(f"{Colors.BOLD}{Colors.PURPLE}Test name (e.g., ProductionTest_001): {Colors.ENDC}").strip()
        
        # Create parent folder for comparative test
        parent_folder = os.path.join(original_dir, "COMPARATIVE_" + base_test_name)
        os.makedirs(parent_folder, exist_ok=True)
        print_success(f"Comparative test folder created: {parent_folder}")
        
        # ===== PHASE 1: KGU Test =====
        print_header("📊 PHASE 1: Known Good Unit (KGU) Test")
        print_info("Connect to your Known Good Unit (KGU) and ensure it's the ONLY router powered on")
        print_warning("Press 'd' + Enter to end KGU test when ready")
        input(f"{Colors.BOLD}{Colors.PURPLE}Press Enter when ready to start KGU test...{Colors.ENDC}")
        
        # Create KGU folder
        kgu_folder = os.path.join(parent_folder, "KGU")
        os.makedirs(kgu_folder, exist_ok=True)
        os.chdir(kgu_folder)
        print_success(f"KGU results will be saved in: {kgu_folder}")
        
        test_name = "KGU"
        
        # Get AP model
        ap_model = input(f"{Colors.BOLD}{Colors.PURPLE}KGU AP Model (e.g., Eero Pro 6): {Colors.ENDC}").strip()
        if not ap_model:
            ap_model = "Not specified"
        
        # Get SSID
        user_provided_ssid = input(f"{Colors.BOLD}{Colors.PURPLE}KGU SSID: {Colors.ENDC}").strip()
        
        log_file_path = os.path.join(kgu_folder, f"network_diagnostics_KGU.txt")
        plot_file_path = os.path.join(kgu_folder, f"network_diagnostics_plot_KGU.png")
        complete_diag_file = os.path.join(kgu_folder, f"complete_Wireless_diagnostics_KGU.txt")
        pdf_report_file = os.path.join(kgu_folder, f"network_report_KGU.pdf")

        try:
            sample_interval = float(input(f"{Colors.BOLD}{Colors.PURPLE}Enter the sample interval in seconds: {Colors.ENDC}").strip())
        except ValueError:
            sample_interval = 2.0
            print_warning(f"Invalid input, using default: {sample_interval}s")

        # Start exit thread for KGU (use 'd' key)
        exit_requested = False
        exit_thread = threading.Thread(target=check_for_exit, args=('d',), daemon=True)
        exit_thread.start()

        ssid = get_ssid()
        channel = get_wifi_channel()
        print_header("KGU Connection")
        print_metric("  SSID", ssid, "", Colors.PURPLE)
        print_metric("  Channel", channel, "", Colors.PURPLE)

        if not network_sanity_check():
            print_error("Cannot continue without network connectivity.")
            sys.exit(1)

        # Run KGU test
        plot_live_diagnostics(sample_interval)

        # Export KGU data
        print_header("📁 Exporting KGU Diagnostic Data")
        export_to_csv("KGU")
        export_to_json("KGU")
        
        # Generate KGU PDF report
        print_info("Generating KGU PDF report...")
        generate_pdf_report()
        print_success("KGU test complete!")
        
        # Store KGU results
        print_info("Storing KGU test results for comparison...")
        kgu_data = store_test_results("KGU")
        
        # ===== PHASE 2: DUT Test =====
        print_header("📊 PHASE 2: Device Under Test (DUT)")
        print_warning("Now POWER OFF the KGU router")
        print_info("Then POWER ON the DUT router")
        print_info("Connect your laptop to the DUT")
        print_warning("Press 'q' + Enter to end DUT test when ready")
        input(f"\n{Colors.BOLD}{Colors.PURPLE}Press Enter when connected to DUT and ready to start test...{Colors.ENDC}")
        
        # Reset globals for DUT test
        csv_data = []
        roaming_events = []
        interference_log = []
        bssid_history = []
        iteration_summaries = []
        mobility_history = []
        sanity_check_passed = False
        exit_requested = False
        
        # Create DUT folder
        dut_folder = os.path.join(parent_folder, "DUT")
        os.makedirs(dut_folder, exist_ok=True)
        os.chdir(dut_folder)
        print_success(f"DUT results will be saved in: {dut_folder}")
        
        test_name = "DUT"
        
        # Get DUT information
        ap_model = input(f"{Colors.BOLD}{Colors.PURPLE}DUT AP Model: {Colors.ENDC}").strip()
        if not ap_model:
            ap_model = "Not specified"
        user_provided_ssid = input(f"{Colors.BOLD}{Colors.PURPLE}DUT SSID: {Colors.ENDC}").strip()
        
        log_file_path = os.path.join(dut_folder, f"network_diagnostics_DUT.txt")
        plot_file_path = os.path.join(dut_folder, f"network_diagnostics_plot_DUT.png")
        complete_diag_file = os.path.join(dut_folder, f"complete_Wireless_diagnostics_DUT.txt")
        pdf_report_file = os.path.join(dut_folder, f"network_report_DUT.pdf")
        
        # Start exit thread for DUT (use 'q' key)
        exit_thread = threading.Thread(target=check_for_exit, args=('q',), daemon=True)
        exit_thread.start()
        
        ssid = get_ssid()
        channel = get_wifi_channel()
        print_header("DUT Connection")
        print_metric("  SSID", ssid, "", Colors.PURPLE)
        print_metric("  Channel", channel, "", Colors.PURPLE)
        
        if not network_sanity_check():
            print_error("Cannot continue without network connectivity.")
            sys.exit(1)
        
        # Run DUT test (same duration as KGU)
        plot_live_diagnostics(sample_interval)
        
        # Export DUT data
        print_header("📁 Exporting DUT Diagnostic Data")
        export_to_csv("DUT")
        export_to_json("DUT")
        
        # Generate DUT PDF report
        print_info("Generating DUT PDF report...")
        generate_pdf_report()
        print_success("DUT test complete!")
        
        # Store DUT results
        print_info("Storing DUT test results for comparison...")
        dut_data = store_test_results("DUT")
        
        # ===== PHASE 3: Comparison =====
        print_header("📊 PHASE 3: Comparative Analysis")
        print_info("Comparing KGU vs DUT...")
        
        comparison = compare_kgu_dut(kgu_data, dut_data)
        
        # Display results
        print_header("🎯 COMPARATIVE TEST RESULTS")
        
        status_color = Colors.GREEN if comparison["overall_status"] == "PASS" else Colors.RED
        print(f"\n{Colors.BOLD}Overall Result:{Colors.ENDC} {status_color}{comparison['overall_status']}{Colors.ENDC}")
        print(f"{Colors.BOLD}Overall Score:{Colors.ENDC} {status_color}{comparison['overall_score']}/100{Colors.ENDC}\n")
        
        # Show metrics
        print(f"{Colors.BOLD}Test Criteria Results:{Colors.ENDC}\n")
        for metric_name, metric_data in comparison["metrics"].items():
            status = metric_data["status"]
            status_color = Colors.GREEN if status == "PASS" else Colors.ORANGE if status == "WARN" else Colors.RED
            status_symbol = "✅" if status == "PASS" else "⚠️" if status == "WARN" else "❌"
            
            print(f"{status_symbol} {Colors.BOLD}{metric_name.replace('_', ' ').title()}:{Colors.ENDC} {status_color}{status}{Colors.ENDC}")
            print(f"   KGU: {metric_data.get('kgu', 'N/A')} | DUT: {metric_data.get('dut', 'N/A')} | Delta: {metric_data.get('delta', 'N/A')}")
            print(f"   {Colors.GRAY}Threshold: {metric_data['threshold']}{Colors.ENDC}\n")
        
        # Show failures
        if comparison["failures"]:
            print(f"\n{Colors.BOLD}{Colors.RED}Critical Failures:{Colors.ENDC}")
            for failure in comparison["failures"]:
                print(f"  {Colors.RED}❌ {failure}{Colors.ENDC}")
        
        # Show warnings
        if comparison["warnings"]:
            print(f"\n{Colors.BOLD}{Colors.ORANGE}Warnings:{Colors.ENDC}")
            for warning in comparison["warnings"]:
                print(f"  {Colors.ORANGE}⚠️ {warning}{Colors.ENDC}")
        
        # Show passed
        if comparison["passed"]:
            print(f"\n{Colors.BOLD}{Colors.GREEN}Passed Criteria:{Colors.ENDC}")
            for passed in comparison["passed"]:
                print(f"  {Colors.GREEN}✅ {passed}{Colors.ENDC}")
        
        # Generate comparative report
        print()
        os.chdir(parent_folder)
        print_info("Generating comparative PDF report...")
        report_file = generate_comparative_report(kgu_data, dut_data, comparison)
        
        # Final disposition
        print_header("🏁 TEST DISPOSITION")
        disposition_color = Colors.GREEN if "NTF" in comparison["disposition"] else Colors.RED
        print(f"{Colors.BOLD}Disposition:{Colors.ENDC} {disposition_color}{comparison['disposition']}{Colors.ENDC}\n")
        print(f"{Colors.BOLD}Recommendation:{Colors.ENDC}")
        print(f"{comparison['recommendation']}\n")
        
        if "NTF" in comparison["disposition"]:
            print_success("✅ DUT is acceptable - No wireless issues detected")
        elif "WIRELESS ISSUE" in comparison["disposition"]:
            print_error("❌ DUT has wireless issues - Further investigation required")
        else:
            print_warning("⚠️ DUT is marginal - Additional testing recommended")
        
        os.chdir(original_dir)
        print_header("✅ Comparative Testing Complete!")
        print_success(f"Parent folder: {parent_folder}")
        print_success(f"  ├── KGU/ (Known Good Unit results)")
        print_success(f"  ├── DUT/ (Device Under Test results)")
        print_success(f"  └── comparative_report_*.pdf")
        print_info(f"Returned to: {original_dir}")
        
    else:
        # ===== STANDARD MODE =====
        comparative_mode = False
        
        # Get test information
        test_name = input(f"{Colors.BOLD}{Colors.PURPLE}What is the test name? {Colors.ENDC}").strip()
        
        # Get AP model
        ap_model = input(f"{Colors.BOLD}{Colors.PURPLE}AP Model (e.g., Eero Pro 6, UniFi AP AC Pro): {Colors.ENDC}").strip()
        if not ap_model:
            ap_model = "Not specified"
        
        # Get SSID (user-provided for report)
        user_provided_ssid = input(f"{Colors.BOLD}{Colors.PURPLE}SSID you're connected to: {Colors.ENDC}").strip()
        
        run_folder = os.path.join(original_dir, "RUN_" + test_name)
        os.makedirs(run_folder, exist_ok=True)
        os.chdir(run_folder)
        print_success(f"Results will be saved in: {run_folder}")

        log_file_path = os.path.join(run_folder, f"network_diagnostics_{test_name}.txt")
        plot_file_path = os.path.join(run_folder, f"network_diagnostics_plot_{test_name}.png")
        complete_diag_file = os.path.join(run_folder, f"complete_Wireless_diagnostics_{test_name}.txt")
        pdf_report_file = os.path.join(run_folder, f"network_report_{test_name}.pdf")

        try:
            sample_interval = float(input(f"{Colors.BOLD}{Colors.PURPLE}Enter the sample interval in seconds: {Colors.ENDC}").strip())
        except ValueError:
            sample_interval = 2.0
            print_warning(f"Invalid input, using default: {sample_interval}s")

        exit_thread = threading.Thread(target=check_for_exit, args=('q',), daemon=True)
        exit_thread.start()

        ssid = get_ssid()
        channel = get_wifi_channel()
        print_header("Current Connection")
        print_metric("  SSID", ssid, "", Colors.PURPLE)
        print_metric("  Channel", channel, "", Colors.PURPLE)

        if not network_sanity_check():
            print_error("Cannot continue without network connectivity.")
            sys.exit(1)

        plot_live_diagnostics(sample_interval)

        # Export data
        print_header("📁 Exporting Diagnostic Data")
        export_to_csv(test_name)
        export_to_json(test_name)

        if input(f"\n{Colors.BOLD}{Colors.PURPLE}Generate PDF report? (y/n): {Colors.ENDC}").strip().lower() == 'y':
            generate_pdf_report()
        else:
            print_info("Skipping PDF report.")

        os.chdir(original_dir)
        print_header("✅ Diagnostics Complete!")
        print_success(f"All results saved in: {run_folder}")
        print_info(f"Returned to: {original_dir}")
