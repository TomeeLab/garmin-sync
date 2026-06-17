#!/usr/bin/env python3
"""
garmin_backup.py – automatic download of FIT files from Garmin Connect
Compatible with garminconnect 0.3.5
Two modes:
  INCREMENTAL – if .garmin_last_sync exists, downloads only new activities
                (paginates until it finds an activity older than last_sync)
  BULK        – if .garmin_last_sync does not exist, paginates through ALL activities
                until Garmin returns an empty page or an activity older than
                GARMIN_LOOKBACK days
Configuration via environment variables:
  GARMIN_EMAIL     – Garmin Connect email
  GARMIN_PASSWORD  – Garmin Connect password
  GARMIN_FIT_DIR   – target directory (default: ~/garmin-fit)
  GARMIN_LOOKBACK  – days back in bulk mode (default: 3650 = ~10 years)
  GARMIN_PAGE_SIZE – activities per page (default: 100, max: 100)
"""
import os
import sys
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
try:
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectTooManyRequestsError,
    )
except ImportError:
    print("ERROR: Missing garminconnect library. Run: pip install garminconnect", file=sys.stderr)
    sys.exit(1)
# ── Configuration ─────────────────────────────────────────────────────────────
EMAIL     = os.environ.get("GARMIN_EMAIL", "")
PASSWORD  = os.environ.get("GARMIN_PASSWORD", "")
FIT_DIR   = Path(os.environ.get("GARMIN_FIT_DIR", Path.home() / "garmin-fit"))
LOOKBACK  = int(os.environ.get("GARMIN_LOOKBACK", "3650"))
PAGE_SIZE = int(os.environ.get("GARMIN_PAGE_SIZE", "100"))
SCRIPT_DIR = Path(__file__).parent
SYNC_FILE  = SCRIPT_DIR / ".garmin_last_sync"
TOKEN_DIR  = SCRIPT_DIR / ".garmin_tokens"
# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)
# ── Helper functions ──────────────────────────────────────────────────────────
def load_last_sync() -> datetime | None:
    """Returns datetime of last sync, or None on first run (bulk mode)."""
    if SYNC_FILE.exists():
        ts_str = SYNC_FILE.read_text().strip()
        try:
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            log.info(f"Last sync: {dt.isoformat()} -> incremental mode")
            return dt
        except ValueError:
            log.warning(f"Invalid format in {SYNC_FILE}, switching to bulk mode.")
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK)
    log.info(f"Bulk mode – downloading from: {cutoff.date()} (LOOKBACK={LOOKBACK} days)")
    return None
def save_last_sync(dt: datetime):
    SYNC_FILE.write_text(dt.isoformat())
def parse_activity_time(activity: dict) -> datetime | None:
    """Parses activity start time from Garmin metadata, returns UTC datetime or None."""
    start_raw = (activity.get("startTimeGMT") or activity.get("startTimeLocal", "")).replace("T", " ")
    try:
        return datetime.strptime(start_raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
def fit_path(activity: dict) -> Path:
    act_dt = parse_activity_time(activity) or datetime.now()
    activity_id = activity["activityId"]
    target_dir  = FIT_DIR / act_dt.strftime("%Y") / act_dt.strftime("%m")
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{act_dt.strftime('%Y-%m-%d')}_{activity_id}.fit"
def login() -> Garmin:
    if not EMAIL or not PASSWORD:
        log.error("Missing GARMIN_EMAIL or GARMIN_PASSWORD!")
        sys.exit(1)
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    client = Garmin(email=EMAIL, password=PASSWORD, is_cn=False)
    try:
        # tokenstore = directory where garth stores/loads session tokens.
        # On subsequent runs tokens are reused – avoids repeated logins and 429 rate limits.
        # Tokens are valid for ~1 year. Delete TOKEN_DIR to force a fresh login.
        client.login(tokenstore=str(TOKEN_DIR))
        log.info("Login successful.")
        return client
    except GarminConnectAuthenticationError as e:
        log.error(f"Authentication failed: {e}")
        sys.exit(1)
    except GarminConnectTooManyRequestsError:
        log.error("Rate limit (429) – IP is temporarily blocked by Garmin. Wait 1-2 hours and retry.")
        sys.exit(2)
    except Exception as e:
        if "429" in str(e):
            log.error("Rate limit (429) – wait 1-2 hours before retrying.")
            sys.exit(2)
        log.error(f"Unexpected error during login: {e}")
        sys.exit(1)
def fetch_activities(client: Garmin, cutoff: datetime | None) -> list[dict]:
    """
    Downloads activity list using pagination.
    Incremental mode (cutoff != None):
      Paginates until it finds an activity older than cutoff or an empty page.
    Bulk mode (cutoff == None):
      Uses LOOKBACK as cutoff. Paginates through all activities from newest
      to oldest until it hits an activity older than cutoff or an empty page.
    """
    if cutoff is None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK)
    all_activities = []
    start         = 0
    page          = 1
    while True:
        log.info(f"  Fetching page {page} (offset {start}, limit {PAGE_SIZE})...")
        try:
            batch = client.get_activities(start, PAGE_SIZE)
        except GarminConnectTooManyRequestsError:
            log.error("Rate limit while fetching activity list.")
            sys.exit(2)
        except Exception as e:
            log.error(f"Error fetching activities (page {page}): {e}")
            break
        if not batch:
            log.info("  Empty page – end of activity list.")
            break
        stop = False
        for act in batch:
            act_dt = parse_activity_time(act)
            if act_dt is None:
                continue
            if act_dt <= cutoff:
                log.info(f"  Reached cutoff ({cutoff.date()}), stopping pagination.")
                stop = True
                break
            all_activities.append(act)
        if stop:
            break
        if len(batch) < PAGE_SIZE:
            log.info("  Last page.")
            break
        start += PAGE_SIZE
        page  += 1
        time.sleep(1)
    return all_activities
def download_fit(client: Garmin, activity: dict) -> bytes | None:
    """Downloads FIT file for an activity, retries once on rate limit."""
    activity_id = activity["activityId"]
    try:
        return client.download_activity(
            activity_id,
            dl_fmt=client.ActivityDownloadFormat.ORIGINAL
        )
    except GarminConnectTooManyRequestsError:
        log.warning("  Rate limit, waiting 60s...")
        time.sleep(60)
        try:
            return client.download_activity(
                activity_id,
                dl_fmt=client.ActivityDownloadFormat.ORIGINAL
            )
        except Exception as e2:
            log.error(f"  ERROR after retry [{activity_id}]: {e2}")
            return None
    except Exception as e:
        log.error(f"  ERROR [{activity_id}]: {e}")
        return None
# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("=== Garmin FIT Backup START ===")
    FIT_DIR.mkdir(parents=True, exist_ok=True)
    last_sync = load_last_sync()  # None = bulk mode
    client = login()
    log.info("Fetching activity list (paginated)...")
    activities = fetch_activities(client, last_sync)
    log.info(f"Total activities to process: {len(activities)}")
    if not activities:
        log.info("No new activities – last_sync unchanged.")
        return
    # Sort oldest-first so that if interrupted, newer ones are retried next run
    activities.sort(key=lambda a: parse_activity_time(a) or datetime.min.replace(tzinfo=timezone.utc))
    downloaded = skipped = errors = 0
    # last_sync is advanced to the startTimeGMT of the newest successfully
    # processed activity – NOT to now(). This prevents skipping activities
    # that were uploaded to Garmin Connect after the script ran (e.g. delayed
    # watch sync). Failed downloads do not advance last_sync so they are
    # retried on the next run.
    newest_processed_dt: datetime | None = None
    for activity in activities:
        activity_id   = activity["activityId"]
        activity_name = activity.get("activityName", "unknown")
        activity_type = activity.get("activityType", {}).get("typeKey", "unknown")
        target_path   = fit_path(activity)
        if target_path.exists():
            log.info(f"  SKIP  [{activity_id}] {activity_name} – already exists")
            skipped += 1
            # File already on disk – advance last_sync past this activity
            act_dt = parse_activity_time(activity)
            if act_dt and (newest_processed_dt is None or act_dt > newest_processed_dt):
                newest_processed_dt = act_dt
            continue
        log.info(f"  DL    [{activity_id}] {activity_name} ({activity_type})")
        fit_data = download_fit(client, activity)
        if fit_data is None:
            errors += 1
            # Download failed – do NOT advance last_sync so this activity
            # is retried on the next run
            continue
        if len(fit_data) == 0:
            log.warning(f"  NO FIT [{activity_id}] – no FIT file available (manually entered?)")
            skipped += 1
            # No FIT data but activity exists on GC – advance last_sync
            act_dt = parse_activity_time(activity)
            if act_dt and (newest_processed_dt is None or act_dt > newest_processed_dt):
                newest_processed_dt = act_dt
            continue
        target_path.write_bytes(fit_data)
        log.info(f"  OK    {target_path} ({len(fit_data)/1024:.1f} kB)")
        downloaded += 1
        act_dt = parse_activity_time(activity)
        if act_dt and (newest_processed_dt is None or act_dt > newest_processed_dt):
            newest_processed_dt = act_dt
        time.sleep(2)
    if newest_processed_dt is not None:
        save_last_sync(newest_processed_dt)
        log.info(f"last_sync updated to: {newest_processed_dt.isoformat()}")
    else:
        log.info("No activity successfully processed – last_sync unchanged.")
    log.info(f"=== Done: {downloaded} downloaded, {skipped} skipped, {errors} errors ===")
if __name__ == "__main__":
    main()
