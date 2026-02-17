#!/usr/bin/env python3
"""
Channel diff tracker - Kanal değişikliklerini takip eder
"""

import json
import os
from datetime import datetime

OUTPUT_DIR = "output"
HISTORY_FILE = os.path.join(OUTPUT_DIR, "history.json")


def load_previous_channels():
    """Önceki kanal listesini yükle"""
    channels_file = os.path.join(OUTPUT_DIR, "channels.json")
    if os.path.exists(channels_file):
        with open(channels_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def compare_channels(old_data, new_groups):
    """İki kanal listesini karşılaştır"""
    if not old_data:
        return {
            "added": sum(len(ch) for ch in new_groups.values()),
            "removed": 0,
            "modified": 0,
            "total": sum(len(ch) for ch in new_groups.values()),
            "details": {
                "added_groups": list(new_groups.keys()),
                "removed_groups": [],
                "changes": [],
            },
        }

    old_groups = old_data.get("groups", {})

    added_groups = []
    removed_groups = []
    modified_groups = []

    # Yeni eklenen gruplar
    for group in new_groups:
        if group not in old_groups:
            added_groups.append(group)

    # Kaldırılan gruplar
    for group in old_groups:
        if group not in new_groups:
            removed_groups.append(group)

    # Değişiklikleri kontrol et
    total_changes = []

    for group, channels in new_groups.items():
        if group not in old_groups:
            continue

        old_channels = {ch["name"]: ch for ch in old_groups[group]}
        new_channels = {ch["name"]: ch for ch in channels}

        # Yeni eklenen kanallar
        for name in new_channels:
            if name not in old_channels:
                total_changes.append({"type": "added", "group": group, "channel": name})

        # Kaldırılan kanallar
        for name in old_channels:
            if name not in new_channels:
                total_changes.append(
                    {"type": "removed", "group": group, "channel": name}
                )

        # URL değişiklikleri
        for name in new_channels:
            if name in old_channels:
                old_url = old_channels[name].get("url", "") or old_channels[name].get(
                    "hls", ""
                )
                new_url = new_channels[name].get("url", "") or new_channels[name].get(
                    "hls", ""
                )
                if old_url != new_url:
                    total_changes.append(
                        {
                            "type": "modified",
                            "group": group,
                            "channel": name,
                            "old_url": old_url,
                            "new_url": new_url,
                        }
                    )

    return {
        "added": sum(1 for c in total_changes if c["type"] == "added"),
        "removed": sum(1 for c in total_changes if c["type"] == "removed"),
        "modified": sum(1 for c in total_changes if c["type"] == "modified"),
        "total": sum(len(ch) for ch in new_groups.values()),
        "details": {
            "added_groups": added_groups,
            "removed_groups": removed_groups,
            "changes": total_changes[:50],  # İlk 50 değişiklik
        },
    }


def save_history(diff_result):
    """Değişiklik geçmişini kaydet"""
    history = []

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "added": diff_result["added"],
        "removed": diff_result["removed"],
        "modified": diff_result["modified"],
        "total": diff_result["total"],
    }

    history.insert(0, entry)

    # Son 100 kaydı tut
    history = history[:100]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def has_changes(diff_result):
    """Değişiklik var mı kontrol et"""
    return (
        diff_result["added"] > 0
        or diff_result["removed"] > 0
        or diff_result["modified"] > 0
    )


def print_diff(diff_result):
    """Değişiklikleri ekrana yazdır"""
    print("\n" + "=" * 60)
    print("KANAL DEĞİŞİKLİK RAPORU")
    print("=" * 60)
    print(f"Toplam Kanal: {diff_result['total']}")
    print(f"Yeni Eklenen: {diff_result['added']}")
    print(f"Kaldırılan: {diff_result['removed']}")
    print(f"Güncellenen: {diff_result['modified']}")

    details = diff_result.get("details", {})

    if details.get("added_groups"):
        print(f"\nYeni Gruplar: {', '.join(details['added_groups'])}")

    if details.get("removed_groups"):
        print(f"Kaldırılan Gruplar: {', '.join(details['removed_groups'])}")

    if details.get("changes"):
        print("\nDetaylı Değişiklikler (İlk 50):")
        for change in details["changes"][:10]:  # İlk 10
            if change["type"] == "added":
                print(f"  [+] {change['group']} - {change['channel']}")
            elif change["type"] == "removed":
                print(f"  [-] {change['group']} - {change['channel']}")
            elif change["type"] == "modified":
                print(f"  [~] {change['group']} - {change['channel']} (URL değişti)")

    print("=" * 60)
