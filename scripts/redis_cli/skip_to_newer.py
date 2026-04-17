"""
Skip the background queue consumer group to newer articles based on created_at.

Uses XGROUP SETID to advance the consumer group pointer — no messages are deleted,
no XREADGROUP is used. Old messages remain in the stream but won't be delivered.

Usage:
    # Dry run — skip background:to.be.scraped to articles from the last 3 days
    python -m scripts.redis_cli.skip_to_newer --stream background:to.be.scraped --days 3

    # Actually apply the skip
    python -m scripts.redis_cli.skip_to_newer --stream background:to.be.scraped --days 3 --apply

    # Skip to a specific date
    python -m scripts.redis_cli.skip_to_newer --stream background:to.be.scraped --cutoff 2026-04-10 --apply

    # Also trim (physically delete) old messages
    python -m scripts.redis_cli.skip_to_newer --stream background:to.be.scraped --days 3 --apply --trim
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import redis


def get_redis_connection() -> redis.Redis:
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "16379"))
    use_ssl = os.getenv("REDIS_SSL", "true").lower() == "true"

    kwargs = dict(
        host=host,
        port=port,
        decode_responses=True,
        socket_timeout=30,
        retry_on_timeout=True,
    )
    if use_ssl:
        kwargs["ssl"] = True
        kwargs["ssl_cert_reqs"] = "none"

    return redis.Redis(**kwargs)


def parse_created_at(value: str) -> datetime:
    """Parse created_at string to timezone-aware datetime."""
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ]:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse created_at: {value}")


def find_cutoff_id(
    r: redis.Redis, stream: str, cutoff: datetime
) -> tuple[str | None, int, int]:
    """
    Binary search the stream for the first message with created_at >= cutoff.
    Returns (redis_id_just_before, skip_count, keep_count).
    """
    entries = r.xrange(stream)
    total = len(entries)
    if total == 0:
        return None, 0, 0

    lo, hi = 0, total - 1
    result_idx = total  # default: skip everything

    while lo <= hi:
        mid = (lo + hi) // 2
        _, data = entries[mid]
        payload = json.loads(data.get("payload", "{}"))
        ca_str = payload.get("header", {}).get("created_at", "")
        if not ca_str:
            lo = mid + 1
            continue
        ca = parse_created_at(ca_str)
        if ca >= cutoff:
            result_idx = mid
            hi = mid - 1
        else:
            lo = mid + 1

    if result_idx == 0:
        # All messages are newer than cutoff — nothing to skip
        return None, 0, total

    if result_idx >= total:
        # All messages are older than cutoff
        last_id = entries[-1][0]
        return last_id, total, 0

    # The ID just before the first "kept" message
    skip_id = entries[result_idx - 1][0]
    return skip_id, result_idx, total - result_idx


def main():
    parser = argparse.ArgumentParser(description="Skip background queue to newer articles")
    parser.add_argument("--stream", required=True, help="Stream name, e.g. background:to.be.scraped")
    parser.add_argument("--group", default="default", help="Consumer group name (default: 'default')")
    parser.add_argument("--days", type=float, help="Keep articles from the last N days")
    parser.add_argument("--cutoff", help="Keep articles with created_at >= this date (YYYY-MM-DD or ISO)")
    parser.add_argument("--apply", action="store_true", help="Actually apply the change (default is dry-run)")
    parser.add_argument("--trim", action="store_true", help="Also XTRIM old messages (destructive)")
    args = parser.parse_args()

    if not args.days and not args.cutoff:
        parser.error("Specify either --days or --cutoff")

    if args.cutoff:
        cutoff_str = args.cutoff
        if "T" not in cutoff_str:
            cutoff_str += "T00:00:00"
        cutoff = parse_created_at(cutoff_str)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    print(f"Cutoff: {cutoff.isoformat()}")
    print(f"Stream: {args.stream}")
    print(f"Group:  {args.group}")
    print()

    r = get_redis_connection()

    # Current state
    length = r.xlen(args.stream)
    groups = r.xinfo_groups(args.stream)
    current_group = next((g for g in groups if g["name"] == args.group), None)
    if not current_group:
        print(f"ERROR: Consumer group '{args.group}' not found on stream '{args.stream}'")
        print(f"Available groups: {[g['name'] for g in groups]}")
        sys.exit(1)

    current_last_delivered = current_group["last-delivered-id"]
    pending = current_group["pending"]
    print(f"Current state:")
    print(f"  Stream length:   {length}")
    print(f"  Last delivered:  {current_last_delivered}")
    print(f"  Pending (unack): {pending}")
    print()

    # Find the skip point
    skip_id, skip_count, keep_count = find_cutoff_id(r, args.stream, cutoff)

    if skip_id is None:
        print("Nothing to skip — all messages are already newer than the cutoff.")
        sys.exit(0)

    print(f"Skip plan:")
    print(f"  Will skip:  {skip_count} messages")
    print(f"  Will keep:  {keep_count} messages")
    print(f"  New last-delivered-id: {skip_id}")
    print()

    if not args.apply:
        print("DRY RUN — no changes made. Add --apply to execute.")
        print(f"\nTo apply manually:")
        print(f"  XGROUP SETID {args.stream} {args.group} {skip_id}")
        if args.trim:
            # MINID would be the first kept message's ID
            print(f"  XTRIM {args.stream} MINID ~ {skip_id}")
        sys.exit(0)

    # Apply XGROUP SETID
    r.xgroup_setid(args.stream, args.group, skip_id)
    print(f"APPLIED: XGROUP SETID {args.stream} {args.group} {skip_id}")

    if args.trim:
        before = r.xlen(args.stream)
        r.xtrim(args.stream, minid=skip_id)
        after = r.xlen(args.stream)
        print(f"APPLIED: XTRIM {args.stream} MINID {skip_id}")
        print(f"  Trimmed {before - after} messages ({before} -> {after})")

    # Verify
    groups_after = r.xinfo_groups(args.stream)
    grp = next(g for g in groups_after if g["name"] == args.group)
    print(f"\nVerification:")
    print(f"  New last-delivered-id: {grp['last-delivered-id']}")
    print(f"  Stream length: {r.xlen(args.stream)}")


if __name__ == "__main__":
    main()
