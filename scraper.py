#!/usr/bin/env python3
"""
Vavoo.to M3U8 Scraper
Otomatik kanal çekme ve M3U8 playlist oluşturma
"""

import requests
import json
import re
import os
import base64
import random
import warnings
from datetime import datetime
from urllib.parse import quote_plus

# Disable SSL warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Import tracker - will be imported dynamically
tracker_loaded = False

# Constants
BASEURL = "https://www2.vavoo.to/ccapi/"
VAVOO_LIVE_URL = "https://www.vavoo.to/live2/index?output=json"
VAVOO_API_URL = "https://vavoo.to/mediahubmx-catalog.json"
PING_URL = "https://www.vavoo.tv/api/box/ping2"
LOKKE_URL = "https://www.lokke.app/api/app/ping"
VEC_URL = "http://mastaaa1987.github.io/repo/veclist.json"

# Output directory
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


class VavooScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        self.channels = []
        self.groups = {}
        self.auth_token = None
        self.watched_sig = None

    def get_veclist(self):
        """Get vector list for auth"""
        try:
            response = self.session.get(VEC_URL, timeout=10)
            data = response.json()
            return data.get("value", [])
        except Exception as e:
            print(f"Error fetching veclist: {e}")
            return []

    def get_auth_signature(self):
        """Get authentication signature from vavoo.tv"""
        veclist = self.get_veclist()
        if not veclist:
            print("No veclist available")
            return None

        sig = None
        for i in range(50):
            try:
                vec = {"vec": random.choice(veclist)}
                response = self.session.post(PING_URL, data=vec, timeout=10)
                data = response.json()

                if data.get("signed"):
                    sig = data["signed"]
                elif data.get("data", {}).get("signed"):
                    sig = data["data"]["signed"]
                elif data.get("response", {}).get("signed"):
                    sig = data["response"]["signed"]

                if sig:
                    break
            except Exception as e:
                continue

        return sig

    def get_watched_signature(self):
        """Get watched signature from lokke.app"""
        headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "accept-encoding": "gzip",
        }

        data = {
            "token": "",
            "reason": "boot",
            "locale": "de",
            "theme": "dark",
            "metadata": {
                "device": {"type": "desktop", "uniqueId": ""},
                "os": {
                    "name": "win32",
                    "version": "Windows 10",
                    "abis": ["x64"],
                    "host": "DESKTOP",
                },
                "app": {"platform": "electron"},
                "version": {
                    "package": "app.lokke.main",
                    "binary": "1.0.19",
                    "js": "1.0.19",
                },
            },
            "appFocusTime": 173,
            "playerActive": False,
            "playDuration": 0,
            "devMode": True,
            "hasAddon": True,
            "castConnected": False,
            "package": "app.lokke.main",
            "version": "1.0.19",
            "process": "app",
            "firstAppStart": 1770751158625,
            "lastAppStart": 1770751158625,
            "ipLocation": 0,
            "adblockEnabled": True,
            "proxy": {
                "supported": ["ss"],
                "engine": "cu",
                "enabled": False,
                "autoServer": True,
                "id": 0,
            },
            "iap": {"supported": False},
        }

        try:
            response = self.session.post(
                LOKKE_URL, json=data, headers=headers, timeout=10
            )
            result = response.json()
            return result.get("addonSig")
        except Exception as e:
            print(f"Error getting watched signature: {e}")
            return None

    def fetch_live_channels(self):
        """Fetch channels from vavoo.to/live2/index"""
        print("Fetching live channels from vavoo.to...")
        try:
            response = self.session.get(
                VAVOO_LIVE_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                timeout=30,
            )
            channels = response.json()
            print(f"Found {len(channels)} channels from live index")
            return channels
        except Exception as e:
            print(f"Error fetching live channels: {e}")
            return []

    def fetch_api_channels(self):
        """Fetch channels from vavoo API"""
        print("Fetching channels from vavoo API...")

        if not self.watched_sig:
            self.watched_sig = self.get_watched_signature()

        if not self.watched_sig:
            print("Could not get watched signature")
            return []

        headers = {
            "accept-encoding": "gzip",
            "user-agent": "MediaHubMX/2",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "mediahubmx-signature": self.watched_sig,
        }

        all_channels = []
        groups = self.get_groups()

        for group in groups:
            print(f"Fetching channels for group: {group}")
            cursor = 0
            while True:
                data = {
                    "language": "de",
                    "region": "AT",
                    "catalogId": "iptv",
                    "id": "iptv",
                    "adult": False,
                    "search": "",
                    "sort": "name",
                    "filter": {"group": group},
                    "cursor": cursor,
                    "clientVersion": "3.0.2",
                }

                try:
                    response = self.session.post(
                        VAVOO_API_URL, json=data, headers=headers, timeout=30
                    )
                    result = response.json()

                    items = result.get("items", [])
                    for item in items:
                        if "LUXEMBOURG" in item.get("name", "") and group == "Germany":
                            continue
                        all_channels.append(item)

                    next_cursor = result.get("nextCursor")
                    if not next_cursor:
                        break
                    cursor = next_cursor

                except Exception as e:
                    print(f"Error fetching API channels for {group}: {e}")
                    break

        print(f"Found {len(all_channels)} channels from API")
        return all_channels

    def get_groups(self):
        """Get available channel groups"""
        if not self.watched_sig:
            self.watched_sig = self.get_watched_signature()

        headers = {
            "user-agent": "WATCHED/1.8.3 (android)",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "cookie": "lng=",
            "watched-sig": self.watched_sig,
        }

        data = {"adult": True, "cursor": 0, "sort": "name"}

        try:
            response = self.session.post(
                "https://www.oha.to/oha-tv-index/directory.watched",
                json=data,
                headers=headers,
                timeout=10,
            )
            result = response.json()
            features = result.get("features", {})
            filter_data = features.get("filter", [])
            if filter_data:
                return [v.get("value") for v in filter_data[0].get("values", [])]
        except Exception as e:
            print(f"Error fetching groups: {e}")

        # Fallback groups
        return [
            "Germany",
            "Austria",
            "Switzerland",
            "Turkey",
            "United Kingdom",
            "USA",
            "Spain",
            "Italy",
            "France",
            "Poland",
            "Russia",
        ]

    def process_channels(self, live_channels, api_channels):
        """Process and merge channels from both sources"""
        print("Processing channels...")

        # Process live channels
        for ch in live_channels:
            country = ch.get("group", "Unknown")
            if country not in self.groups:
                self.groups[country] = []

            channel_data = {
                "name": ch.get("name", ""),
                "display_name": self.clean_name(ch.get("name", "")),
                "group": country,
                "logo": ch.get("logo", ""),
                "url": ch.get("url", ""),
                "hls": "",
            }
            self.groups[country].append(channel_data)

        # Process API channels and merge
        for ch in api_channels:
            country = ch.get("group", "Unknown")

            # Find existing channel
            existing = None
            if country in self.groups:
                for existing_ch in self.groups[country]:
                    if existing_ch["name"] == ch.get("name"):
                        existing = existing_ch
                        break

            if existing:
                existing["hls"] = ch.get("url", "")
                if ch.get("logo") and not existing["logo"]:
                    existing["logo"] = ch.get("logo")
            else:
                if country not in self.groups:
                    self.groups[country] = []

                channel_data = {
                    "name": ch.get("name", ""),
                    "display_name": self.clean_name(ch.get("name", "")),
                    "group": country,
                    "logo": ch.get("logo", ""),
                    "url": "",
                    "hls": ch.get("url", ""),
                }
                self.groups[country].append(channel_data)

    def clean_name(self, name):
        """Clean channel name"""
        patterns = [
            r" (AUSTRIA|AT|HEVC|RAW|SD|HD|FHD|UHD|H265|GERMANY|DEUTSCHLAND|1080|DE|S-ANHALT|SACHSEN|MATCH TIME)",
            r"(\+)",
            r" \(BACKUP\)",
            r"\(BACKUP\)",
            r" \([\w ]+\)",
            r"\([\d+]\)",
            r" (4K|\.b|\.c|\.s|\[.*]|\|.*)",
        ]

        result = name
        for pattern in patterns:
            result = re.sub(pattern, "", result)

        return result.strip()

    def categorize_channel(self, name, group):
        """Categorize channel into subgroups"""
        if group != "Germany":
            return group

        matches1 = [
            "13TH",
            "AXN",
            "A&E",
            "INVESTIGATION",
            "TNT",
            "DISNEY",
            "SKY",
            "WARNER",
        ]
        matches2 = ["BUNDESLIGA", "SPORT", "TELEKOM"]
        matches3 = ["CINE", "EAGLE", "KINO", "FILMAX", "POPCORN"]

        if any(x in name.upper() for x in matches1):
            return "Sky"
        if any(x in name.upper() for x in matches2):
            return "Sport"
        if any(x in name.upper() for x in matches3):
            return "Cine"

        return group

    def generate_m3u8(self):
        """Generate M3U8 playlist files"""
        print("Generating M3U8 files...")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for country, channels in self.groups.items():
            if not channels:
                continue

            filename = re.sub(r"[^\w\-_\.]", "_", country)
            filepath = os.path.join(OUTPUT_DIR, f"{filename}.m3u8")

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"#EXTM3U\n")
                f.write(f"# Generated: {timestamp}\n")
                f.write(f"# Source: vavoo.to\n\n")

                # Sort channels by name
                sorted_channels = sorted(channels, key=lambda x: x["name"])

                for ch in sorted_channels:
                    group = self.categorize_channel(ch["name"], country)

                    # Add first URL (live2)
                    if ch["url"]:
                        extinf = (
                            f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{group}"'
                        )
                        if ch["logo"]:
                            extinf += f' tvg-logo="{ch["logo"]}"'
                        extinf += f",{ch['display_name']}"

                        f.write(extinf + "\n")
                        f.write(f"#EXTVLCOPT:http-user-agent=VAVOO/2.6\n")
                        f.write(f"{ch['url']}\n\n")

                    # Add second URL (vavoo-iptv) if different
                    if ch["hls"] and ch["hls"] != ch["url"]:
                        extinf = (
                            f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{group}"'
                        )
                        if ch["logo"]:
                            extinf += f' tvg-logo="{ch["logo"]}"'
                        extinf += f",{ch['display_name']}"

                        f.write(extinf + "\n")
                        f.write(f"#EXTVLCOPT:http-user-agent=VAVOO/2.6\n")
                        f.write(f"{ch['hls']}\n\n")

            print(f"Created: {filepath} ({len(channels)} channels)")

    def save_json(self):
        """Save channels as JSON for tracking changes"""
        filepath = os.path.join(OUTPUT_DIR, "channels.json")

        data = {
            "updated": datetime.now().isoformat(),
            "total_channels": sum(len(ch) for ch in self.groups.values()),
            "total_groups": len(self.groups),
            "groups": self.groups,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Saved JSON: {filepath}")

    def run(self):
        """Main execution"""
        print("=" * 60)
        print("Vavoo.to M3U8 Scraper")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # Get signatures
        print("\n[1/5] Getting authentication signatures...")
        self.auth_token = self.get_auth_signature()
        self.watched_sig = self.get_watched_signature()

        if not self.auth_token and not self.watched_sig:
            print("Warning: Could not get authentication tokens, continuing anyway...")

        # Fetch channels
        print("\n[2/5] Fetching live channels...")
        live_channels = self.fetch_live_channels()

        print("\n[3/5] Fetching API channels...")
        api_channels = self.fetch_api_channels()

        # Process
        print("\n[4/5] Processing channels...")
        self.process_channels(live_channels, api_channels)

        print(f"\nTotal groups: {len(self.groups)}")
        print(f"Total channels: {sum(len(ch) for ch in self.groups.values())}")

        # Generate outputs
        print("\n[5/5] Generating output files...")
        self.generate_m3u8()
        self.save_json()

        # Track changes
        print("\n[6/6] Tracking changes...")
        try:
            from tracker import (
                load_previous_channels,
                compare_channels,
                save_history,
                print_diff,
            )

            old_data = load_previous_channels()
            diff = compare_channels(old_data, self.groups)
            print_diff(diff)
            save_history(diff)

            # Save diff report
            diff_file = os.path.join(OUTPUT_DIR, "diff_report.json")
            with open(diff_file, "w", encoding="utf-8") as f:
                json.dump(diff, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Tracker error (non-critical): {e}")

        print("\n" + "=" * 60)
        print("Done!")
        print("=" * 60)


if __name__ == "__main__":
    scraper = VavooScraper()
    scraper.run()
