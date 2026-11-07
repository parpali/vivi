#!/usr/bin/env python3
"""
Vavoo.to M3U8 Scraper
Otomatik kanal çekme ve M3U8 playlist oluşturma
"""

import json
import os
import random
import re
import sys
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

# Disable SSL warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Constants
BASEURL = "https://www2.vavoo.to/ccapi/"
VAVOO_API_URL = "https://vavoo.to/mediahubmx-catalog.json"
VAVOO_RESOLVE_URL = "https://vavoo.to/mediahubmx-resolve.json"
PING_URL = "https://www.vavoo.tv/api/box/ping2"
LOKKE_URL = "https://www.lokke.app/api/app/ping"
VEC_URL = "http://mastaaa1987.github.io/repo/veclist.json"

# Fallback groups if the catalog is unreachable
FALLBACK_GROUPS = [
    "Albania",
    "Arabia",
    "Balkans",
    "Bulgaria",
    "Croatia",
    "France",
    "France Sport",
    "Germany",
    "Italy",
    "Netherlands",
    "Poland",
    "Portugal",
    "Romania",
    "Russia",
    "Spain",
    "Turkey",
    "United Kingdom",
]

# How many streams to resolve in parallel
RESOLVE_WORKERS = int(os.environ.get("RESOLVE_WORKERS", "8"))

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
        self._local = threading.local()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def get_veclist(self):
        """Get vector list for auth"""
        try:
            response = self.session.get(VEC_URL, timeout=30)
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

        for _ in range(50):
            try:
                vec = {"vec": random.choice(veclist)}
                response = self.session.post(PING_URL, data=vec, timeout=10)
                data = response.json()

                if data.get("signed"):
                    return data["signed"]
                if data.get("data", {}).get("signed"):
                    return data["data"]["signed"]
                if data.get("response", {}).get("signed"):
                    return data["response"]["signed"]
            except Exception:
                continue

        print("Could not get auth signature from vavoo.tv")
        return None

    def get_watched_signature(self):
        """Get watched signature from lokke.app (fallback only)"""
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

    def get_mediahub_headers(self):
        """Build auth headers for catalog and resolve endpoints.

        The mediahubmx endpoints accept the signature returned by
        vavoo.tv/api/box/ping2 ("signed"). The lokke.app addon signature is
        kept only as a fallback because the catalog rejects it now.
        """
        sig = self.auth_token or self.watched_sig
        if not sig:
            return None

        return {
            "accept-encoding": "gzip",
            "user-agent": "MediaHubMX/2",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "mediahubmx-signature": sig,
        }

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------
    def get_groups(self):
        """Get available channel groups from the vavoo catalog"""
        headers = self.get_mediahub_headers()
        if not headers:
            print("No auth signature available, using fallback groups")
            return FALLBACK_GROUPS

        data = {
            "language": "de",
            "region": "AT",
            "catalogId": "iptv",
            "id": "iptv",
            "adult": False,
            "search": "",
            "sort": "name",
            "filter": {"group": ""},
            "cursor": 0,
            "clientVersion": "3.0.2",
        }

        try:
            response = self.session.post(
                VAVOO_API_URL, json=data, headers=headers, timeout=30
            )
            result = response.json()
            filter_data = result.get("features", {}).get("filter", [])
            if filter_data:
                groups = [v for v in filter_data[0].get("values", []) if v]
                if groups:
                    return groups
        except Exception as e:
            print(f"Error fetching groups: {e}")

        return FALLBACK_GROUPS

    def fetch_api_channels(self):
        """Fetch every channel from the vavoo catalog"""
        print("Fetching channels from vavoo API...")

        headers = self.get_mediahub_headers()
        if not headers:
            print("Could not get a valid mediahubmx signature")
            return []

        all_channels = []
        seen_ids = set()
        groups = self.get_groups()

        for group in groups:
            print(f"Fetching channels for group: {group}")
            cursor = 0
            page = 0

            while page < 100:
                page += 1
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

                    if result.get("error"):
                        print(f"API error for {group}: {result.get('error')}")
                        break

                    for item in result.get("items", []):
                        if "LUXEMBOURG" in item.get("name", "") and group == "Germany":
                            continue

                        item_id = (item.get("ids") or {}).get("id") or item.get("url")
                        if item_id and item_id in seen_ids:
                            continue
                        if item_id:
                            seen_ids.add(item_id)
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

    # ------------------------------------------------------------------
    # Stream resolution
    # ------------------------------------------------------------------
    def _worker_session(self):
        """One requests session per worker thread"""
        if not hasattr(self._local, "session"):
            session = requests.Session()
            session.headers.update(self.session.headers)
            self._local.session = session
        return self._local.session

    def _resolve_one(self, item, headers):
        """Resolve a catalog item to a direct stream URL"""
        body = {
            "language": "de",
            "region": "AT",
            "catalogId": "iptv",
            "id": "iptv",
            "clientVersion": "3.0.2",
            "url": item.get("url", ""),
            "type": item.get("type", "iptv"),
            "ids": item.get("ids", {}),
        }

        for _ in range(2):
            try:
                response = self._worker_session().post(
                    VAVOO_RESOLVE_URL, json=body, headers=headers, timeout=25
                )
                data = response.json()

                if isinstance(data, list) and data:
                    url = data[0].get("url")
                    if url:
                        return url
                elif isinstance(data, dict) and data.get("url"):
                    return data["url"]
            except Exception:
                continue

        return None

    def resolve_streams(self, channels):
        """Resolve every channel to a direct playable URL"""
        print("Resolving stream URLs...")
        headers = self.get_mediahub_headers()
        if not headers:
            return []

        resolved_channels = []
        resolved = 0

        with ThreadPoolExecutor(max_workers=RESOLVE_WORKERS) as executor:
            futures = {
                executor.submit(self._resolve_one, ch, headers): ch for ch in channels
            }

            for done, future in enumerate(as_completed(futures), 1):
                channel = futures[future]
                url = future.result()

                if url:
                    channel["resolved_url"] = url
                    resolved_channels.append(channel)
                    resolved += 1

                if done % 500 == 0:
                    print(f"  resolved {done}/{len(channels)}")

        print(f"Resolved {resolved}/{len(channels)} streams")
        return resolved_channels

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def process_channels(self, channels):
        """Group resolved channels by their group name"""
        print("Processing channels...")

        for ch in channels:
            url = ch.get("resolved_url")
            if not url:
                continue

            country = ch.get("group") or "Unknown"
            name = ch.get("name", "")

            self.groups.setdefault(country, []).append(
                {
                    "name": name,
                    "display_name": self.clean_name(name),
                    "group": country,
                    "logo": ch.get("logo", ""),
                    "url": ch.get("url", ""),
                    "hls": url,
                }
            )

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

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    def clean_output(self):
        """Remove old playlists so removed/renamed groups leave no stale files.

        This also prevents files that differ only by case (Germany.m3u8 vs
        GERMANY.m3u8) from breaking the GitHub release upload.
        """
        removed = 0
        for name in os.listdir(OUTPUT_DIR):
            if name.lower().endswith(".m3u8"):
                os.remove(os.path.join(OUTPUT_DIR, name))
                removed += 1
        if removed:
            print(f"Removed {removed} old playlist(s)")

    def count_playable(self):
        """Number of channels that have a stream URL"""
        return sum(
            1 for channels in self.groups.values() for ch in channels if ch.get("hls")
        )

    def generate_m3u8(self):
        """Generate M3U8 playlist files"""
        print("Generating M3U8 files...")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_written = 0

        for country, channels in self.groups.items():
            if not channels:
                continue

            filename = re.sub(r"[^\w\-_\.]", "_", country)
            filepath = os.path.join(OUTPUT_DIR, f"{filename}.m3u8")
            written_channels = 0
            skipped_channels = 0

            lines = [
                "#EXTM3U",
                f"# Generated: {timestamp}",
                "# Source: vavoo.to catalog (resolved streams)",
                "",
            ]

            for ch in sorted(channels, key=lambda x: x["name"]):
                group = self.categorize_channel(ch["name"], country)
                raw_url = ch.get("hls")

                if not raw_url:
                    skipped_channels += 1
                    continue

                extinf = f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{group}"'
                if ch["logo"]:
                    extinf += f' tvg-logo="{ch["logo"]}"'
                extinf += f",{ch['display_name']}"

                lines.append(extinf)
                lines.append("#EXTVLCOPT:http-user-agent=VAVOO/2.6")
                lines.append(raw_url)
                lines.append("")
                written_channels += 1

            # Do not publish an empty playlist
            if written_channels == 0:
                print(f"Skipped: {filepath} (no playable channels)")
                continue

            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            total_written += written_channels
            print(
                f"Created: {filepath} ({written_channels} playable, {skipped_channels} skipped)"
            )

        return total_written

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

    # ------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------
    def run(self):
        """Main execution"""
        print("=" * 60)
        print("Vavoo.to M3U8 Scraper")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # Get signature
        print("\n[1/5] Getting authentication signature...")
        for attempt in range(1, 4):
            self.auth_token = self.get_auth_signature()
            if self.auth_token:
                break
            print(f"Auth signature attempt {attempt}/3 failed, retrying...")

        if not self.auth_token:
            # lokke signature is only a fallback; the catalog often rejects it
            self.watched_sig = self.get_watched_signature()

        if self.auth_token:
            print("Got vavoo.tv auth signature")
        elif self.watched_sig:
            print("Using lokke.app signature (fallback)")
        else:
            print("ERROR: Could not get authentication tokens")
            sys.exit(1)

        # Fetch channels
        print("\n[2/5] Fetching channels...")
        api_channels = self.fetch_api_channels()
        if not api_channels:
            print("\nERROR: No channels returned by the catalog, aborting")
            sys.exit(1)

        # Resolve direct stream URLs
        print("\n[3/5] Resolving streams...")
        resolved = self.resolve_streams(api_channels)
        if not resolved:
            print("\nERROR: No streams could be resolved, aborting")
            sys.exit(1)

        # Group channels
        print("\n[4/5] Processing channels...")
        self.process_channels(resolved)

        total_channels = sum(len(ch) for ch in self.groups.values())
        playable = self.count_playable()
        print(f"\nTotal groups: {len(self.groups)}")
        print(f"Total channels: {total_channels}")
        print(f"Playable channels: {playable}")

        # Never overwrite working playlists with an empty result
        if playable == 0:
            print("\nERROR: No playable channels found, aborting")
            sys.exit(1)

        # Load the previous channel list before channels.json is overwritten
        old_data = None
        tracker_available = False
        try:
            from tracker import (
                compare_channels,
                load_previous_channels,
                print_diff,
                save_history,
            )

            old_data = load_previous_channels()
            tracker_available = True
        except Exception as e:
            print(f"Tracker import error (non-critical): {e}")

        # Generate outputs
        print("\n[5/5] Generating output files...")
        self.clean_output()
        written = self.generate_m3u8()
        if written == 0:
            print("\nERROR: No playlist files were written, aborting")
            sys.exit(1)
        self.save_json()

        # Track changes
        print("\n[6/6] Tracking changes...")
        if tracker_available:
            try:
                diff = compare_channels(old_data, self.groups)
                print_diff(diff)
                save_history(diff)

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
