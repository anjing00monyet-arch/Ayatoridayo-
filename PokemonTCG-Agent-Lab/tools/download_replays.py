"""Download Kaggle simulation-competition episode replays by episode ID.

Uses the public (undocumented but widely used across Kaggle simulation
competitions) EpisodeService endpoint:

    POST https://www.kaggle.com/api/i/competitions.EpisodeService/GetEpisodeReplay
    body: {"EpisodeId": <int>}

This has NOT been exercised against this specific competition from this
sandbox (no network access here to verify), so treat the response-shape
assumptions below as a starting point to adjust, not a guarantee. Get episode
IDs from the competition's leaderboard / episodes list on kaggle.com first --
this script only fetches replays for IDs you already have.

    python download_replays.py 89558380 89558402 89558932 -o replays/
    python download_replays.py --ids-file top_episode_ids.txt -o replays/
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://www.kaggle.com/api/i/competitions.EpisodeService/GetEpisodeReplay"


def fetch_episode(episode_id: int, *, timeout: float = 30.0) -> dict:
    payload = json.dumps({"EpisodeId": episode_id}).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if "result" not in body:
        raise RuntimeError(f"unexpected response shape for episode {episode_id}: {list(body)}")
    return body["result"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode_ids", nargs="*", type=int)
    parser.add_argument("--ids-file", type=Path, help="text file, one episode ID per line")
    parser.add_argument("-o", "--out", type=Path, default=Path("replays"))
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    args = parser.parse_args()

    ids = list(args.episode_ids)
    if args.ids_file:
        ids += [int(line.strip()) for line in args.ids_file.read_text().splitlines() if line.strip()]
    if not ids:
        parser.error("give at least one episode ID, positionally or via --ids-file")

    args.out.mkdir(parents=True, exist_ok=True)
    ok, failed = 0, []
    for i, episode_id in enumerate(ids):
        target = args.out / f"episode-{episode_id}.json"
        if target.exists():
            print(f"[skip] {target} already exists")
            ok += 1
            continue
        try:
            result = fetch_episode(episode_id)
        except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
            print(f"[FAIL] episode {episode_id}: {exc}", file=sys.stderr)
            failed.append(episode_id)
            continue
        target.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] wrote {target}")
        ok += 1
        if i < len(ids) - 1:
            time.sleep(args.delay)

    print(f"\n{ok}/{len(ids)} downloaded, {len(failed)} failed: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
