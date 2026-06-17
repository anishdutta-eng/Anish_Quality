# Requirements Document

## Introduction

The Offline Data Viewer is a self-contained, browser-based visualization system for WiFi diagnostic test runs produced by `wl_tool12.py`. It enables wireless engineers to review individual test runs with interactive charts, compare multiple runs side-by-side, track quality trends over time, and present findings to senior engineers — all from a single HTML file opened in Chrome with no server or internet connection.

The system consists of a Python-side pipeline (DataBundler, MLScoringEngine, HTMLGenerator) that produces `.wldata` JSON bundles and self-contained `.html` viewer files, plus a client-side JavaScript ComparisonEngine embedded in the viewer for runtime multi-run analysis.

## Glossary

- **Viewer**: The self-contained HTML file that renders interactive charts and comparison views in Chrome via the `file://` protocol with no server or internet connection
- **DataBundler**: The Python component that reads a test run folder (CSV + JSON) and produces a normalized `.wldata` JSON bundle
- **MLScoringEngine**: The Python component that applies anomaly detection and quality scoring to a data bundle using IsolationForest and GradientBoostingRegressor models, with a rule-based fallback
- **HTMLGenerator**: The Python component that produces a self-contained HTML file with embedded Plotly.js, chart configurations, and scored data bundles
- **ComparisonEngine**: The client-side JavaScript module embedded in the Viewer that handles multi-run overlay, statistical comparison, and delta computation
- **WLDataBundle**: The JSON data structure (`.wldata` file) containing time-series data, metadata, statistics, quality scores, and anomaly annotations for a single test run
- **Run_Folder**: A directory following the `RUN_*` naming convention containing `diagnostics_*.csv` and `diagnostics_*.json` files from a `wl_tool12.py` test run
- **Quality_Score**: A 0–100 numeric score summarizing WiFi quality for a test run, composed of MCS (50 pts), SNR (35 pts), and NSS (15 pts) sub-scores
- **Anomaly**: A data point flagged as unusual by IsolationForest statistical analysis or rule-based threshold checks (RSSI drops, MCS instability, latency spikes)
- **Feature_Vector**: A compressed representation (~200 bytes) of a test run stored in the ML history database, summarizing key metrics for model training
- **ML_History_Database**: An opt-in SQLite database at `~/.wl_tool/ml_history.db` storing compressed feature vectors per run, tagged with AP model, location, band, and channel width
- **Sentinel_Value**: A numeric placeholder for missing data: `-1` for latency, `0.0` for rates
- **Run_Tag**: Contextual metadata attached to each run in the ML_History_Database: AP model, location, band, and channel width

## Requirements

### Requirement 1: Data Bundling

**User Story:** As a wireless engineer, I want to convert a test run folder into a portable data bundle, so that I can share and visualize test results independently of the original run environment.

#### Acceptance Criteria

1. WHEN a valid Run_Folder is provided, THE DataBundler SHALL parse the `diagnostics_*.csv` file and produce a WLDataBundle where the number of time-series rows equals the number of data rows in the CSV (excluding the header)
2. WHEN the CSV contains `N/A`, empty strings, or unparseable values in numeric fields, THE DataBundler SHALL convert those values to the appropriate Sentinel_Value (`-1` for latency, `0.0` for rates and other metrics)
3. WHEN the DataBundler processes a Run_Folder, THE DataBundler SHALL compute per-metric summary statistics (min, max, mean, median, standard deviation, 5th percentile, 95th percentile) for RSSI, SNR, Tx Rate, latency, MCS, channel utilization, and distance
4. WHEN the DataBundler is called twice on the same unchanged Run_Folder, THE DataBundler SHALL produce identical WLDataBundle objects (excluding the `generated_at` timestamp)
5. WHEN a Run_Folder is missing a `diagnostics_*.csv` or `diagnostics_*.json` file, THE DataBundler SHALL raise a BundleError with a message identifying the missing file and the expected naming convention
6. WHEN the CSV contains malformed rows (wrong column count, corrupted encoding), THE DataBundler SHALL skip those rows, log warnings, and continue bundling with the remaining valid rows
7. IF all rows in the CSV are malformed and zero valid rows remain, THEN THE DataBundler SHALL raise a BundleError stating "No valid data rows in CSV"
8. THE DataBundler SHALL normalize column names to a canonical schema and produce a versioned `.wldata` JSON file with a semver `version` field

### Requirement 2: ML Quality Scoring

**User Story:** As a wireless engineer, I want each test run automatically scored for WiFi quality, so that I can quickly assess whether a run meets performance expectations without manually inspecting every metric.

#### Acceptance Criteria

1. WHEN a WLDataBundle is provided, THE MLScoringEngine SHALL produce a Quality_Score with an `overall` value in the range [0, 100]
2. WHEN a trained GradientBoostingRegressor model exists at `~/.wl_tool/models/quality_model.pkl`, THE MLScoringEngine SHALL use that model for scoring and set `model_used` to `"gradient_boosting"`
3. WHEN no trained model exists at the expected path, THE MLScoringEngine SHALL fall back to rule-based scoring using MCS (50 points), SNR (35 points), and NSS (15 points) weights and set `model_used` to `"rule_based"`
4. WHEN the ML model file exists but cannot be deserialized, THE MLScoringEngine SHALL log a warning, delete the corrupted file, and fall back to rule-based scoring
5. THE MLScoringEngine SHALL map the overall score to a status label: "Excellent" for scores >= 85, "Good" for 70–84, "Fair" for 50–69, and "Poor" for scores below 50
6. WHEN a bundle contains no valid rows (all MCS < 0 or all SNR <= -50), THE MLScoringEngine SHALL return a Quality_Score with overall 0 and status "Unknown"

### Requirement 3: Anomaly Detection

**User Story:** As a wireless engineer, I want anomalous data points automatically flagged in my test runs, so that I can quickly identify WiFi performance issues like sudden signal drops, MCS instability, or latency spikes.

#### Acceptance Criteria

1. WHEN a time-series has 10 or more valid rows, THE MLScoringEngine SHALL run IsolationForest (contamination=0.1) on the feature matrix [RSSI, SNR, MCS, TxRate, Latency, ChannelUtil] to detect statistical outliers
2. WHEN a time-series has fewer than 10 valid rows, THE MLScoringEngine SHALL skip IsolationForest and use only rule-based anomaly detection
3. WHEN RSSI drops more than 15 dBm between consecutive iterations, THE MLScoringEngine SHALL flag the iteration as an "rssi_drop" Anomaly with severity "high"
4. WHEN MCS index drops 4 or more levels between consecutive iterations, THE MLScoringEngine SHALL flag the iteration as an "mcs_instability" Anomaly with severity "medium"
5. WHEN latency exceeds 3 times the running average of the previous 3 iterations, THE MLScoringEngine SHALL flag the iteration as a "latency_spike" Anomaly with severity "medium", or "high" if latency exceeds 5 times the running average
6. WHEN the same iteration is flagged by both IsolationForest and rule-based checks for the same anomaly type, THE MLScoringEngine SHALL keep only the anomaly with the highest severity and discard the duplicate
7. THE MLScoringEngine SHALL produce anomalies sorted by iteration in ascending order, where each Anomaly references a valid iteration present in the time-series and has a severity of "low", "medium", or "high"

### Requirement 4: ML History Database

**User Story:** As a wireless engineer, I want my test run data stored in a local database for model training, so that the ML scoring improves over time as I accumulate more test data.

#### Acceptance Criteria

1. WHEN a bundle is scored, THE MLScoringEngine SHALL append the run's compressed Feature_Vector (~200 bytes) to the ML_History_Database at `~/.wl_tool/ml_history.db`
2. WHEN appending to the ML_History_Database, THE MLScoringEngine SHALL tag each run with AP model, location, band, and channel width as Run_Tags for contextual filtering
3. WHEN the user invokes the retrain command, THE MLScoringEngine SHALL retrain the GradientBoostingRegressor and IsolationForest models from all historical data in the ML_History_Database
4. THE ML_History_Database SHALL be opt-in for external distribution to protect user privacy — the database file is stored locally and is not shared unless the user explicitly copies it

### Requirement 5: HTML Viewer Generation

**User Story:** As a wireless engineer, I want a single HTML file I can double-click to open in Chrome, so that I can review test results with interactive charts without needing a server, internet connection, or any special software.

#### Acceptance Criteria

1. WHEN one or more scored bundles are provided, THE HTMLGenerator SHALL produce a single self-contained HTML file with all JavaScript (including Plotly.js) and CSS embedded inline
2. THE HTMLGenerator SHALL produce HTML that contains zero external resource references — no `<script src="http...">`, no `<link href="http...">`, and no `fetch()` calls
3. THE HTMLGenerator SHALL produce valid HTML5 that renders correctly in Chrome via the `file://` protocol
4. WHEN a single bundle is provided, THE HTMLGenerator SHALL generate interactive Plotly.js charts for: RSSI vs Time, MCS vs Time, Tx Rate vs Time, Latency vs Time, SNR vs Time, Channel Utilization vs Time, Distance vs RSSI scatter, and a combined health dashboard
5. THE HTMLGenerator SHALL highlight anomalous data points on charts with distinct markers that visually differentiate them from normal data points
6. THE HTMLGenerator SHALL escape all user-provided strings (test names, file paths) through `html.escape()` before embedding to prevent XSS
7. THE HTMLGenerator SHALL produce a file under 10 MB for a single-run viewer and under 20 MB for a 5-run comparison viewer

### Requirement 6: Viewer User Interface

**User Story:** As a wireless engineer, I want a clean, minimalist viewer interface, so that I can focus on the data without being distracted by unnecessary controls or visual clutter.

#### Acceptance Criteria

1. THE Viewer SHALL present a simple, minimalist, and intuitive interface with no unnecessary controls or visual clutter
2. WHEN displaying a single run, THE Viewer SHALL show a tabbed interface with a detail view containing interactive charts and an ML quality score summary
3. WHEN multiple bundles are embedded, THE Viewer SHALL provide a tabbed interface to switch between single-run detail view and multi-run comparison view
4. THE Viewer SHALL support Plotly.js interactive features: zoom, pan, hover tooltips with exact values, and trace toggling on all charts
5. WHEN displaying the quality score, THE Viewer SHALL show the overall 0–100 score, the status label (Excellent/Good/Fair/Poor), sub-score breakdown (MCS, SNR, NSS), and the scoring model used (gradient_boosting or rule_based)
6. WHEN displaying anomalies, THE Viewer SHALL show anomaly type, severity, description, and affected metrics for each flagged data point

### Requirement 7: Drag-and-Drop Multi-Run Comparison

**User Story:** As a wireless engineer, I want to drag additional test run files onto the viewer to compare runs side-by-side, so that I can evaluate KGU vs DUT performance or compare the same AP at different distances without regenerating the viewer.

#### Acceptance Criteria

1. WHEN a user drops one or more `.wldata` files onto the Viewer, THE ComparisonEngine SHALL parse each file using the FileReader API and add the runs to the comparison set
2. WHEN N `.wldata` files are loaded (including the initially embedded run), THE ComparisonEngine SHALL display exactly N runs in the comparison view with N distinct trace colors
3. WHEN comparing two runs, THE ComparisonEngine SHALL align time-series data by iteration index or normalized elapsed time
4. WHEN comparing two runs, THE ComparisonEngine SHALL compute Welch's t-test and Mann-Whitney U test for each metric (RSSI, SNR, MCS, Tx Rate, Latency) and report p-values with significance at the 0.05 threshold
5. WHEN two runs have identical time-series data, THE ComparisonEngine SHALL report p-values >= 0.05 for all metrics (identical data is not flagged as significantly different)
6. WHEN comparing runs A and B, THE ComparisonEngine SHALL produce delta values where `|delta(A, B)| == |delta(B, A)|` for each metric (statistical symmetry)
7. WHEN comparing runs, THE ComparisonEngine SHALL render overlay charts with color-coded traces per run and generate a statistical comparison table with per-metric deltas and significance indicators
8. WHEN a user drops a non-`.wldata` file or a malformed JSON file, THE Viewer SHALL display a toast notification stating "Invalid file format. Please drop a .wldata file." and leave existing charts and data unaffected

### Requirement 8: Large Data Handling

**User Story:** As a wireless engineer running long test sessions, I want the viewer to handle large datasets gracefully, so that charts remain responsive even with thousands of iterations.

#### Acceptance Criteria

1. WHEN a `.wldata` file exceeds 50 MB, THE Viewer SHALL display a warning and offer to downsample the data to every Nth point for charting while keeping full data for statistical computations
2. WHEN a chart has more than 10,000 data points, THE Viewer SHALL downsample to every Nth point for rendering while preserving full data for hover tooltips and statistics
3. WHEN both runs in a comparison have fewer than 2 valid data points for a given metric, THE ComparisonEngine SHALL report an "Insufficient data" error for that metric instead of computing statistics

### Requirement 9: CLI Integration

**User Story:** As a wireless engineer, I want to generate viewers directly from the `wl_tool12.py` command line, so that viewer generation fits naturally into my existing test workflow.

#### Acceptance Criteria

1. WHEN the user runs `wl_tool12.py --viewer RUN_folder/`, THE CLI SHALL invoke the DataBundler, MLScoringEngine, and HTMLGenerator pipeline and produce a self-contained HTML viewer file
2. WHEN the user runs `wl_tool12.py --viewer RUN_A/ RUN_B/ --compare`, THE CLI SHALL generate a multi-run comparison viewer with all specified runs embedded
3. WHEN the user runs `wl_tool12.py --retrain-ml`, THE CLI SHALL retrain the ML models from all historical data in the ML_History_Database

### Requirement 10: Data Validation

**User Story:** As a wireless engineer, I want the system to validate all data against defined ranges, so that corrupted or out-of-range values do not produce misleading charts or scores.

#### Acceptance Criteria

1. THE DataBundler SHALL validate that `rssi_dbm` values are in the range [-120, 0]
2. THE DataBundler SHALL validate that `mcs_index` values are in the range [0, 12]
3. THE DataBundler SHALL validate that `snr_db` values are in the range [-50, 100]
4. THE DataBundler SHALL validate that `latency_ms` values are non-negative, with `N/A` values stored as Sentinel_Value `-1`
5. THE DataBundler SHALL validate that `tx_rate_mbps` values are non-negative, with `0` indicating a measurement failure
6. THE DataBundler SHALL validate that `quality_score.overall` is in the range [0, 100]
7. THE DataBundler SHALL validate that `anomaly.severity` is one of "low", "medium", or "high"
8. THE WLDataBundle SHALL contain at least 1 time-series row to be considered valid
