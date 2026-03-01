#!/usr/bin/env python3
"""
Check IGDB/Twitch auth: get token, then call IGDB genres endpoint.
Run from project root with env vars set: TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET.

  python scripts/check_igdb_auth.py

If you see 403 on IGDB, try: 2FA enabled on Twitch, app type Confidential, correct Client ID/Secret.
"""

import os
import sys

# Add project root so app.clients can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main() -> None:
    client_id = os.environ.get("TWITCH_CLIENT_ID") or os.environ.get("IGDB_CLIENT_ID")
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET") or os.environ.get("IGDB_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET (or IGDB_*).")
        sys.exit(1)
    print("Getting Twitch token...")
    from app.clients.igdb_client import IGDBClient
    client = IGDBClient(client_id=client_id, client_secret=client_secret)
    try:
        token = client.get_token()
        print(f"Token obtained (length {len(token)})")
    except Exception as e:
        print(f"Token failed: {e}")
        sys.exit(1)
    print("Calling IGDB /genres...")
    try:
        genre_map = client.get_genre_map()
        print(f"Genres: {len(genre_map)} entries")
    except Exception as e:
        print(f"IGDB genres failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"  Status: {e.response.status_code}")
            print(f"  Body: {e.response.text[:500]}")
        sys.exit(1)
    print("OK")

if __name__ == "__main__":
    main()
