"""Resume ranking client, v2. Works with api_v1.py's POST /rank-resumes.

Improvements over client.py:
  * unique result names (relative paths), so same-named files in different folders don't collide
  * sends files in batches and skips files the server would reject (size / type)
  * only a batch's files are open at a time
  * failures are counted separately from analyzed files
  * request timeouts, CLI options, optional recursive search, CSV export
"""
import argparse
import csv
import json
import os
import sys
import time

import requests

MAX_FILE_SIZE = 5 * 1024 * 1024  # must match the server
SUPPORTED = (".pdf", ".docx", ".jpg", ".jpeg", ".png")
DEFAULT_FOLDERS = ["./INFORMATION-TECHNOLOGY", "./Resume", "./ENGINEERING"]


def collect_files(folders, recursive=False):
    """Return (files, skipped). files: list of (label, path); label is unique per path."""
    files, skipped, seen = [], [], set()
    for folder in folders:
        if not os.path.isdir(folder):
            skipped.append((folder, "folder not found"))
            continue
        walker = os.walk(folder) if recursive else [(folder, [], os.listdir(folder))]
        for root, _, names in walker:
            for name in sorted(names):
                path = os.path.abspath(os.path.join(root, name))
                if not os.path.isfile(path) or path in seen:
                    continue
                if not name.lower().endswith(SUPPORTED):
                    continue
                seen.add(path)
                if os.path.getsize(path) > MAX_FILE_SIZE:
                    skipped.append((path, "larger than 5MB"))
                    continue
                try:
                    label = os.path.relpath(path)
                except ValueError:  # different drive on Windows
                    label = path
                files.append((label.replace("\\", "/"), path))
    return files, skipped


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def rank(results):
    ok = [r for r in results if r.get("status") == "success"]
    return sorted(ok, key=lambda r: (-r["score"], r["filename"]))


def write_csv(path, results):
    ranked = rank(results)
    failed = [r for r in results if r.get("status") != "success"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "filename", "score", "matched_skills", "time_taken_sec", "status", "error"])
        for i, r in enumerate(ranked, 1):
            w.writerow([i, r["filename"], r["score"], "; ".join(r["matched_skills"]),
                        r["time_taken_sec"], "success", ""])
        for r in failed:
            w.writerow(["", r["filename"], "", "", "", r.get("status", "error"), r.get("error", "")])


def send_batch(url, keywords, batch, timeout, session=requests, api_key=None):
    """Upload one batch; yield result dicts as they stream in. Files are closed afterwards."""
    handles = [(label, open(path, "rb")) for label, path in batch]
    try:
        files = [("files", (label, fh)) for label, fh in handles]
        with session.post(url, data={"skills": keywords}, files=files,
                          stream=True, timeout=timeout,
                          headers={"X-API-Key": api_key} if api_key else None) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"server returned {resp.status_code}: {resp.text[:200]}")
            for line in resp.iter_lines():
                if line:
                    yield json.loads(line.decode("utf-8"))
    finally:
        for _, fh in handles:
            fh.close()


def print_row(r):
    name = r["filename"][-40:]
    if r.get("status") != "success":
        print(f"{name:<40} | {'ERR':<5} | {'-':<8} | {r.get('error', '')}")
    else:
        print(f"{name:<40} | {r['score']:<5} | {r['time_taken_sec']:<8} | {', '.join(r['matched_skills'])}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Rank resumes against keywords using the resume parser API.")
    p.add_argument("-k", "--keywords", help="comma-separated keywords (prompted if omitted)")
    p.add_argument("-f", "--folders", nargs="+", default=DEFAULT_FOLDERS, help="folders containing resumes")
    p.add_argument("-r", "--recursive", action="store_true", help="include subfolders")
    p.add_argument("--url", default="http://127.0.0.1:8000/rank-resumes")
    p.add_argument("--batch-size", type=int, default=50, help="files per request (server max is 300)")
    p.add_argument("--timeout", type=float, default=300, help="seconds to wait for server data")
    p.add_argument("--top", type=int, default=10, help="how many ranked results to print")
    p.add_argument("-o", "--output", help="write full ranking to this CSV file")
    p.add_argument("--api-key", default=os.getenv("RESUME_API_KEY"), help="API key for api_v2 (or set RESUME_API_KEY)")
    p.add_argument("--no-pause", action="store_true", help="don't wait for Enter at the end")
    return p.parse_args(argv)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    args.batch_size = max(1, min(args.batch_size, 300))

    keywords = (args.keywords if args.keywords is not None
                else input("Enter keywords (comma-separated): ")).strip()
    if not keywords.replace(",", "").strip():
        print("Error: you must enter at least one keyword.")
        return 1

    files, skipped = collect_files(args.folders, args.recursive)
    for item, why in skipped:
        print(f"Warning: skipped {item} ({why})")
    if not files:
        print(f"No valid resumes found in: {args.folders}")
        return 1

    print(f"\nFound {len(files)} resumes. Sending in batches of {args.batch_size}...")
    print("=" * 90)
    print(f"{'FILENAME':<40} | {'SCORE':<5} | {'TIME(s)':<8} | MATCHED SKILLS")
    print("-" * 90)

    results, start = [], time.time()
    try:
        for batch in chunked(files, args.batch_size):
            for r in send_batch(args.url, keywords, batch, (5, args.timeout), api_key=args.api_key):
                results.append(r)
                print_row(r)
    except requests.exceptions.ConnectionError:
        print(f"\nCould not connect to {args.url}. Is the server running?")
    except (requests.exceptions.Timeout, RuntimeError) as e:
        print(f"\nRequest failed: {e}")

    ok = rank(results)
    failed = len(results) - len(ok)
    unreturned = len(files) - len(results)
    print("-" * 90)
    print(f"Done in {time.time() - start:.1f}s: {len(ok)} analyzed, {failed} failed, "
          f"{unreturned} not processed, {len(skipped)} skipped")

    if ok:
        print(f"\nTOP {min(args.top, len(ok))} RANKING:")
        for i, r in enumerate(ok[:args.top], 1):
            print(f"{i:<5} | {r['score']:<5} | {r['filename']}")
    if args.output and results:
        write_csv(args.output, results)
        print(f"\nFull results written to {args.output}")

    if not args.no_pause and sys.stdin.isatty():
        input("\nPress Enter to exit...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
