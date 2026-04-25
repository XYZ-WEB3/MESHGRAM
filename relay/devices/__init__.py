"""
Catalog of supported home-node hardware models.

Each entry is `(model_id, friendly_label, svg_filename)`.
SVG files live in this same package directory. `model_id` is what gets
written to .env (NODE_MODEL=...). Use `get_label(id)` and `get_svg_path(id)`
to look things up.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

DEVICES_DIR = Path(__file__).parent

NODE_CATALOG: list[tuple[str, str, Optional[str]]] = [
    ("generic", "— Не выбрано / другое —", None),

    # ── Heltec ───────────────────────────────────────────────────────
    ("heltec_v3",                 "Heltec WiFi LoRa 32 V3",         "heltec-v3-case.svg"),
    ("heltec_v4",                 "Heltec WiFi LoRa 32 V4",         "heltec_v4.svg"),
    ("heltec_wsl_v3",             "Heltec Wireless Stick Lite V3",  "heltec-wsl-v3.svg"),
    ("heltec_mesh_pocket",        "Heltec Mesh Pocket",             "heltec_mesh_pocket.svg"),
    ("heltec_mesh_node_t114",     "Heltec Mesh Node T114",          "heltec-mesh-node-t114.svg"),
    ("heltec_ht62",               "Heltec HT62 (ESP32-C3 / SX1262)","heltec-ht62-esp32c3-sx1262.svg"),
    ("heltec_wireless_paper",     "Heltec Wireless Paper",          "heltec-wireless-paper.svg"),
    ("heltec_wireless_tracker",   "Heltec Wireless Tracker",        "heltec-wireless-tracker.svg"),
    ("heltec_wireless_tracker_v2","Heltec Wireless Tracker V2",     "heltec_wireless_tracker_v2.svg"),
    ("heltec_vision_e213",        "Heltec Vision Master E213",      "heltec-vision-master-e213.svg"),
    ("heltec_vision_e290",        "Heltec Vision Master E290",      "heltec-vision-master-e290.svg"),
    ("heltec_vision_t190",        "Heltec Vision Master T190",      "heltec-vision-master-t190.svg"),

    # ── LilyGo ───────────────────────────────────────────────────────
    ("tbeam",                     "LilyGo T-Beam (1W)",             "tbeam-1w.svg"),
    ("tbeam_s3_core",             "LilyGo T-Beam S3 Core",          "tbeam-s3-core.svg"),
    ("t_echo",                    "LilyGo T-Echo",                  "t-echo.svg"),
    ("t_echo_plus",               "LilyGo T-Echo Plus",             "t-echo_plus.svg"),
    ("t_deck",                    "LilyGo T-Deck",                  "t-deck.svg"),
    ("t_deck_pro",                "LilyGo T-Deck Pro",              "tdeck_pro.svg"),
    ("tlora_pager",               "LilyGo T-LoRa Pager",            "lilygo-tlora-pager.svg"),
    ("tlora_t3s3_v1",             "LilyGo T-LoRa T3S3 V1",          "tlora-t3s3-v1.svg"),
    ("tlora_t3s3_epaper",         "LilyGo T-LoRa T3S3 e-Paper",     "tlora-t3s3-epaper.svg"),

    # ── RAK ──────────────────────────────────────────────────────────
    ("rak4631",                   "RAK4631 / WisBlock",             "rak4631_case.svg"),
    ("rak_wismesh_tap",           "RAK WisMesh Tap",                "rak-wismeshtap.svg"),
    ("rak_wismesh_tap_v2",        "RAK WisMesh Tap V2",             "rak-wismesh-tap-v2.svg"),
    ("rak_wismesh_tag",           "RAK WisMesh Tag",                "rak_wismesh_tag.svg"),
    ("rak11310",                  "RAK11310",                       "rak11310.svg"),
    ("rak2560",                   "RAK2560",                        "rak2560.svg"),
    ("rak3401",                   "RAK3401",                        "rak3401.svg"),
    ("rak3312",                   "RAK3312",                        "rak_3312.svg"),
    ("station_g2",                "RAK Station G2",                 "station-g2.svg"),

    # ── Seeed / Xiao ─────────────────────────────────────────────────
    ("xiao_s3",                   "Seeed Xiao S3",                  "seeed-xiao-s3.svg"),
    ("xiao_nrf52_kit",            "Seeed Xiao nRF52 Kit",           "seeed_xiao_nrf52_kit.svg"),
    ("sensecap_indicator",        "Seeed SenseCAP Indicator",       "seeed-sensecap-indicator.svg"),
    ("seeed_solar",               "Seeed Solar Mini",               "seeed_solar.svg"),

    # ── M5 ───────────────────────────────────────────────────────────
    ("m5_c6l",                    "M5 C6L",                         "m5_c6l.svg"),

    # ── CrowPanel ────────────────────────────────────────────────────
    ("crowpanel_2_8",             'CrowPanel 2.8"',                 "crowpanel_2_8.svg"),
    ("crowpanel_3_5",             'CrowPanel 3.5"',                 "crowpanel_3_5.svg"),
    ("crowpanel_7_0",             'CrowPanel 7.0"',                 "crowpanel_7_0.svg"),

    # ── Other ────────────────────────────────────────────────────────
    ("nano_g2_ultra",             "Nano G2 Ultra",                  "nano-g2-ultra.svg"),
    ("meteor_pro",                "Meteor Pro",                     "meteor_pro.svg"),
    ("muzi_base",                 "Muzi Base",                      "muzi_base.svg"),
    ("muzi_r1_neo",               "Muzi R1 Neo",                    "muzi_r1_neo.svg"),
    ("thinknode_m1",              "ThinkNode M1",                   "thinknode_m1.svg"),
    ("thinknode_m2",              "ThinkNode M2",                   "thinknode_m2.svg"),
    ("thinknode_m3",              "ThinkNode M3",                   "thinknode_m3.svg"),
    ("thinknode_m4",              "ThinkNode M4",                   "thinknode_m4.svg"),
    ("thinknode_m6",              "ThinkNode M6",                   "thinknode_m6.svg"),
    ("tracker_t1000_e",           "Tracker T1000-E",                "tracker-t1000-e.svg"),
    ("wio_tracker_l1_case",       "Wio Tracker L1 (case)",          "wio_tracker_l1_case.svg"),
    ("wio_tracker_l1_eink",       "Wio Tracker L1 (e-ink)",         "wio_tracker_l1_eink.svg"),

    ("other", "Другая модель (не из списка)", None),
]


# Reverse lookups (built once on import)
_BY_ID: dict[str, tuple[str, str, Optional[str]]] = {row[0]: row for row in NODE_CATALOG}


def get_label(model_id: str) -> str:
    row = _BY_ID.get(model_id)
    if row is None:
        return model_id or "—"
    return row[1]


def get_svg_path(model_id: str) -> Optional[Path]:
    row = _BY_ID.get(model_id)
    if row is None or row[2] is None:
        return None
    p = DEVICES_DIR / row[2]
    return p if p.exists() else None


def all_ids() -> list[str]:
    return [row[0] for row in NODE_CATALOG]
