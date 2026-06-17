# Implementation Plan: Offline Data Viewer

## Overview

Build a self-contained, browser-based interactive visualization system for WiFi diagnostic test runs. The implementation creates a new `wl_viewer.py` module with three Python components (DataBundler, MLScoringEngine, HTMLGenerator) that produce `.wldata` JSON bundles and self-contained `.html` viewer files. The viewer embeds Plotly.js and works offline in Chrome via `file://` protocol. A JavaScript ComparisonEngine is embedded in the HTML for runtime multi-run drag-and-drop comparison.

Build order: data models → data bundling → ML scoring → anomaly detection → HTML generation → comparison engine → CLI integration → final wiring.

## Tasks

- [x] 1. Set up module structure and data models
  - [x] 1.1 Create `wl_viewer.py` with imports, constants, and all dataclass models
    - Create the new `wl_viewer.py` file (separate from `wl_tool12.py`)
    - Define all dataclass models: `TimeSeriesRow`, `RoamingEvent`, `InterferenceEvent`, `RunMetadata`, `MetricStats`, `RunStatistics`, `Anomaly`, `QualityScore`, `WLDataBundle`
    - Define `BundleError` exception class
    - Add helper functions: `safe_float()`, `safe_int()`, `score_to_status()`
    - Import dependencies: `dataclasses`, `json`, `csv`, `glob`, `os`, `datetime`, `html`, `sqlite3`, `numpy`, `typing`
    - Add module docstring and version constant (`__version__ = "1.0.0"`)
    - _Requirements: 1.8, 10.1–10.8_

  - [ ]* 1.2 Write property test: safe_float and safe_int handle all input types
    - **Property 9: N/A Handling** — No `"N/A"` string values appear in any numeric field; all missing values convert to sentinel values (`-1` for latency, `0.0` for rates)
    - Use `hypothesis` with strategies for strings including `"N/A"`, `""`, numeric strings, and edge cases
    - **Validates: Requirements 1.2, 10.4, 10.5**

  - [ ]* 1.3 Write property test: score_to_status maps correctly
    - **Property 3: Score Bounds** — For any integer in [0, 100], `score_to_status()` returns one of `"Excellent"`, `"Good"`, `"Fair"`, `"Poor"`
    - **Validates: Requirements 2.5**

- [x] 2. Implement DataBundler component
  - [x] 2.1 Implement `DataBundler.parse_csv()` method
    - Parse `diagnostics_*.csv` files using the `csv` module
    - Handle the 16-column header: `Iteration,Timestamp_s,SSID,Channel,BSSID,RSSI_dBm,SNR_dB,Noise_dBm,TxRate_Mbps,Latency_ms,MCS_Index,PHY_Mode,NSS,ChannelUtil_%,Distance_m,Health_Status`
    - Convert `N/A`, empty strings, and unparseable values to sentinel values using `safe_float()`/`safe_int()`
    - Skip malformed rows (wrong column count, corrupted encoding) with logged warnings
    - Validate numeric ranges: RSSI in [-120, 0], MCS in [0, 12], SNR in [-50, 100], latency non-negative, tx_rate non-negative
    - _Requirements: 1.1, 1.2, 1.6, 1.7, 10.1–10.5_

  - [x] 2.2 Implement `DataBundler.parse_json()` method
    - Parse `diagnostics_*.json` files into `RunMetadata` dataclass
    - Extract roaming events, interference log, and summary fields
    - Handle missing or optional fields gracefully
    - _Requirements: 1.1, 1.5_

  - [x] 2.3 Implement `DataBundler.compute_statistics()` method
    - Compute per-metric summary statistics: min, max, mean, median, std, p5, p95
    - Use `numpy` for percentile and standard deviation calculations
    - Compute for all 7 metrics: RSSI, SNR, Tx Rate, Latency, MCS, Channel Utilization, Distance
    - Filter out sentinel values (`-1`) before computing latency statistics
    - _Requirements: 1.3_

  - [x] 2.4 Implement `DataBundler.bundle()` and `DataBundler.save_bundle()` methods
    - Discover CSV and JSON files inside a `RUN_*` folder by naming convention (`diagnostics_*.csv`, `diagnostics_*.json`)
    - Raise `BundleError` with descriptive message if required files are missing
    - Assemble `WLDataBundle` with version, test_name, generated_at, time_series, metadata, statistics
    - Serialize bundle to `.wldata` JSON file with `json.dumps()` using `default=str` for datetime handling
    - Normalize column names to canonical schema
    - _Requirements: 1.1, 1.4, 1.5, 1.8_

  - [ ]* 2.5 Write property test: bundle completeness
    - **Property 1: Bundle Completeness** — For any valid `RUN_*` folder, `bundle()` produces a `WLDataBundle` where `len(time_series)` equals the number of data rows in the CSV (excluding header)
    - Test with `RUN_Test0019/` (17 rows) and `RUN_beta2/` data
    - **Validates: Requirements 1.1**

  - [ ]* 2.6 Write property test: idempotent bundling
    - **Property 2: Idempotent Bundling** — `bundle(folder)` called twice on the same unchanged folder produces identical `WLDataBundle` objects (excluding `generated_at` timestamp)
    - **Validates: Requirements 1.4**

  - [ ]* 2.7 Write unit tests for DataBundler
    - Test `parse_csv()` with real `RUN_Test0019/diagnostics_Test0019.csv` — verify 17 rows parsed
    - Test `N/A` handling: verify sentinel values for missing latency and tx_rate
    - Test `compute_statistics()` against known values from test data
    - Test `BundleError` raised for missing CSV/JSON files
    - Test malformed row skipping with a synthetic CSV containing bad rows
    - _Requirements: 1.1–1.8, 10.1–10.8_

- [x] 3. Checkpoint — Verify data bundling
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement MLScoringEngine component
  - [x] 4.1 Implement rule-based quality scoring
    - Implement `MLScoringEngine.score_quality()` with rule-based fallback
    - MCS scoring: 50 points (avg_mcs >= 8 → 50, >= 5 → 35, >= 3 → 20, else 10)
    - SNR scoring: 35 points (avg_snr >= 35 → 35, >= 25 → 28, >= 20 → 20, >= 15 → 12, else 5)
    - NSS scoring: 15 points (avg_nss >= 4 → 15, >= 3 → 12, >= 2 → 8, else 4)
    - Map overall score to status: Excellent >= 85, Good 70–84, Fair 50–69, Poor < 50
    - Handle edge case: no valid rows → score 0, status "Unknown"
    - _Requirements: 2.1, 2.3, 2.5, 2.6_

  - [x] 4.2 Implement ML model loading and GradientBoosting scoring path
    - Implement `extract_run_features()` to build 14-element feature vector
    - Load model from `~/.wl_tool/models/quality_model.pkl` using `joblib`
    - If model exists and loads: use it, set `model_used = "gradient_boosting"`
    - If model file is corrupted: log warning, delete file, fall back to rule-based
    - If no model exists: use rule-based scoring, set `model_used = "rule_based"`
    - _Requirements: 2.2, 2.3, 2.4_

  - [x] 4.3 Implement anomaly detection
    - Implement `MLScoringEngine.detect_anomalies()` with IsolationForest + rule-based checks
    - Build feature matrix `[RSSI, SNR, MCS, TxRate, Latency, ChannelUtil]` for IsolationForest
    - Run IsolationForest with `contamination=0.1` when >= 10 valid rows; skip when < 10
    - Rule-based checks: RSSI drop > 15 dBm → "rssi_drop" (high), MCS drop >= 4 → "mcs_instability" (medium), Latency > 3x running avg → "latency_spike" (medium/high)
    - Implement `deduplicate_anomalies()`: keep highest severity per (iteration, anomaly_type), sort by iteration ascending
    - _Requirements: 3.1–3.7_

  - [x] 4.4 Implement `MLScoringEngine.score_bundle()` to orchestrate scoring + anomaly detection
    - Call `detect_anomalies()` and `score_quality()` on the bundle
    - Return a scored bundle with quality_score and anomalies populated
    - _Requirements: 2.1, 3.7_

  - [ ]* 4.5 Write property test: score bounds
    - **Property 3: Score Bounds** — For any bundle with randomly generated time-series data (RSSI in [-120, 0], MCS in [0, 12], SNR in [-50, 100]), `score_quality()` returns a score in [0, 100]
    - Use `hypothesis` to generate random time-series rows
    - **Validates: Requirements 2.1**

  - [ ]* 4.6 Write property test: anomaly validity
    - **Property 4: Anomaly Validity** — For any anomaly in `detect_anomalies(ts)`, `anomaly.iteration` exists in `ts` and `anomaly.severity` is in `{"low", "medium", "high"}`
    - **Validates: Requirements 3.7, 10.7**

  - [ ]* 4.7 Write property test: anomaly deduplication
    - For any list of anomalies with random duplicates, `deduplicate_anomalies()` produces a list with no `(iteration, anomaly_type)` duplicates and length ≤ input length
    - **Validates: Requirements 3.6**

  - [ ]* 4.8 Write unit tests for MLScoringEngine
    - Test rule-based scoring with known inputs from `RUN_Test0019/` data
    - Test anomaly detection with synthetic data containing known RSSI drops and latency spikes
    - Test ML fallback when no model file exists
    - Test corrupted model file handling
    - Test edge case: fewer than 10 rows skips IsolationForest
    - _Requirements: 2.1–2.6, 3.1–3.7_

- [x] 5. Implement ML History Database
  - [x] 5.1 Implement SQLite history database operations
    - Implement `MLScoringEngine.__init__()` with SQLite DB initialization at `~/.wl_tool/ml_history.db`
    - Create table schema for storing compressed feature vectors (~200 bytes per run)
    - Implement `append_to_history()`: store run's feature vector with Run_Tags (AP model, location, band, channel width)
    - Implement `retrain()`: retrain GradientBoostingRegressor and IsolationForest from all historical data
    - Save retrained models to `~/.wl_tool/models/` using `joblib`
    - _Requirements: 4.1–4.4_

  - [ ]* 5.2 Write property test: ML fallback
    - **Property 8: ML Fallback** — When no trained model exists at `~/.wl_tool/models/quality_model.pkl`, `score_quality()` returns a valid `QualityScore` with `model_used == "rule_based"`
    - Use a temporary directory to ensure no model file exists
    - **Validates: Requirements 2.3**

  - [ ]* 5.3 Write unit tests for ML History Database
    - Test database creation and schema
    - Test `append_to_history()` stores feature vectors correctly
    - Test `retrain()` produces valid model files
    - _Requirements: 4.1–4.3_

- [x] 6. Checkpoint — Verify ML pipeline
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement HTMLGenerator component
  - [x] 7.1 Create the HTML template with embedded Plotly.js
    - Create the HTML template as a string constant or separate template file in `wl_viewer.py`
    - Embed the full minified Plotly.js library inline (use `plotly` package to get the JS source)
    - Include CSS styles for minimalist, intuitive UI layout
    - Include placeholder slots for: chart configs, embedded data, comparison JS, drag-drop JS
    - Ensure valid HTML5 with zero external resource references
    - _Requirements: 5.1, 5.2, 5.3, 6.1_

  - [x] 7.2 Implement `HTMLGenerator.build_chart_configs()` for all chart types
    - Generate Plotly trace/layout dicts for 8 chart types:
      1. RSSI vs Time (line chart)
      2. MCS vs Time (line chart)
      3. Tx Rate vs Time (line chart)
      4. Latency vs Time (line chart)
      5. SNR vs Time (line chart)
      6. Channel Utilization vs Time (line chart)
      7. Distance vs RSSI (scatter plot)
      8. Combined health dashboard (multi-axis)
    - Highlight anomalous data points with distinct red markers on each chart
    - Configure Plotly interactive features: zoom, pan, hover tooltips with exact values, trace toggling
    - _Requirements: 5.4, 5.5, 6.4_

  - [x] 7.3 Implement single-run detail view UI
    - Build tabbed interface with detail view containing all interactive charts
    - Display ML quality score summary: overall 0–100 score, status label, sub-score breakdown (MCS/SNR/NSS), model used
    - Display anomaly list: type, severity, description, affected metrics for each flagged point
    - Escape all user-provided strings through `html.escape()` before embedding
    - _Requirements: 6.2, 6.5, 6.6, 5.6_

  - [x] 7.4 Implement multi-run comparison view UI
    - Build comparison tab with overlay charts and statistical comparison table
    - Implement `render_comparison_table()` for side-by-side statistics
    - Support tabbed switching between single-run detail and multi-run comparison views
    - Color-code traces per run with distinct colors
    - _Requirements: 6.3, 7.7_

  - [x] 7.5 Implement `HTMLGenerator.generate()` to assemble and write the final HTML file
    - Load Plotly.js source via `plotly` package (`plotly.offline.get_plotlyjs()`)
    - Build chart configs for each bundle
    - Serialize bundle data as embedded JSON
    - Render HTML from template with all components assembled
    - Write to output file
    - Verify file size: < 10 MB for single-run, < 20 MB for 5-run comparison
    - _Requirements: 5.1, 5.3, 5.7_

  - [ ]* 7.6 Write property test: HTML self-containment
    - **Property 6: HTML Self-Containment** — The generated HTML file contains zero external resource references (no `<script src="http...">`, no `<link href="http...">`, no `fetch()` calls)
    - Parse generated HTML and search for external URLs
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 7.7 Write unit tests for HTMLGenerator
    - Test generated HTML is valid HTML5 (parse with `html.parser`)
    - Test no external URLs in output
    - Test embedded JSON is parseable by `json.loads()`
    - Test `html.escape()` is applied to test names and file paths
    - Test file size constraints
    - _Requirements: 5.1–5.7, 6.1–6.6_

- [x] 8. Implement ComparisonEngine (JavaScript embedded in HTML)
  - [x] 8.1 Implement drag-and-drop `.wldata` file loading
    - Implement FileReader API-based drag-and-drop handler in JavaScript
    - Parse dropped `.wldata` JSON files and add to comparison set
    - Validate file format: check for `.wldata` extension and valid JSON structure
    - Display toast notification for invalid files: "Invalid file format. Please drop a .wldata file."
    - Leave existing charts and data unaffected on invalid drop
    - _Requirements: 7.1, 7.8_

  - [x] 8.2 Implement time-series alignment and statistical comparison
    - Implement `align_timeseries()`: align two runs by iteration index or normalized elapsed time
    - Implement `compute_deltas()`: per-metric differences between aligned runs
    - Implement `statistical_tests()`: Welch's t-test and Mann-Whitney U test for each metric (RSSI, SNR, MCS, Tx Rate, Latency)
    - Report p-values with significance at 0.05 threshold
    - Handle insufficient data: report "Insufficient data" when < 2 valid points per metric
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 8.3_

  - [x] 8.3 Implement overlay chart rendering for multiple runs
    - Update Plotly charts with overlaid traces from all loaded runs
    - Assign distinct trace colors per run (N runs → N colors)
    - Generate statistical comparison table with per-metric deltas and significance indicators
    - _Requirements: 7.2, 7.7_

  - [x] 8.4 Implement large data handling
    - Detect `.wldata` files exceeding 50 MB and display warning with downsample offer
    - Downsample charts with > 10,000 data points to every Nth point for rendering
    - Preserve full data for hover tooltips and statistical computations
    - _Requirements: 8.1, 8.2_

  - [ ]* 8.5 Write property test: statistical symmetry
    - **Property 5: Statistical Symmetry** — For any two runs A and B, `|statistical_tests(A, B).delta| == |statistical_tests(B, A).delta|` for each metric
    - **Validates: Requirements 7.6**

  - [ ]* 8.6 Write property test: comparison consistency
    - **Property 7: Comparison Consistency** — If runs A and B have identical time-series data, `statistical_tests(A, B).p_value >= 0.05` for all metrics
    - **Validates: Requirements 7.5**

  - [ ]* 8.7 Write property test: drag-drop additivity
    - **Property 10: Drag-Drop Additivity** — Loading N `.wldata` files via drag-and-drop results in exactly N runs displayed in the comparison view with N distinct trace colors
    - **Validates: Requirements 7.2**

  - [ ]* 8.8 Write unit tests for ComparisonEngine
    - Test drag-and-drop with valid `.wldata` file
    - Test invalid file rejection with toast notification
    - Test statistical comparison with known delta values
    - Test overlay rendering with 2 and 3 runs
    - _Requirements: 7.1–7.8, 8.1–8.3_

- [x] 9. Checkpoint — Verify viewer generation end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. CLI integration with wl_tool12.py
  - [x] 10.1 Add `--viewer`, `--compare`, and `--retrain-ml` CLI arguments to `wl_tool12.py`
    - Add `argparse` or `sys.argv` handling for new flags at the top of the `if __name__ == "__main__"` block (before the interactive menu)
    - `--viewer RUN_folder/` → invoke DataBundler + MLScoringEngine + HTMLGenerator pipeline
    - `--viewer RUN_A/ RUN_B/ --compare` → generate multi-run comparison viewer
    - `--retrain-ml` → retrain ML models from all historical data
    - Import `wl_viewer` module components
    - Preserve existing interactive mode when no `--viewer`/`--retrain-ml` flags are passed
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 10.2 Write unit tests for CLI integration
    - Test `--viewer RUN_Test0019/` produces a valid HTML file
    - Test `--viewer RUN_Test0019/ RUN_beta2/ --compare` produces a comparison viewer
    - Test `--retrain-ml` invokes retrain without errors
    - Test existing interactive mode still works when no new flags are passed
    - _Requirements: 9.1–9.3_

- [x] 11. Final integration and validation
  - [x] 11.1 End-to-end pipeline test with real data
    - Run full pipeline on `RUN_Test0019/`: bundle → score → generate HTML
    - Run full pipeline on `RUN_beta2/`: bundle → score → generate HTML
    - Generate a multi-run comparison viewer with both runs
    - Verify generated HTML files are self-contained and under size limits
    - Verify all charts render (parse HTML, check for Plotly div elements)
    - _Requirements: 1.1–1.8, 2.1–2.6, 3.1–3.7, 5.1–5.7, 9.1–9.2_

  - [ ]* 11.2 Write integration tests
    - Test end-to-end pipeline: `bundle() → score_bundle() → generate()` on real test run folders
    - Verify output HTML contains expected chart divs and embedded data
    - Verify `.wldata` file is valid JSON and round-trips correctly
    - _Requirements: 1.1–1.8, 5.1–5.7_

- [x] 12. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each major component
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The only new pip dependency is `plotly` — all other dependencies are already installed or stdlib
- `wl_viewer.py` is a standalone module; it does NOT modify `wl_tool12.py` internals (only CLI integration adds flags)
- Use existing test run data in `RUN_Test0019/` and `RUN_beta2/` for testing
- The ML history database stores only compressed feature vectors (~200 bytes per run), not full time-series
