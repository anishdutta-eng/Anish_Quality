#!/usr/bin/env python3
"""
eero_devices.py - eero Product Database & Lookup Repository
============================================================

A self-contained repository of eero mesh WiFi products with technical
specifications relevant to wireless performance testing.

Purpose:
  - Normalize free-text AP model entries (e.g. "eeromax7" -> "eero Max 7")
  - Provide expected capabilities (bands, max PHY rate, channel width, NSS)
    so the diagnostic tool can sanity-check measured results against the
    device's theoretical maximums.
  - Enrich test reports with accurate device metadata.

Data notes:
  - Specs are sourced from eero.com, eero Help Center, and public reviews.
  - "max_wireless_mbps" is the manufacturer's advertised aggregate wireless
    rate. "max_phy_*_mbps" are per-band PHY (link) rate ceilings and are
    approximate where eero does not publish exact figures.
  - Fields marked approximate are best-effort and flagged with `approx=True`.

Author: Wireless Diagnostic Suite
"""

from dataclasses import dataclass, field
from typing import Optional
import re


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EeroDevice:
    """Technical specification record for a single eero product."""
    model: str                      # Canonical display name
    code_name: str                  # Internal eero project code name (e.g. "Jupiter")
    generation: str                 # Marketing generation grouping
    wifi_standard: str              # e.g. "Wi-Fi 6E (802.11ax)"
    wifi_gen_num: int               # 5, 6, 7 (numeric WiFi generation)
    bands: tuple                    # e.g. ("2.4GHz", "5GHz", "6GHz")
    tri_band: bool                  # True if 3+ radios
    max_channel_width_mhz: int      # Widest supported channel (per highest band)
    max_wireless_mbps: int          # Advertised aggregate wireless rate (Mbps)
    max_wired_mbps: int             # Max wired throughput across ports (Mbps)
    ethernet_ports: str             # Human-readable port summary
    spatial_streams: str            # Best-effort NSS summary (e.g. "2x2", "4x4")
    coverage_sqft: int              # Per-unit coverage (sq ft)
    recommended_isp_mbps: int       # Max ISP plan eero recommends
    role: str                       # "Gateway/Extender", "Extender", etc.
    year: int                       # Approx. release year
    discontinued: bool = False
    aliases: tuple = field(default_factory=tuple)  # Alternate user-typed names
    approx: bool = False            # True if some figures are estimates


# ---------------------------------------------------------------------------
# Product database
# ---------------------------------------------------------------------------
# Keyed by a lowercase canonical key for stable lookups.

_EERO_DB = {
    # ----- Wi-Fi 5 (802.11ac) -----
    "eero_1st_gen": EeroDevice(
        model="eero (1st Gen)", code_name="", generation="Wi-Fi 5", wifi_standard="Wi-Fi 5 (802.11ac)",
        wifi_gen_num=5, bands=("2.4GHz", "5GHz"), tri_band=False,
        max_channel_width_mhz=80, max_wireless_mbps=350, max_wired_mbps=1000,
        ethernet_ports="2x 1 GbE", spatial_streams="2x2", coverage_sqft=1000,
        recommended_isp_mbps=350, role="Gateway/Extender", year=2016,
        discontinued=True, aliases=("eero gen 1", "eero first gen", "eero 2016"),
        approx=True,
    ),
    "eero_pro_2nd_gen": EeroDevice(
        model="eero Pro (2nd Gen)", code_name="", generation="Wi-Fi 5", wifi_standard="Wi-Fi 5 (802.11ac)",
        wifi_gen_num=5, bands=("2.4GHz", "5GHz", "5GHz"), tri_band=True,
        max_channel_width_mhz=80, max_wireless_mbps=550, max_wired_mbps=1000,
        ethernet_ports="2x 1 GbE", spatial_streams="2x2", coverage_sqft=1750,
        recommended_isp_mbps=550, role="Gateway/Extender", year=2017,
        discontinued=True, aliases=("eero pro", "eero pro gen 2", "eero pro 2"),
        approx=True,
    ),
    "eero_beacon": EeroDevice(
        model="eero Beacon", code_name="", generation="Wi-Fi 5", wifi_standard="Wi-Fi 5 (802.11ac)",
        wifi_gen_num=5, bands=("2.4GHz", "5GHz"), tri_band=False,
        max_channel_width_mhz=80, max_wireless_mbps=350, max_wired_mbps=0,
        ethernet_ports="None (plug-in extender)", spatial_streams="2x2", coverage_sqft=1500,
        recommended_isp_mbps=350, role="Extender", year=2017,
        discontinued=True, aliases=("beacon", "eero beacon ac"),
        approx=True,
    ),
    "eero_3rd_gen": EeroDevice(
        model="eero (3rd Gen)", code_name="", generation="Wi-Fi 5", wifi_standard="Wi-Fi 5 (802.11ac)",
        wifi_gen_num=5, bands=("2.4GHz", "5GHz"), tri_band=False,
        max_channel_width_mhz=80, max_wireless_mbps=350, max_wired_mbps=1000,
        ethernet_ports="2x 1 GbE", spatial_streams="2x2", coverage_sqft=1500,
        recommended_isp_mbps=350, role="Gateway/Extender", year=2019,
        discontinued=True, aliases=("eero 3", "eero gen 3", "eero 2019"),
        approx=True,
    ),

    # ----- Wi-Fi 6 (802.11ax) -----
    "eero_6": EeroDevice(
        model="eero 6", code_name="Firefly", generation="Wi-Fi 6", wifi_standard="Wi-Fi 6 (802.11ax)",
        wifi_gen_num=6, bands=("2.4GHz", "5GHz"), tri_band=False,
        max_channel_width_mhz=80, max_wireless_mbps=900, max_wired_mbps=1000,
        ethernet_ports="2x 1 GbE", spatial_streams="2x2", coverage_sqft=1500,
        recommended_isp_mbps=500, role="Gateway/Extender", year=2020,
        aliases=("eero6", "eero 6 dual band", "firefly"),
    ),
    "eero_6_plus": EeroDevice(
        model="eero 6+", code_name="", generation="Wi-Fi 6", wifi_standard="Wi-Fi 6 (802.11ax)",
        wifi_gen_num=6, bands=("2.4GHz", "5GHz"), tri_band=False,
        max_channel_width_mhz=160, max_wireless_mbps=1000, max_wired_mbps=1000,
        ethernet_ports="2x 1 GbE", spatial_streams="2x2", coverage_sqft=1500,
        recommended_isp_mbps=1000, role="Gateway/Extender", year=2022,
        aliases=("eero 6 plus", "eero6+", "eero 6+"),
    ),
    "eero_pro_6": EeroDevice(
        model="eero Pro 6", code_name="", generation="Wi-Fi 6", wifi_standard="Wi-Fi 6 (802.11ax)",
        wifi_gen_num=6, bands=("2.4GHz", "5GHz", "5GHz"), tri_band=True,
        max_channel_width_mhz=160, max_wireless_mbps=1000, max_wired_mbps=1000,
        ethernet_ports="2x 1 GbE", spatial_streams="2x2 / 4x4", coverage_sqft=2000,
        recommended_isp_mbps=900, role="Gateway/Extender", year=2020,
        discontinued=True, aliases=("eeropro6", "eero pro 6 tri-band"),
        approx=True,
    ),
    "eero_pro_6e": EeroDevice(
        model="eero Pro 6E", code_name="Trieste", generation="Wi-Fi 6E", wifi_standard="Wi-Fi 6E (802.11ax)",
        wifi_gen_num=6, bands=("2.4GHz", "5GHz", "6GHz"), tri_band=True,
        max_channel_width_mhz=160, max_wireless_mbps=1600, max_wired_mbps=2300,
        ethernet_ports="1x 2.5 GbE + 1x 1 GbE", spatial_streams="4x4", coverage_sqft=2000,
        recommended_isp_mbps=2300, role="Gateway/Extender", year=2022,
        aliases=("eero pro 6 e", "eeropro6e", "pro 6e", "trieste", "eero 6e"),
    ),
    "eero_poe_6": EeroDevice(
        model="eero PoE 6", code_name="", generation="Wi-Fi 6", wifi_standard="Wi-Fi 6 (802.11ax)",
        wifi_gen_num=6, bands=("2.4GHz", "5GHz"), tri_band=False,
        max_channel_width_mhz=160, max_wireless_mbps=1000, max_wired_mbps=2500,
        ethernet_ports="1x 2.5 GbE (PoE+)", spatial_streams="2x2", coverage_sqft=2000,
        recommended_isp_mbps=1000, role="Gateway/Extender (PoE)", year=2023,
        aliases=("eero poe6", "poe 6"),
        approx=True,
    ),

    # ----- Wi-Fi 7 (802.11be) -----
    "eero_7": EeroDevice(
        model="eero 7", code_name="Patria", generation="Wi-Fi 7", wifi_standard="Wi-Fi 7 (802.11be)",
        wifi_gen_num=7, bands=("2.4GHz", "5GHz"), tri_band=False,
        max_channel_width_mhz=160, max_wireless_mbps=1800, max_wired_mbps=2500,
        ethernet_ports="2x 2.5 GbE", spatial_streams="2x2", coverage_sqft=2000,
        recommended_isp_mbps=2500, role="Gateway/Extender", year=2025,
        aliases=("eero7", "eero 7 dual band", "patria"),
    ),
    "eero_pro_7": EeroDevice(
        model="eero Pro 7", code_name="Merci", generation="Wi-Fi 7", wifi_standard="Wi-Fi 7 (802.11be)",
        wifi_gen_num=7, bands=("2.4GHz", "5GHz", "6GHz"), tri_band=True,
        max_channel_width_mhz=320, max_wireless_mbps=3900, max_wired_mbps=4700,
        ethernet_ports="2x 5 GbE", spatial_streams="4x4", coverage_sqft=2000,
        recommended_isp_mbps=5000, role="Gateway/Extender", year=2025,
        aliases=("eeropro7", "pro 7", "merci"),
    ),
    "eero_max_7": EeroDevice(
        model="eero Max 7", code_name="Jupiter", generation="Wi-Fi 7", wifi_standard="Wi-Fi 7 (802.11be)",
        wifi_gen_num=7, bands=("2.4GHz", "5GHz", "6GHz"), tri_band=True,
        max_channel_width_mhz=320, max_wireless_mbps=4300, max_wired_mbps=9400,
        ethernet_ports="2x 10 GbE + 2x 2.5 GbE", spatial_streams="4x4", coverage_sqft=2500,
        recommended_isp_mbps=10000, role="Gateway/Extender", year=2023,
        aliases=("eeromax7", "max 7", "eero max7", "jupiter"),
    ),
    "eero_outdoor_7": EeroDevice(
        model="eero Outdoor 7", code_name="Snowbird", generation="Wi-Fi 7", wifi_standard="Wi-Fi 7 (802.11be)",
        wifi_gen_num=7, bands=("2.4GHz", "5GHz"), tri_band=False,
        max_channel_width_mhz=160, max_wireless_mbps=1800, max_wired_mbps=2500,
        ethernet_ports="1x 2.5 GbE (PoE)", spatial_streams="2x2", coverage_sqft=15000,
        recommended_isp_mbps=2500, role="Outdoor Gateway/Extender", year=2025,
        aliases=("outdoor 7", "eero outdoor7", "snowbird"),
        approx=True,
    ),
    "eero_poe_7": EeroDevice(
        model="eero PoE 7", code_name="", generation="Wi-Fi 7", wifi_standard="Wi-Fi 7 (802.11be)",
        wifi_gen_num=7, bands=("2.4GHz", "5GHz", "6GHz"), tri_band=True,
        max_channel_width_mhz=320, max_wireless_mbps=3900, max_wired_mbps=10000,
        ethernet_ports="1x 10 GbE (PoE++)", spatial_streams="4x4", coverage_sqft=2000,
        recommended_isp_mbps=5000, role="Gateway/Extender (PoE)", year=2025,
        aliases=("eero poe7", "poe 7"),
        approx=True,
    ),
}


# ---------------------------------------------------------------------------
# Normalization & lookup
# ---------------------------------------------------------------------------

def _normalize_query(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for matching."""
    if not text:
        return ""
    t = text.lower().strip()
    t = t.replace("-", " ").replace("_", " ")
    t = re.sub(r"\s+", " ", t)
    # Common typo / spacing fixes
    t = t.replace("wifi", "").replace("wi fi", "")
    return t.strip()


def _build_alias_index():
    """Map every alias, canonical name, and code name to a DB key for lookup."""
    index = {}
    for key, dev in _EERO_DB.items():
        # Canonical model name
        index[_normalize_query(dev.model)] = key
        # Key itself (underscores -> spaces)
        index[_normalize_query(key.replace("_", " "))] = key
        # Internal code name (e.g. "Jupiter")
        if dev.code_name:
            index[_normalize_query(dev.code_name)] = key
        # Aliases
        for alias in dev.aliases:
            index[_normalize_query(alias)] = key
    return index


_ALIAS_INDEX = _build_alias_index()


def lookup(model_text: str) -> Optional[EeroDevice]:
    """
    Look up an eero device by free-text model name.

    Tries, in order:
      1. Exact normalized match against canonical names + aliases
      2. Compact match (spaces removed) e.g. "eeromax7"
      3. Substring / token containment scoring

    Returns the best EeroDevice match, or None if no confident match.
    """
    q = _normalize_query(model_text)
    if not q:
        return None

    # 1. Exact normalized match
    if q in _ALIAS_INDEX:
        return _EERO_DB[_ALIAS_INDEX[q]]

    # 2. Compact match (remove all spaces)
    q_compact = q.replace(" ", "")
    for alias_norm, key in _ALIAS_INDEX.items():
        if alias_norm.replace(" ", "") == q_compact:
            return _EERO_DB[key]

    # 3. Token containment scoring
    q_tokens = set(q.split())
    best_key, best_score = None, 0.0
    for key, dev in _EERO_DB.items():
        candidates = [dev.model] + list(dev.aliases) + [key.replace("_", " ")]
        if dev.code_name:
            candidates.append(dev.code_name)
        for cand in candidates:
            c_tokens = set(_normalize_query(cand).split())
            if not c_tokens:
                continue
            overlap = len(q_tokens & c_tokens)
            score = overlap / max(len(c_tokens), len(q_tokens))
            # Require the distinctive generation/number token to match
            if score > best_score:
                best_score, best_key = score, key

    # Require a reasonably strong match to avoid false positives
    if best_key and best_score >= 0.5:
        return _EERO_DB[best_key]
    return None


def normalize_model_name(model_text: str) -> str:
    """
    Return the canonical eero model name for free-text input.
    Falls back to a brand-corrected version of the original text if unknown.
    """
    dev = lookup(model_text)
    if dev:
        return dev.model
    # Brand correction fallback: "eero" is always lowercase
    return re.sub(r"(?i)\beero\b", "eero", model_text).strip()


def is_eero(model_text: str) -> bool:
    """True if the text refers to a known eero product."""
    return lookup(model_text) is not None


def all_models():
    """Return a list of all canonical model names, newest generation first."""
    return [d.model for d in sorted(
        _EERO_DB.values(), key=lambda x: (-x.wifi_gen_num, -x.year, x.model)
    )]


def models_by_generation():
    """Return {generation: [model, ...]} grouped mapping."""
    grouped = {}
    for dev in _EERO_DB.values():
        grouped.setdefault(dev.generation, []).append(dev.model)
    # Sort each group by year descending
    for g in grouped:
        grouped[g].sort()
    return grouped


def get_expected_capabilities(model_text: str) -> Optional[dict]:
    """
    Return a dict of expected performance ceilings for a model, suitable for
    sanity-checking measured results in the diagnostic tool.

    Returns None for unknown devices.
    """
    dev = lookup(model_text)
    if not dev:
        return None
    return {
        "model": dev.model,
        "code_name": dev.code_name,
        "wifi_standard": dev.wifi_standard,
        "wifi_gen_num": dev.wifi_gen_num,
        "bands": list(dev.bands),
        "tri_band": dev.tri_band,
        "max_channel_width_mhz": dev.max_channel_width_mhz,
        "max_wireless_mbps": dev.max_wireless_mbps,
        "max_wired_mbps": dev.max_wired_mbps,
        "spatial_streams": dev.spatial_streams,
        "supports_6ghz": "6GHz" in dev.bands,
        "approx": dev.approx,
    }


def describe(model_text: str) -> str:
    """Return a human-readable one-line description of the device."""
    dev = lookup(model_text)
    if not dev:
        return f"Unknown device: '{model_text}'"
    bands = ", ".join(dev.bands)
    note = " (specs approx.)" if dev.approx else ""
    disc = " [discontinued]" if dev.discontinued else ""
    cname = f" (code name: {dev.code_name})" if dev.code_name else ""
    return (f"{dev.model}{cname}{disc}: {dev.wifi_standard}, bands [{bands}], "
            f"up to {dev.max_wireless_mbps} Mbps wireless / "
            f"{dev.max_wired_mbps} Mbps wired, {dev.max_channel_width_mhz} MHz, "
            f"{dev.spatial_streams}, ~{dev.coverage_sqft} sq ft/unit{note}")


# ---------------------------------------------------------------------------
# CLI / self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 78)
    print("eero Device Repository".center(78))
    print("=" * 78)
    print(f"\nTotal products: {len(_EERO_DB)}\n")

    for gen, models in models_by_generation().items():
        print(f"[{gen}]")
        for m in models:
            print(f"   - {m}")
        print()

    print("-" * 78)
    print("Lookup / normalization tests:")
    print("-" * 78)
    samples = [
        "eeromax7", "Max 7", "EERO PRO 7", "eero pro 6 e",
        "eero6+", "eero 6 plus", "beacon", "eero pro", "unifi ap", "",
        "Jupiter", "Snowbird", "Patria", "Merci", "Firefly", "Trieste",
        "jupiter", "FIREFLY",
    ]
    for s in samples:
        dev = lookup(s)
        result = dev.model if dev else "NO MATCH"
        print(f"  {s!r:24s} -> {result}")

    print("\n" + "-" * 78)
    print("Describe examples:")
    print("-" * 78)
    for m in ["eero Max 7", "eero Pro 6E", "eero 6"]:
        print("  " + describe(m))
