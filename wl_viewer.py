"""
Wireless Diagnostics Offline Data Viewer

Self-contained browser-based interactive visualization system for WiFi
diagnostic test runs produced by wl_tool12.py. Generates .wldata JSON
bundles and self-contained HTML viewer files that open in Chrome with
no server or internet connection.

Author: Anish Dutta
Version: 1.0.0
"""

__version__ = "1.0.0"

import os
import sys
import csv
import json
import glob
import html
import sqlite3
import logging
import warnings
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

import numpy as np

logger = logging.getLogger(__name__)


# ===== EXCEPTIONS =====

class BundleError(Exception):
    """Raised when a test run folder cannot be bundled."""
    pass


# ===== HELPER FUNCTIONS =====

def safe_float(value, default: float = 0.0) -> float:
    """Convert any value to float, handling 'N/A', empty strings, and None.

    >>> safe_float("42.5")
    42.5
    >>> safe_float("N/A", -1.0)
    -1.0
    >>> safe_float("", 0.0)
    0.0
    >>> safe_float(None)
    0.0
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s.upper() == "N/A":
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def safe_int(value, default: int = 0) -> int:
    """Convert any value to int, handling 'N/A', empty strings, and None.

    >>> safe_int("11")
    11
    >>> safe_int("N/A", -1)
    -1
    >>> safe_int("")
    0
    >>> safe_int(None)
    0
    """
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value).strip()
    if not s or s.upper() == "N/A":
        return default
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return default


def score_to_status(score: int) -> str:
    """Map a numeric quality score (0-100) to a status label.

    >>> score_to_status(90)
    'Excellent'
    >>> score_to_status(75)
    'Good'
    >>> score_to_status(55)
    'Fair'
    >>> score_to_status(30)
    'Poor'
    """
    if score >= 85:
        return "Excellent"
    elif score >= 70:
        return "Good"
    elif score >= 50:
        return "Fair"
    else:
        return "Poor"


# ===== DATA MODELS =====

@dataclass
class TimeSeriesRow:
    """A single iteration measurement from a WiFi diagnostic test run."""
    iteration: int = 0
    timestamp_s: float = 0.0
    ssid: str = ""
    channel: str = ""
    bssid: str = ""
    rssi_dbm: float = 0.0
    snr_db: float = 0.0
    noise_dbm: float = 0.0
    tx_rate_mbps: float = 0.0
    latency_ms: float = -1.0      # -1 = missing/N/A
    mcs_index: int = -1            # -1 = missing/N/A
    phy_mode: str = ""             # "11ax", "11ac", "11n"
    nss: int = 1
    channel_util_pct: float = 0.0
    distance_m: float = 0.0
    health_status: str = ""        # "Excellent", "Good", "Bad"


@dataclass
class RoamingEvent:
    """A roaming event between two BSSIDs."""
    timestamp: float = 0.0
    from_bssid: str = ""
    to_bssid: str = ""


@dataclass
class InterferenceEvent:
    """An interference incident with one or more issues."""
    timestamp: float = 0.0
    issues: List[str] = field(default_factory=list)


@dataclass
class RunMetadata:
    """Metadata for a test run parsed from the JSON diagnostics file."""
    test_name: str = ""
    timestamp: str = ""            # ISO 8601
    ssid: str = ""
    channel: str = ""
    bssid: str = ""
    total_iterations: int = 0
    total_roaming_events: int = 0
    interference_incidents: int = 0
    unique_bssids: int = 0
    roaming_events: List[RoamingEvent] = field(default_factory=list)
    interference_log: List[InterferenceEvent] = field(default_factory=list)


@dataclass
class MetricStats:
    """Summary statistics for a single metric."""
    min: float = 0.0
    max: float = 0.0
    mean: float = 0.0
    median: float = 0.0
    std: float = 0.0
    p5: float = 0.0
    p95: float = 0.0


@dataclass
class RunStatistics:
    """Per-metric summary statistics for a test run."""
    rssi: MetricStats = field(default_factory=MetricStats)
    snr: MetricStats = field(default_factory=MetricStats)
    tx_rate: MetricStats = field(default_factory=MetricStats)
    latency: MetricStats = field(default_factory=MetricStats)
    mcs: MetricStats = field(default_factory=MetricStats)
    channel_util: MetricStats = field(default_factory=MetricStats)
    distance: MetricStats = field(default_factory=MetricStats)


@dataclass
class Anomaly:
    """An anomalous data point flagged by ML or rule-based detection."""
    iteration: int = 0
    timestamp_s: float = 0.0
    anomaly_type: str = ""         # "rssi_drop", "mcs_instability", "latency_spike", "statistical_outlier"
    severity: str = ""             # "low", "medium", "high"
    description: str = ""
    affected_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class QualityScore:
    """WiFi quality score for a test run (0-100)."""
    overall: int = 0               # 0-100
    mcs_score: int = 0             # 0-50
    snr_score: int = 0             # 0-35
    nss_score: int = 0             # 0-15
    status: str = ""               # "Excellent", "Good", "Fair", "Poor", "Unknown"
    details: List[str] = field(default_factory=list)
    model_used: str = "rule_based" # "gradient_boosting" or "rule_based"


@dataclass
class WLDataBundle:
    """Complete data bundle for a single test run (.wldata file format)."""
    version: str = "1.0"
    test_name: str = ""
    generated_at: str = ""
    time_series: List[TimeSeriesRow] = field(default_factory=list)
    metadata: Optional[RunMetadata] = None
    statistics: Optional[RunStatistics] = None
    quality_score: Optional[QualityScore] = None
    anomalies: List[Anomaly] = field(default_factory=list)
    heatmap_image_b64: str = ""    # Base64-encoded coverage heatmap PNG (if available)


# ===== DATA BUNDLER =====

class DataBundler:
    """Reads a test run folder (CSV + JSON) and produces a WLDataBundle."""

    def parse_csv(self, csv_path: str) -> List[TimeSeriesRow]:
        """Parse a diagnostics CSV file into typed TimeSeriesRow objects.

        Handles N/A values, malformed rows, and validates numeric ranges.
        Skips rows with wrong column count or unparseable data.
        """
        rows = []
        warnings_list = []

        with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                raise BundleError(f"CSV file is empty: {csv_path}")

            for line_num, raw in enumerate(reader, start=2):
                if len(raw) < 16:
                    warnings_list.append(f"Line {line_num}: wrong column count ({len(raw)}), skipping")
                    continue

                try:
                    rssi = safe_float(raw[5])
                    mcs = safe_int(raw[10], default=-1)
                    snr = safe_float(raw[6])
                    latency = safe_float(raw[9], default=-1.0)
                    tx_rate = safe_float(raw[8])

                    # Validate ranges
                    if rssi != 0.0 and not (-120 <= rssi <= 0):
                        rssi = 0.0
                    if mcs != -1 and not (0 <= mcs <= 12):
                        mcs = -1
                    if snr != 0.0 and not (-50 <= snr <= 100):
                        snr = 0.0

                    row = TimeSeriesRow(
                        iteration=safe_int(raw[0]),
                        timestamp_s=safe_float(raw[1]),
                        ssid=raw[2].strip(),
                        channel=raw[3].strip().replace("\n", " ").replace("\r", ""),
                        bssid=raw[4].strip(),
                        rssi_dbm=rssi,
                        snr_db=snr,
                        noise_dbm=safe_float(raw[7]),
                        tx_rate_mbps=max(0.0, tx_rate),
                        latency_ms=max(-1.0, latency),
                        mcs_index=mcs,
                        phy_mode=raw[11].strip() if len(raw) > 11 else "",
                        nss=max(1, safe_int(raw[12], default=1)),
                        channel_util_pct=safe_float(raw[13]),
                        distance_m=safe_float(raw[14]),
                        health_status=raw[15].strip() if len(raw) > 15 else "",
                    )
                    rows.append(row)
                except Exception as e:
                    warnings_list.append(f"Line {line_num}: parse error ({e}), skipping")

        if warnings_list:
            for w in warnings_list:
                logger.warning(w)

        if not rows:
            raise BundleError(f"No valid data rows in CSV: {csv_path}")

        return rows

    def parse_json(self, json_path: str) -> RunMetadata:
        """Parse a diagnostics JSON file into RunMetadata."""
        with open(json_path, "r") as f:
            data = json.load(f)

        roaming = []
        for evt in data.get("roaming_events", []):
            roaming.append(RoamingEvent(
                timestamp=safe_float(evt.get("timestamp", 0)),
                from_bssid=evt.get("from_bssid", ""),
                to_bssid=evt.get("to_bssid", ""),
            ))

        interference = []
        for evt in data.get("interference_log", []):
            interference.append(InterferenceEvent(
                timestamp=safe_float(evt.get("timestamp", 0)),
                issues=evt.get("issues", []),
            ))

        conn = data.get("current_connection", {})
        summary = data.get("summary", {})

        return RunMetadata(
            test_name=data.get("test_name", ""),
            timestamp=data.get("timestamp", ""),
            ssid=conn.get("ssid", ""),
            channel=conn.get("channel", ""),
            bssid=conn.get("bssid", ""),
            total_iterations=summary.get("total_iterations", 0),
            total_roaming_events=summary.get("total_roaming_events", 0),
            interference_incidents=summary.get("interference_incidents", 0),
            unique_bssids=summary.get("unique_bssids", 0),
            roaming_events=roaming,
            interference_log=interference,
        )

    def compute_statistics(self, rows: List[TimeSeriesRow]) -> RunStatistics:
        """Compute per-metric summary statistics from time-series rows."""

        def _stats(values: List[float]) -> MetricStats:
            if not values:
                return MetricStats()
            arr = np.array(values, dtype=float)
            return MetricStats(
                min=float(np.min(arr)),
                max=float(np.max(arr)),
                mean=float(np.mean(arr)),
                median=float(np.median(arr)),
                std=float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
                p5=float(np.percentile(arr, 5)),
                p95=float(np.percentile(arr, 95)),
            )

        rssi_vals = [r.rssi_dbm for r in rows if r.rssi_dbm != 0.0]
        snr_vals = [r.snr_db for r in rows if r.snr_db != 0.0]
        tx_vals = [r.tx_rate_mbps for r in rows if r.tx_rate_mbps > 0]
        lat_vals = [r.latency_ms for r in rows if r.latency_ms >= 0]
        mcs_vals = [float(r.mcs_index) for r in rows if r.mcs_index >= 0]
        cu_vals = [r.channel_util_pct for r in rows if r.channel_util_pct > 0]
        dist_vals = [r.distance_m for r in rows if r.distance_m > 0]

        return RunStatistics(
            rssi=_stats(rssi_vals),
            snr=_stats(snr_vals),
            tx_rate=_stats(tx_vals),
            latency=_stats(lat_vals),
            mcs=_stats(mcs_vals),
            channel_util=_stats(cu_vals),
            distance=_stats(dist_vals),
        )

    def bundle(self, run_folder: str) -> WLDataBundle:
        """Parse a RUN_* folder and return a structured WLDataBundle."""
        run_folder = os.path.abspath(run_folder)

        # Discover files
        csv_files = glob.glob(os.path.join(run_folder, "diagnostics_*.csv"))
        json_files = glob.glob(os.path.join(run_folder, "diagnostics_*.json"))

        if not csv_files:
            raise BundleError(
                f"Missing required file in {run_folder}: expected diagnostics_*.csv"
            )
        if not json_files:
            raise BundleError(
                f"Missing required file in {run_folder}: expected diagnostics_*.json"
            )

        csv_path = csv_files[0]
        json_path = json_files[0]

        # Extract test name from CSV filename
        basename = os.path.basename(csv_path)
        test_name = basename.replace("diagnostics_", "").replace(".csv", "")

        # Parse
        time_series = self.parse_csv(csv_path)
        metadata = self.parse_json(json_path)
        statistics = self.compute_statistics(time_series)

        return WLDataBundle(
            version="1.0",
            test_name=test_name,
            generated_at=datetime.now().isoformat(),
            time_series=time_series,
            metadata=metadata,
            statistics=statistics,
            heatmap_image_b64=self._load_heatmap_image(run_folder, test_name),
        )

    def _load_heatmap_image(self, run_folder: str, test_name: str) -> str:
        """Find and base64-encode the coverage heatmap PNG if it exists."""
        import base64
        patterns = [
            f"network_diagnostics_plot_{test_name}_coverage_heatmap.png",
            f"network_diagnostics_plot_{test_name}_coverage_window.png",
        ]
        for pattern in patterns:
            path = os.path.join(run_folder, pattern)
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        return base64.b64encode(f.read()).decode("ascii")
                except Exception:
                    pass
        return ""

    def save_bundle(self, bundle: WLDataBundle, output_path: str) -> None:
        """Serialize a WLDataBundle to a .wldata JSON file."""
        data = asdict(bundle)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, default=str)



# ===== ML SCORING ENGINE =====

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def deduplicate_anomalies(anomalies: List[Anomaly]) -> List[Anomaly]:
    """Remove duplicate anomalies per (iteration, anomaly_type), keeping highest severity."""
    best = {}
    for a in anomalies:
        key = (a.iteration, a.anomaly_type)
        if key not in best or SEVERITY_ORDER.get(a.severity, 0) > SEVERITY_ORDER.get(best[key].severity, 0):
            best[key] = a
    return sorted(best.values(), key=lambda a: a.iteration)


def extract_run_features(time_series: List[TimeSeriesRow]) -> List[float]:
    """Build a 14-element feature vector summarizing an entire run for ML scoring."""
    rssi = [r.rssi_dbm for r in time_series if r.rssi_dbm != 0]
    snr = [r.snr_db for r in time_series if r.snr_db != 0]
    mcs = [float(r.mcs_index) for r in time_series if r.mcs_index >= 0]
    tx = [r.tx_rate_mbps for r in time_series if r.tx_rate_mbps > 0]
    lat = [r.latency_ms for r in time_series if r.latency_ms >= 0]
    cu = [r.channel_util_pct for r in time_series if r.channel_util_pct > 0]

    def _mean(v): return float(np.mean(v)) if v else 0.0
    def _std(v): return float(np.std(v)) if len(v) > 1 else 0.0

    return [
        _mean(rssi), _std(rssi),
        _mean(snr), _std(snr),
        _mean(mcs), _std(mcs),
        _mean(tx), _std(tx),
        _mean(lat), _std(lat),
        _mean(cu),
        float(len(time_series)),
        0.0,  # num_roaming_events (filled by caller)
        0.0,  # num_interference_events (filled by caller)
    ]


class MLScoringEngine:
    """Applies anomaly detection and quality scoring to data bundles."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.expanduser("~/.wl_tool/ml_history.db")
        self.db_path = db_path
        self.model_dir = os.path.expanduser("~/.wl_tool/models")

    def score_quality(self, bundle: WLDataBundle) -> QualityScore:
        """Score a test run's WiFi quality 0-100. Uses ML model if available, else rule-based."""
        ts = bundle.time_series

        # Try ML model
        model_path = os.path.join(self.model_dir, "quality_model.pkl")
        if os.path.exists(model_path):
            try:
                import joblib
                model = joblib.load(model_path)
                fv = extract_run_features(ts)
                overall = int(np.clip(model.predict([fv])[0], 0, 100))
                return QualityScore(
                    overall=overall, mcs_score=-1, snr_score=-1, nss_score=-1,
                    status=score_to_status(overall),
                    details=["Scored by GradientBoosting model"],
                    model_used="gradient_boosting",
                )
            except Exception as e:
                logger.warning(f"ML model load failed: {e}. Deleting and falling back to rule-based.")
                try:
                    os.remove(model_path)
                except OSError:
                    pass

        # Rule-based fallback
        valid = [r for r in ts if r.mcs_index >= 0 and r.snr_db > -50]
        if not valid:
            return QualityScore(0, 0, 0, 0, "Unknown", ["Insufficient data"], "rule_based")

        avg_mcs = float(np.mean([r.mcs_index for r in valid]))
        avg_snr = float(np.mean([r.snr_db for r in valid]))
        avg_nss = float(np.mean([r.nss for r in valid]))

        # MCS scoring (50 points)
        mcs_score = 50 if avg_mcs >= 8 else (35 if avg_mcs >= 5 else (20 if avg_mcs >= 3 else 10))
        # SNR scoring (35 points)
        snr_score = 35 if avg_snr >= 35 else (28 if avg_snr >= 25 else (20 if avg_snr >= 20 else (12 if avg_snr >= 15 else 5)))
        # NSS scoring (15 points)
        nss_score = 15 if avg_nss >= 4 else (12 if avg_nss >= 3 else (8 if avg_nss >= 2 else 4))

        overall = min(mcs_score + snr_score + nss_score, 100)

        return QualityScore(
            overall=overall,
            mcs_score=mcs_score,
            snr_score=snr_score,
            nss_score=nss_score,
            status=score_to_status(overall),
            details=[
                f"MCS: {avg_mcs:.1f} avg -> {mcs_score}/50",
                f"SNR: {avg_snr:.1f} dB avg -> {snr_score}/35",
                f"NSS: {avg_nss:.1f} avg -> {nss_score}/15",
            ],
            model_used="rule_based",
        )

    def detect_anomalies(self, time_series: List[TimeSeriesRow]) -> List[Anomaly]:
        """Detect anomalous iterations using IsolationForest + rule-based checks."""
        anomalies = []

        # IsolationForest (needs >= 10 valid rows)
        features = []
        valid_indices = []
        for i, r in enumerate(time_series):
            if r.latency_ms >= 0 and r.tx_rate_mbps > 0 and r.mcs_index >= 0:
                features.append([r.rssi_dbm, r.snr_db, float(r.mcs_index),
                                 r.tx_rate_mbps, r.latency_ms, r.channel_util_pct])
                valid_indices.append(i)

        if len(features) >= 10:
            try:
                from sklearn.preprocessing import StandardScaler
                from sklearn.ensemble import IsolationForest
                X = np.array(features)
                X_scaled = StandardScaler().fit_transform(X)
                iso = IsolationForest(contamination=0.1, random_state=42, n_estimators=100)
                preds = iso.fit_predict(X_scaled)
                for j, pred in enumerate(preds):
                    if pred == -1:
                        idx = valid_indices[j]
                        r = time_series[idx]
                        anomalies.append(Anomaly(
                            iteration=r.iteration, timestamp_s=r.timestamp_s,
                            anomaly_type="statistical_outlier", severity="medium",
                            description=f"Statistical outlier at iter {r.iteration}",
                            affected_metrics={"rssi_dbm": r.rssi_dbm, "mcs_index": float(r.mcs_index)},
                        ))
            except ImportError:
                logger.warning("scikit-learn not available, skipping IsolationForest")

        # Rule-based checks
        for i in range(1, len(time_series)):
            prev, curr = time_series[i - 1], time_series[i]

            # RSSI drop > 15 dBm
            if prev.rssi_dbm != 0 and curr.rssi_dbm != 0:
                drop = prev.rssi_dbm - curr.rssi_dbm
                if drop > 15:
                    anomalies.append(Anomaly(
                        iteration=curr.iteration, timestamp_s=curr.timestamp_s,
                        anomaly_type="rssi_drop", severity="high",
                        description=f"RSSI dropped {drop:.0f} dBm ({prev.rssi_dbm} -> {curr.rssi_dbm})",
                        affected_metrics={"rssi_dbm": curr.rssi_dbm},
                    ))

            # MCS drop >= 4 levels
            if prev.mcs_index >= 0 and curr.mcs_index >= 0:
                mcs_drop = prev.mcs_index - curr.mcs_index
                if mcs_drop >= 4:
                    anomalies.append(Anomaly(
                        iteration=curr.iteration, timestamp_s=curr.timestamp_s,
                        anomaly_type="mcs_instability", severity="medium",
                        description=f"MCS dropped {mcs_drop} levels ({prev.mcs_index} -> {curr.mcs_index})",
                        affected_metrics={"mcs_index": float(curr.mcs_index)},
                    ))

            # Latency spike > 3x running average
            if i >= 3 and curr.latency_ms >= 0:
                recent = [time_series[k].latency_ms for k in range(max(0, i-3), i) if time_series[k].latency_ms >= 0]
                if recent:
                    avg = float(np.mean(recent))
                    if avg > 0 and curr.latency_ms > 3 * avg:
                        sev = "high" if curr.latency_ms > 5 * avg else "medium"
                        anomalies.append(Anomaly(
                            iteration=curr.iteration, timestamp_s=curr.timestamp_s,
                            anomaly_type="latency_spike", severity=sev,
                            description=f"Latency spike: {curr.latency_ms:.1f}ms (avg was {avg:.1f}ms)",
                            affected_metrics={"latency_ms": curr.latency_ms},
                        ))

        return deduplicate_anomalies(anomalies)

    def score_bundle(self, bundle: WLDataBundle) -> WLDataBundle:
        """Run anomaly detection + quality scoring on a bundle. Returns the bundle with scores."""
        bundle.anomalies = self.detect_anomalies(bundle.time_series)
        bundle.quality_score = self.score_quality(bundle)
        return bundle


    # ===== ML History Database =====

    def _init_db(self):
        """Initialize SQLite database and create tables if needed."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                ap_model TEXT DEFAULT '',
                band TEXT DEFAULT '',
                channel_width TEXT DEFAULT '',
                quality_score INTEGER DEFAULT 0,
                anomaly_count INTEGER DEFAULT 0,
                num_iterations INTEGER DEFAULT 0,
                feature_vector TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def append_to_history(self, bundle: WLDataBundle, ap_model: str = "",
                          band: str = "", channel_width: str = "") -> None:
        """Store a run's compressed feature vector in the ML history database."""
        self._init_db()
        fv = extract_run_features(bundle.time_series)
        # Add roaming/interference counts
        if bundle.metadata:
            fv[12] = float(bundle.metadata.total_roaming_events)
            fv[13] = float(bundle.metadata.interference_incidents)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO run_history
               (test_name, timestamp, ap_model, band, channel_width,
                quality_score, anomaly_count, num_iterations, feature_vector)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bundle.test_name,
                bundle.generated_at,
                ap_model,
                band,
                channel_width,
                bundle.quality_score.overall if bundle.quality_score else 0,
                len(bundle.anomalies),
                len(bundle.time_series),
                json.dumps(fv),
            )
        )
        conn.commit()
        conn.close()

    def retrain(self) -> None:
        """Retrain ML models from all historical data in SQLite."""
        self._init_db()
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT feature_vector, quality_score FROM run_history"
        ).fetchall()
        conn.close()

        if len(rows) < 10:
            logger.warning(f"Only {len(rows)} runs in history. Need >= 10 for training. Skipping.")
            return

        X = []
        y = []
        for fv_json, score in rows:
            try:
                fv = json.loads(fv_json)
                if len(fv) == 14 and score > 0:
                    X.append(fv)
                    y.append(score)
            except (json.JSONDecodeError, TypeError):
                continue

        if len(X) < 10:
            logger.warning("Insufficient valid training data. Skipping retrain.")
            return

        try:
            from sklearn.ensemble import GradientBoostingRegressor
            import joblib

            X_arr = np.array(X)
            y_arr = np.array(y)

            model = GradientBoostingRegressor(
                n_estimators=100, max_depth=3, random_state=42
            )
            model.fit(X_arr, y_arr)

            os.makedirs(self.model_dir, exist_ok=True)
            model_path = os.path.join(self.model_dir, "quality_model.pkl")
            joblib.dump(model, model_path)
            logger.info(f"Model retrained on {len(X)} runs, saved to {model_path}")
        except ImportError:
            logger.warning("scikit-learn/joblib not available. Cannot retrain.")



# ===== HTML GENERATOR =====

class HTMLGenerator:
    """Produces self-contained HTML viewer files with embedded Plotly.js."""

    def _get_plotly_js(self) -> str:
        """Get the full Plotly.js library source for inline embedding."""
        try:
            import plotly
            js_path = os.path.join(os.path.dirname(plotly.__file__), "package_data", "plotly.min.js")
            if os.path.exists(js_path):
                with open(js_path, "r") as f:
                    return f.read()
        except Exception:
            pass
        # Fallback: use CDN reference (not ideal for offline but functional)
        return ""

    def build_chart_configs(self, bundle: WLDataBundle) -> Dict[str, Any]:
        """Create Plotly trace/layout dicts for all chart types."""
        ts = bundle.time_series
        times = [r.timestamp_s for r in ts]
        iters = [r.iteration for r in ts]
        anomaly_iters = {a.iteration for a in bundle.anomalies}

        # Colors for normal vs anomaly points
        def _colors(values, metric_name=""):
            colors = []
            for r in ts:
                if r.iteration in anomaly_iters:
                    colors.append("red")
                else:
                    colors.append("#3498DB")
            return colors

        charts = {}

        # 1. RSSI vs Time
        charts["rssi"] = {
            "data": [{
                "x": times, "y": [r.rssi_dbm for r in ts],
                "type": "scatter", "mode": "lines+markers",
                "name": "RSSI (dBm)",
                "marker": {"color": _colors(ts), "size": 6},
                "line": {"color": "#E74C3C", "width": 2},
            }],
            "layout": {
                "title": "Signal Strength (RSSI) Over Time",
                "xaxis": {"title": "Time (s)"}, "yaxis": {"title": "RSSI (dBm)"},
                "height": 350, "margin": {"t": 40, "b": 40, "l": 60, "r": 20},
            }
        }

        # 2. MCS vs Time
        charts["mcs"] = {
            "data": [{
                "x": times, "y": [r.mcs_index for r in ts],
                "type": "scatter", "mode": "lines+markers",
                "name": "MCS Index",
                "line": {"color": "#3498DB", "width": 2},
                "marker": {"size": 6},
            }],
            "layout": {
                "title": "MCS Index Over Time",
                "xaxis": {"title": "Time (s)"}, "yaxis": {"title": "MCS Index", "range": [-1, 12]},
                "height": 350, "margin": {"t": 40, "b": 40, "l": 60, "r": 20},
            }
        }

        # 3. Tx Rate vs Time
        charts["tx_rate"] = {
            "data": [{
                "x": times, "y": [r.tx_rate_mbps for r in ts],
                "type": "scatter", "mode": "lines+markers",
                "name": "Tx Rate (Mbps)",
                "line": {"color": "#9B59B6", "width": 2},
                "marker": {"size": 6},
            }],
            "layout": {
                "title": "Throughput (Tx Rate) Over Time",
                "xaxis": {"title": "Time (s)"}, "yaxis": {"title": "Tx Rate (Mbps)"},
                "height": 350, "margin": {"t": 40, "b": 40, "l": 60, "r": 20},
            }
        }

        # 4. Latency vs Time
        lat_vals = [r.latency_ms if r.latency_ms >= 0 else None for r in ts]
        charts["latency"] = {
            "data": [{
                "x": times, "y": lat_vals,
                "type": "scatter", "mode": "lines+markers",
                "name": "Latency (ms)",
                "line": {"color": "#E67E22", "width": 2},
                "marker": {"size": 6},
                "connectgaps": False,
            }],
            "layout": {
                "title": "Network Latency Over Time",
                "xaxis": {"title": "Time (s)"}, "yaxis": {"title": "Latency (ms)"},
                "height": 350, "margin": {"t": 40, "b": 40, "l": 60, "r": 20},
            }
        }

        # 5. SNR vs Time
        charts["snr"] = {
            "data": [{
                "x": times, "y": [r.snr_db for r in ts],
                "type": "scatter", "mode": "lines+markers",
                "name": "SNR (dB)",
                "line": {"color": "#27AE60", "width": 2},
                "marker": {"size": 6},
            }],
            "layout": {
                "title": "Signal-to-Noise Ratio Over Time",
                "xaxis": {"title": "Time (s)"}, "yaxis": {"title": "SNR (dB)"},
                "height": 350, "margin": {"t": 40, "b": 40, "l": 60, "r": 20},
            }
        }

        # 6. Channel Utilization vs Time
        charts["channel_util"] = {
            "data": [{
                "x": times, "y": [r.channel_util_pct for r in ts],
                "type": "scatter", "mode": "lines+markers",
                "name": "Channel Util (%)",
                "line": {"color": "#F39C12", "width": 2},
                "marker": {"size": 6},
            }],
            "layout": {
                "title": "Channel Utilization Over Time",
                "xaxis": {"title": "Time (s)"}, "yaxis": {"title": "Channel Util (%)"},
                "height": 350, "margin": {"t": 40, "b": 40, "l": 60, "r": 20},
            }
        }

        # 7. Distance vs RSSI scatter
        charts["dist_rssi"] = {
            "data": [{
                "x": [r.distance_m for r in ts],
                "y": [r.rssi_dbm for r in ts],
                "text": [f"Iter {r.iteration}<br>MCS {r.mcs_index}<br>Tx {r.tx_rate_mbps} Mbps" for r in ts],
                "type": "scatter", "mode": "markers",
                "name": "RSSI vs Distance",
                "marker": {
                    "size": 10,
                    "color": [r.mcs_index for r in ts],
                    "colorscale": "RdYlGn", "showscale": True,
                    "colorbar": {"title": "MCS"},
                },
            }],
            "layout": {
                "title": "RSSI vs Estimated Distance (colored by MCS)",
                "xaxis": {"title": "Distance (m)"}, "yaxis": {"title": "RSSI (dBm)"},
                "height": 400, "margin": {"t": 40, "b": 40, "l": 60, "r": 80},
            }
        }

        return charts

    def generate(self, bundles: List[WLDataBundle], output_path: str,
                 title: str = "WiFi Diagnostics Viewer") -> str:
        """Generate a self-contained HTML viewer file."""
        plotly_js = self._get_plotly_js()

        # Build chart configs and data for each bundle
        all_data = []
        for b in bundles:
            charts = self.build_chart_configs(b)
            all_data.append({
                "test_name": html.escape(b.test_name),
                "charts": charts,
                "bundle": asdict(b),
            })

        embedded_json = json.dumps(all_data, default=str)

        html_content = self._render_html(title, plotly_js, embedded_json, len(bundles))

        with open(output_path, "w") as f:
            f.write(html_content)

        return output_path

    def _render_html(self, title: str, plotly_js: str, embedded_json: str, num_runs: int) -> str:
        """Render the complete HTML viewer."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<script>{plotly_js}</script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8f9fa; color: #2c3e50; }}
.header {{ background: #1a1a2e; color: white; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }}
.header h1 {{ font-size: 18px; font-weight: 600; }}
.header .score {{ font-size: 14px; padding: 6px 16px; border-radius: 20px; font-weight: 600; }}
.score-excellent {{ background: #27ae60; }}
.score-good {{ background: #2ecc71; }}
.score-fair {{ background: #f39c12; }}
.score-poor {{ background: #e74c3c; }}
.tabs {{ display: flex; background: #fff; border-bottom: 2px solid #e9ecef; padding: 0 24px; }}
.tab {{ padding: 12px 20px; cursor: pointer; border-bottom: 3px solid transparent; font-size: 13px; font-weight: 500; color: #7f8c8d; }}
.tab.active {{ color: #1a1a2e; border-bottom-color: #3498db; }}
.tab:hover {{ color: #2c3e50; }}
.content {{ padding: 20px 24px; max-width: 1400px; margin: 0 auto; }}
.card {{ background: white; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.card h3 {{ font-size: 14px; color: #7f8c8d; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }}
.stat {{ text-align: center; }}
.stat .value {{ font-size: 24px; font-weight: 700; color: #1a1a2e; }}
.stat .label {{ font-size: 11px; color: #95a5a6; margin-top: 2px; }}
.chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.chart-full {{ grid-column: 1 / -1; }}
.anomaly {{ padding: 8px 12px; margin: 4px 0; border-radius: 4px; font-size: 12px; }}
.anomaly-high {{ background: #fde8e8; border-left: 3px solid #e74c3c; }}
.anomaly-medium {{ background: #fef3e2; border-left: 3px solid #f39c12; }}
.anomaly-low {{ background: #e8f5e9; border-left: 3px solid #27ae60; }}
.drop-zone {{ border: 2px dashed #bdc3c7; border-radius: 8px; padding: 24px; text-align: center; color: #95a5a6; margin: 16px 0; transition: all 0.2s; }}
.drop-zone.active {{ border-color: #3498db; background: #ebf5fb; color: #3498db; }}
.toast {{ position: fixed; bottom: 20px; right: 20px; background: #e74c3c; color: white; padding: 12px 20px; border-radius: 6px; font-size: 13px; display: none; z-index: 1000; }}
.compare-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.compare-table th, .compare-table td {{ padding: 8px 12px; text-align: center; border-bottom: 1px solid #e9ecef; }}
.compare-table th {{ background: #f8f9fa; font-weight: 600; color: #7f8c8d; text-transform: uppercase; font-size: 10px; }}
.sig {{ color: #e74c3c; font-weight: 600; }}
.not-sig {{ color: #95a5a6; }}
@media (max-width: 768px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>{html.escape(title)}</h1>
  <div id="score-badge" class="score"></div>
</div>
<div class="tabs" id="tabs">
  <div class="tab active" onclick="showTab('detail')">Detail View</div>
  <div class="tab" onclick="showTab('compare')">Compare Runs</div>
</div>
<div id="detail-view" class="content">
  <div class="card">
    <h3>Quality Score</h3>
    <div class="stats-grid" id="score-summary"></div>
  </div>
  <div class="card">
    <h3>Key Metrics</h3>
    <div class="stats-grid" id="metrics-summary"></div>
  </div>
  <div class="card">
    <h3>Charts</h3>
    <div class="chart-grid" id="charts-container"></div>
  </div>
  <div class="card" id="anomaly-card" style="display:none">
    <h3>Anomalies Detected</h3>
    <div id="anomaly-list"></div>
  </div>
  <div class="card" id="heatmap-card" style="display:none">
    <h3>Coverage Heatmap</h3>
    <div id="heatmap-container" style="text-align:center"></div>
  </div>
</div>
<div id="compare-view" class="content" style="display:none">
  <div class="card">
    <div class="drop-zone" id="drop-zone">
      Drop .wldata files here to compare runs
    </div>
  </div>
  <div class="card" id="compare-table-card" style="display:none">
    <h3>Statistical Comparison</h3>
    <div id="compare-table-container"></div>
  </div>
  <div class="card" id="compare-charts-card" style="display:none">
    <h3>Overlay Charts</h3>
    <div id="compare-charts-container"></div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
const RUNS_DATA = {embedded_json};
const loadedRuns = [];
const COLORS = ['#3498DB','#E74C3C','#27AE60','#F39C12','#9B59B6','#1ABC9C','#E67E22','#2C3E50'];

function showTab(tab) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('detail-view').style.display = tab === 'detail' ? 'block' : 'none';
  document.getElementById('compare-view').style.display = tab === 'compare' ? 'block' : 'none';
  event.target.classList.add('active');
}}

function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3000);
}}

function renderScore(bundle) {{
  const qs = bundle.quality_score;
  if (!qs) return;
  const badge = document.getElementById('score-badge');
  badge.textContent = qs.overall + '/100 ' + qs.status;
  badge.className = 'score score-' + qs.status.toLowerCase();
  
  const summary = document.getElementById('score-summary');
  summary.innerHTML = `
    <div class="stat"><div class="value">${{qs.overall}}</div><div class="label">Overall</div></div>
    <div class="stat"><div class="value">${{qs.mcs_score >= 0 ? qs.mcs_score + '/50' : '-'}}</div><div class="label">MCS</div></div>
    <div class="stat"><div class="value">${{qs.snr_score >= 0 ? qs.snr_score + '/35' : '-'}}</div><div class="label">SNR</div></div>
    <div class="stat"><div class="value">${{qs.nss_score >= 0 ? qs.nss_score + '/15' : '-'}}</div><div class="label">NSS</div></div>
    <div class="stat"><div class="value">${{qs.model_used}}</div><div class="label">Model</div></div>
  `;
}}

function renderMetrics(stats) {{
  if (!stats) return;
  const el = document.getElementById('metrics-summary');
  const m = [
    ['RSSI', stats.rssi.mean.toFixed(1) + ' dBm'],
    ['SNR', stats.snr.mean.toFixed(1) + ' dB'],
    ['Tx Rate', stats.tx_rate.mean.toFixed(0) + ' Mbps'],
    ['Latency', stats.latency.mean.toFixed(1) + ' ms'],
    ['MCS', stats.mcs.mean.toFixed(1)],
    ['Ch. Util', stats.channel_util.mean.toFixed(0) + '%'],
  ];
  el.innerHTML = m.map(([l,v]) => `<div class="stat"><div class="value">${{v}}</div><div class="label">${{l}}</div></div>`).join('');
}}

function renderCharts(charts) {{
  const container = document.getElementById('charts-container');
  container.innerHTML = '';
  const order = ['rssi','mcs','tx_rate','latency','snr','channel_util','dist_rssi'];
  order.forEach((key, i) => {{
    if (!charts[key]) return;
    const div = document.createElement('div');
    div.id = 'chart-' + key;
    div.className = key === 'dist_rssi' ? 'chart-full' : '';
    container.appendChild(div);
    Plotly.newPlot(div.id, charts[key].data, charts[key].layout, {{responsive: true, displayModeBar: false}});
  }});
}}

function renderAnomalies(anomalies) {{
  if (!anomalies || anomalies.length === 0) return;
  document.getElementById('anomaly-card').style.display = 'block';
  const el = document.getElementById('anomaly-list');
  el.innerHTML = anomalies.map(a =>
    `<div class="anomaly anomaly-${{a.severity}}">
      <strong>Iter ${{a.iteration}}</strong> — ${{a.anomaly_type}} (${{a.severity}}) — ${{a.description}}
    </div>`
  ).join('');
}}

function renderHeatmap(bundle) {{
  const b64 = bundle.heatmap_image_b64;
  if (!b64) return;
  document.getElementById('heatmap-card').style.display = 'block';
  const el = document.getElementById('heatmap-container');
  el.innerHTML = `<img src="data:image/png;base64,${{b64}}" style="max-width:100%;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1)" alt="Coverage Heatmap"/>`;
}}

// Drag and drop
const dropZone = document.getElementById('drop-zone');
dropZone.addEventListener('dragover', e => {{ e.preventDefault(); dropZone.classList.add('active'); }});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('active'));
dropZone.addEventListener('drop', e => {{
  e.preventDefault(); dropZone.classList.remove('active');
  for (const file of e.dataTransfer.files) {{
    if (!file.name.endsWith('.wldata')) {{
      showToast('Invalid file format. Please drop a .wldata file.');
      continue;
    }}
    const reader = new FileReader();
    reader.onload = ev => {{
      try {{
        const data = JSON.parse(ev.target.result);
        loadedRuns.push(data);
        renderComparison();
      }} catch(err) {{
        showToast('Invalid file format. Please drop a .wldata file.');
      }}
    }};
    reader.readAsText(file);
  }}
}});

function renderComparison() {{
  if (loadedRuns.length === 0 && RUNS_DATA.length < 2) return;
  document.getElementById('compare-table-card').style.display = 'block';
  document.getElementById('compare-charts-card').style.display = 'block';
  
  const allRuns = [...RUNS_DATA.map(r => r.bundle), ...loadedRuns];
  
  // Comparison table
  const metrics = ['rssi','snr','tx_rate','latency','mcs'];
  const labels = ['RSSI (dBm)','SNR (dB)','Tx Rate (Mbps)','Latency (ms)','MCS Index'];
  let tableHtml = '<table class="compare-table"><tr><th>Metric</th>';
  allRuns.forEach((r,i) => tableHtml += `<th style="color:${{COLORS[i%COLORS.length]}}">${{r.test_name}}</th>`);
  tableHtml += '</tr>';
  metrics.forEach((m,mi) => {{
    tableHtml += `<tr><td>${{labels[mi]}}</td>`;
    allRuns.forEach(r => {{
      const s = r.statistics ? r.statistics[m] : null;
      tableHtml += `<td>${{s ? s.mean.toFixed(1) : '-'}}</td>`;
    }});
    tableHtml += '</tr>';
  }});
  tableHtml += '</table>';
  document.getElementById('compare-table-container').innerHTML = tableHtml;
  
  // Overlay charts
  const container = document.getElementById('compare-charts-container');
  container.innerHTML = '';
  ['rssi','mcs','tx_rate','latency','snr'].forEach(metric => {{
    const div = document.createElement('div');
    div.id = 'compare-' + metric;
    container.appendChild(div);
    const traces = allRuns.map((r,i) => ({{
      x: r.time_series.map(t => t.timestamp_s),
      y: r.time_series.map(t => t[metric + (metric==='rssi'?'_dbm':metric==='snr'?'_db':metric==='tx_rate'?'_mbps':metric==='latency'?'_ms':'_index')]),
      type: 'scatter', mode: 'lines+markers',
      name: r.test_name,
      line: {{color: COLORS[i%COLORS.length], width: 2}},
      marker: {{size: 5}},
    }}));
    Plotly.newPlot(div.id, traces, {{
      title: labels[['rssi','snr','tx_rate','latency','mcs'].indexOf(metric)] + ' Comparison',
      xaxis: {{title: 'Time (s)'}},
      height: 300, margin: {{t: 40, b: 40, l: 60, r: 20}},
    }}, {{responsive: true, displayModeBar: false}});
  }});
}}

// Initialize
if (RUNS_DATA.length > 0) {{
  const first = RUNS_DATA[0];
  renderScore(first.bundle);
  renderMetrics(first.bundle.statistics);
  renderCharts(first.charts);
  renderAnomalies(first.bundle.anomalies);
  renderHeatmap(first.bundle);
  if (RUNS_DATA.length > 1) renderComparison();
}}
</script>
</body>
</html>"""



# ===== STANDALONE LAUNCHER =====

def launch_viewer_gui():
    """Launch a simple GUI for drag-and-drop viewer generation."""
    import tkinter as tk
    from tkinter import filedialog, messagebox
    import subprocess as _sp
    import webbrowser

    bundler = DataBundler()
    ml_engine = MLScoringEngine()
    html_gen = HTMLGenerator()

    def process_folders(folders):
        """Bundle, score, generate viewer, and open in Chrome."""
        bundles = []
        for folder in folders:
            folder = folder.strip()
            if not folder or not os.path.isdir(folder):
                continue
            try:
                status_var.set(f"Bundling {os.path.basename(folder)}...")
                root.update()
                bundle = bundler.bundle(folder)
                scored = ml_engine.score_bundle(bundle)
                bundles.append(scored)
                # Save .wldata
                try:
                    bundler.save_bundle(scored, os.path.join(folder, f"{scored.test_name}.wldata"))
                except PermissionError:
                    bundler.save_bundle(scored, f"{scored.test_name}.wldata")
            except BundleError as e:
                messagebox.showerror("Bundle Error", str(e))
                return

        if not bundles:
            messagebox.showwarning("No Data", "No valid RUN folders found.")
            return

        status_var.set("Generating viewer...")
        root.update()

        if len(bundles) == 1:
            title = f"{bundles[0].test_name} WiFi Diagnostics"
            out = f"viewer_{bundles[0].test_name}.html"
        else:
            title = " vs ".join(b.test_name for b in bundles)
            out = "viewer_comparison.html"

        html_gen.generate(bundles, out, title)
        status_var.set(f"Done! Opening {out}...")
        root.update()

        # Open in default browser
        webbrowser.open(f"file://{os.path.abspath(out)}")
        status_var.set(f"Viewer ready: {out}")

    def browse_folders():
        folder = filedialog.askdirectory(title="Select a RUN_* folder")
        if folder:
            folder_list.append(folder)
            listbox.insert(tk.END, os.path.basename(folder))

    def generate():
        if not folder_list:
            messagebox.showwarning("No Folders", "Add at least one RUN folder.")
            return
        process_folders(folder_list)

    def clear_list():
        folder_list.clear()
        listbox.delete(0, tk.END)
        status_var.set("Ready")

    # Window
    root = tk.Tk()
    root.title("WiFi Diagnostics Viewer")
    root.geometry("480x400")
    root.configure(bg="#f8f9fa")

    folder_list = []
    status_var = tk.StringVar(value="Add RUN folders, then click Generate")

    # Title
    tk.Label(root, text="WiFi Diagnostics Viewer", font=("Helvetica", 16, "bold"),
             bg="#f8f9fa", fg="#1a1a2e").pack(pady=(16, 4))
    tk.Label(root, text="Add test run folders and generate interactive viewer",
             font=("Helvetica", 10), bg="#f8f9fa", fg="#7f8c8d").pack(pady=(0, 12))

    # Folder list
    frame = tk.Frame(root, bg="#f8f9fa")
    frame.pack(fill=tk.BOTH, expand=True, padx=20)

    listbox = tk.Listbox(frame, height=8, font=("Helvetica", 11), selectmode=tk.SINGLE,
                          bg="white", relief=tk.FLAT, highlightthickness=1, highlightcolor="#3498db")
    listbox.pack(fill=tk.BOTH, expand=True)

    # Buttons
    btn_frame = tk.Frame(root, bg="#f8f9fa")
    btn_frame.pack(pady=8)

    tk.Button(btn_frame, text="+ Add Folder", command=browse_folders,
              font=("Helvetica", 11), bg="#3498db", fg="white", relief=tk.FLAT,
              padx=16, pady=6).pack(side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="Generate Viewer", command=generate,
              font=("Helvetica", 11, "bold"), bg="#27ae60", fg="white", relief=tk.FLAT,
              padx=16, pady=6).pack(side=tk.LEFT, padx=4)
    tk.Button(btn_frame, text="Clear", command=clear_list,
              font=("Helvetica", 11), bg="#95a5a6", fg="white", relief=tk.FLAT,
              padx=16, pady=6).pack(side=tk.LEFT, padx=4)

    # Status
    tk.Label(root, textvariable=status_var, font=("Helvetica", 10),
             bg="#f8f9fa", fg="#7f8c8d").pack(pady=(4, 16))

    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # CLI mode
        folders = sys.argv[1:]
        bundler = DataBundler()
        ml = MLScoringEngine()
        gen = HTMLGenerator()

        bundles = []
        for folder in folders:
            if not os.path.isdir(folder):
                continue
            print(f"Bundling {folder}...")
            bundle = bundler.bundle(folder)
            scored = ml.score_bundle(bundle)
            bundles.append(scored)

        if bundles:
            if len(bundles) == 1:
                out = f"viewer_{bundles[0].test_name}.html"
                title = f"{bundles[0].test_name} WiFi Diagnostics"
            else:
                out = "viewer_comparison.html"
                title = " vs ".join(b.test_name for b in bundles)
            gen.generate(bundles, out, title)
            print(f"Viewer: {out}")
            print(f"Open: file://{os.path.abspath(out)}")
    else:
        # GUI mode
        launch_viewer_gui()
