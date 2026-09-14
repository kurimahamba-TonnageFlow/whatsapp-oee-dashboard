# ==========================================================
# TONNAGEFLOW PULSE
# WhatsApp Web Observer - Phase 1 + Phase 2 (read-only)
# ==========================================================
#
# Phase 1 purpose: open web.whatsapp.com in a visible, isolated
# Playwright Chromium profile so a person can manually scan the QR
# code and keep a persistent local session across runs.
#
# Phase 2 purpose: a temporary, authorised shadow-mode trial that
# reads ONLY the single WhatsApp group named in WHATSAPP_ALLOWED_GROUP
# - and only while that exact group is already open in the browser -
# collecting messages from 06:00 Europe/London today onward into a
# local JSON Lines file, then watching for new messages. It never
# opens a chat itself, never touches Supabase, and never touches the
# Pulse CLI engine. It is a strictly separate, opt-in mode (run with
# --shadow-mode); the default `run_observer()` behaviour is unchanged.
#
# Deliberately out of scope (both phases):
#   - Sending, editing, deleting, or reacting to messages
#   - Typing into WhatsApp, opening another chat/contact, or changing
#     any WhatsApp setting
#   - Downloading media
#   - Automatically opening any group or chat
#   - Any authentication bypass or reuse of another browser's
#     existing WhatsApp session
#   - Reading any group other than the one named in
#     WHATSAPP_ALLOWED_GROUP
#
# This adapter is independent of src/main.py, src/database.py, and
# src/whatsapp_webhook.py - none of those files import from here,
# and this module does not import from them. Phase 2 does not connect
# to Supabase or the Pulse engine - it only writes to the local JSONL
# file described below.
#
# Only status-level, non-secret messages are ever printed. Message
# bodies, sender names, phone numbers, and the allow-listed group name
# are never printed - only safe counts and status strings.
#
# All WhatsApp-specific DOM knowledge lives in whatsapp_dom.py. Date/
# time resolution, filtering, and record-building are pure functions
# in whatsapp_message_parser.py. Persistence is in
# whatsapp_message_store.py. This file only wires those three
# together with a live Playwright page - keeping the DOM layer the
# only piece that would need replacing for a future tablet UI capture
# mechanism.
#
# LIVE-TEST NOTE: WhatsApp Web's DOM is unofficial and undocumented.
# The selectors in whatsapp_dom.py are a best-effort, defensive first
# pass and have not been validated against a live session in this
# environment (no live WhatsApp access here). Before relying on Phase
# 2 output, run a short controlled live test (see the --shadow-mode
# command in this file's __main__ block) against the real, already-
# logged-in "Rovema production line 1" chat, and adjust the selectors
# in whatsapp_dom.py if messages are not being captured.

import argparse
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from src.adapters import whatsapp_dom
from src.adapters.whatsapp_message_parser import (
    LONDON_TZ,
    build_message_record,
    compute_historical_boundary,
    is_before_historical_boundary,
    resolve_date_separator,
    resolve_message_datetime,
)
from src.adapters.whatsapp_message_store import WhatsAppMessageStore

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR_NAME = ".pulse_browser_profile"
SHADOW_INBOX_DIR_NAME = ".pulse_shadow_inbox"
WHATSAPP_WEB_URL = "https://web.whatsapp.com"

# Selectors used only to report connection status - never used to
# read chat list or message content.
LOGGED_IN_SELECTOR = "#pane-side"
QR_CODE_SELECTOR = "canvas"

# Best-effort, defensive selectors for Phase 2 live extraction. See
# the LIVE-TEST NOTE above - these need validating against a real
# session and may need adjusting after any WhatsApp Web UI change.
CHAT_HEADER_SELECTOR = "header"
MESSAGE_ROW_SELECTOR = "div[data-id]"
MAX_HISTORICAL_SCROLL_ITERATIONS = 500
SCROLL_PAUSE_MS = 800
WATCH_POLL_INTERVAL_MS = 2000

# Phase 2 startup: after login, the user must manually open the
# authorised group. We poll for it indefinitely by default rather
# than refusing immediately or giving up after a fixed time.
AUTHORISED_CHAT_POLL_INTERVAL_SECONDS = 2


# ==========================================================
# CONFIGURATION
# ==========================================================


def get_profile_dir(project_root: Path = PROJECT_ROOT) -> Path:
    """Resolve the persistent Playwright profile directory location."""
    return project_root / PROFILE_DIR_NAME


def get_allowed_group():
    """
    Read the allow-listed WhatsApp group name from the environment.

    Phase 1 reads and validates this only - it is not used to open
    any group automatically. A later phase can use it to restrict
    which single group may ever be opened.
    """
    return os.getenv("WHATSAPP_ALLOWED_GROUP")


def describe_configuration(project_root: Path = PROJECT_ROOT):
    """Build a safe, non-secret configuration summary for status printing."""
    return {
        "profile_dir": str(get_profile_dir(project_root)),
        "allowed_group_configured": bool(get_allowed_group()),
    }


def get_shadow_inbox_dir(project_root: Path = PROJECT_ROOT) -> Path:
    """Resolve the local Phase 2 shadow-mode inbox directory location."""
    return project_root / SHADOW_INBOX_DIR_NAME


def confirm_active_chat_matches(active_title, allowed_group):
    """
    Return True only if allowed_group is a non-empty string and
    active_title matches it exactly. Refuses (returns False) if the
    allow-listed group is missing/empty, if the active chat title is
    unknown, or if they do not match exactly - per Phase 2 item 2,
    nothing may be extracted otherwise.
    """
    if not allowed_group:
        return False

    if not active_title:
        return False

    return active_title == allowed_group


# ==========================================================
# CONNECTION STATUS (READ-ONLY)
# ==========================================================


def wait_for_connection_status(page, timeout_seconds=120):
    """
    Poll the page for a QR code or a logged-in landmark and report
    status only. Never reads chat list content or message text.
    """
    deadline = time.time() + timeout_seconds
    reported_waiting = False

    while time.time() < deadline:
        if page.locator(LOGGED_IN_SELECTOR).count() > 0:
            print("WhatsApp Web: logged in.")
            return "logged_in"

        if (
            not reported_waiting
            and page.locator(QR_CODE_SELECTOR).count() > 0
        ):
            print("WhatsApp Web: waiting for QR code scan...")
            reported_waiting = True

        page.wait_for_timeout(1000)

    print("WhatsApp Web: timed out waiting for login.")
    return "timeout"


# ==========================================================
# OBSERVER ENTRY POINT
# ==========================================================


def run_observer(timeout_seconds=120):
    configuration = describe_configuration()

    print("TonnageFlow Pulse - WhatsApp Web Observer (Phase 1, read-only)")
    print(f"Profile directory: {configuration['profile_dir']}")
    print(
        "Allowed group configured: "
        f"{configuration['allowed_group_configured']}"
    )
    print("This observer does not read, store, or send any messages.")

    profile_dir = get_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
        )

        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(WHATSAPP_WEB_URL)

            print(
                "Browser launched. Waiting for manual QR code "
                "login if required."
            )

            status = wait_for_connection_status(
                page,
                timeout_seconds=timeout_seconds,
            )

            print(f"Connection status: {status}")
            print("No messages were read, parsed, or stored.")
            print("Press Ctrl+C in this terminal to close the observer.")

            while True:
                page.wait_for_timeout(1000)

        except KeyboardInterrupt:
            print("Observer stopped by user.")

        finally:
            context.close()


# ==========================================================
# SHADOW MODE (PHASE 2, READ-ONLY, SINGLE AUTHORISED GROUP)
# ==========================================================


def get_active_chat_title(page):
    """Read the currently open chat's title via the DOM extraction layer."""
    header = page.locator(CHAT_HEADER_SELECTOR).first

    try:
        if header.count() == 0:
            return None
        header_html = header.evaluate("el => el.outerHTML")
    except Exception:
        return None

    return whatsapp_dom.extract_chat_title(header_html)


def is_authorised_chat_active(page, allowed_group):
    """
    Return True only if the currently open chat's title exactly
    matches allowed_group. Never prints or returns the title itself -
    callers must not leak it (see confirm_active_chat_matches).
    """
    return confirm_active_chat_matches(get_active_chat_title(page), allowed_group)


def wait_for_authorised_chat(
    page,
    allowed_group,
    timeout_seconds=None,
    poll_interval_seconds=AUTHORISED_CHAT_POLL_INTERVAL_SECONDS,
):
    """
    Wait for the user to manually open the authorised WhatsApp group.
    Never clicks or opens a chat itself - only polls the active chat
    title every poll_interval_seconds until it exactly matches
    allowed_group. By default (timeout_seconds=None) this waits
    indefinitely, since there is no reliable bound on how long a
    person takes to open the right group by hand; pass a finite
    timeout_seconds to bound the wait instead.

    Stops only when: the group becomes active (returns True), a
    finite timeout_seconds elapses (returns False), KeyboardInterrupt
    is raised (propagates to the caller - Ctrl+C stops the wait), or
    the browser/page is closed (a Playwright error is caught here,
    a safe status message is printed, and this returns False).

    Never prints the detected title, group name, sender, or message
    content - only generic waiting/timeout/closed status.
    """
    print("Open the authorised WhatsApp group manually. Waiting for exact match...")

    deadline = time.time() + timeout_seconds if timeout_seconds is not None else None

    try:
        while deadline is None or time.time() < deadline:
            if is_authorised_chat_active(page, allowed_group):
                return True
            page.wait_for_timeout(poll_interval_seconds * 1000)
    except PlaywrightError:
        print("Shadow mode stopped because the browser was closed.")
        return False

    print("Shadow mode: timed out waiting for the authorised group to be opened.")
    return False


def _row_outer_html(row_handle):
    try:
        return row_handle.evaluate("el => el.outerHTML")
    except Exception:
        return None


def _process_row(row_html, group_name, date_context, store):
    """
    Classify one row's HTML and either update the date context (date
    separator), append a new message record, or ignore it. Returns
    (date_context, message_datetime_or_None, appended_bool).
    """
    separator_text = whatsapp_dom.extract_date_separator_text(row_html)
    if separator_text:
        resolved = resolve_date_separator(separator_text, datetime.now(LONDON_TZ).date())
        if resolved:
            date_context = resolved
        return date_context, None, False

    raw_row = whatsapp_dom.classify_and_extract_row(row_html)
    message_datetime = resolve_message_datetime(raw_row, date_context)
    record = build_message_record(raw_row, group_name, date_context)

    appended = False
    if record is not None:
        appended = store.append_message(record)

    return date_context, message_datetime, appended


def collect_historical_messages(page, store, group_name, timeout_seconds=600):
    """
    Scroll backwards from the newest message, collecting messages from
    06:00 Europe/London today onward, stopping once a message earlier
    than that boundary is reached (or a safety limit is hit). Never
    raises - a failure stops scrolling safely, leaving whatever was
    already appended to the JSONL file intact. Prints and returns only
    safe counts.

    Re-checks the active chat title every iteration: extraction pauses
    (no reading, no scrolling) whenever the authorised group is not
    the active chat, and resumes automatically once it is again. Never
    reads or stores content from any other chat.
    """
    boundary = compute_historical_boundary(datetime.now(LONDON_TZ))
    date_context = None
    collected = 0
    reached_boundary = False
    deadline = time.time() + timeout_seconds
    authorised_active = True

    try:
        for _ in range(MAX_HISTORICAL_SCROLL_ITERATIONS):
            if time.time() > deadline:
                print("Shadow mode: historical scroll timed out safely.")
                break

            if not is_authorised_chat_active(page, group_name):
                if authorised_active:
                    print(
                        "Shadow mode: authorised group no longer active - "
                        "pausing extraction."
                    )
                    authorised_active = False
                page.wait_for_timeout(SCROLL_PAUSE_MS)
                continue

            if not authorised_active:
                print(
                    "Shadow mode: authorised group active again - "
                    "resuming extraction."
                )
                authorised_active = True

            rows = page.locator(MESSAGE_ROW_SELECTOR)

            for index in range(rows.count()):
                row_html = _row_outer_html(rows.nth(index))
                if not row_html:
                    continue

                date_context, message_datetime, appended = _process_row(
                    row_html, group_name, date_context, store
                )

                if appended:
                    collected += 1

                if message_datetime and is_before_historical_boundary(
                    message_datetime, boundary
                ):
                    reached_boundary = True

            if reached_boundary:
                print("Shadow mode: reached the 06:00 Europe/London boundary.")
                break

            page.mouse.wheel(0, -3000)
            page.wait_for_timeout(SCROLL_PAUSE_MS)

    except Exception:
        print("Shadow mode: historical scroll stopped safely after an error.")

    print(f"Shadow mode: historical collection complete. New messages saved: {collected}")
    return {"collected": collected}


def watch_new_messages(page, store, group_name):
    """
    Poll the currently open, already-validated chat for new messages
    at the bottom of the conversation and append any new ones. Runs
    until interrupted (Ctrl+C) or a failure occurs, in which case it
    stops safely without corrupting the JSONL file. Prints and returns
    only safe counts.

    Re-checks the active chat title every iteration: extraction pauses
    whenever the authorised group is not the active chat, and resumes
    automatically once it is again. Never reads or stores content from
    any other chat.
    """
    date_context = None
    collected = 0
    authorised_active = True

    print("Shadow mode: watching for new messages. Press Ctrl+C to stop.")

    try:
        while True:
            if not is_authorised_chat_active(page, group_name):
                if authorised_active:
                    print(
                        "Shadow mode: authorised group no longer active - "
                        "pausing extraction."
                    )
                    authorised_active = False
                page.wait_for_timeout(WATCH_POLL_INTERVAL_MS)
                continue

            if not authorised_active:
                print(
                    "Shadow mode: authorised group active again - "
                    "resuming extraction."
                )
                authorised_active = True

            rows = page.locator(MESSAGE_ROW_SELECTOR)

            for index in range(rows.count()):
                row_html = _row_outer_html(rows.nth(index))
                if not row_html:
                    continue

                date_context, _message_datetime, appended = _process_row(
                    row_html, group_name, date_context, store
                )

                if appended:
                    collected += 1

            page.wait_for_timeout(WATCH_POLL_INTERVAL_MS)

    except KeyboardInterrupt:
        print("Shadow mode: watch stopped by user.")

    except Exception:
        print("Shadow mode: watch stopped safely after an error.")

    print(f"Shadow mode: new messages saved while watching: {collected}")
    return {"collected": collected}


def run_shadow_observer(timeout_seconds=120, historical_timeout_seconds=600):
    """
    Phase 2 entry point. Requires WHATSAPP_ALLOWED_GROUP to be set.
    After login, keeps the browser open and waits indefinitely
    (polling every AUTHORISED_CHAT_POLL_INTERVAL_SECONDS) for the
    user to manually open the matching group before extracting
    anything. Stops only on an exact match, Ctrl+C, or the browser
    being closed. Never opens a chat itself.
    """
    allowed_group = get_allowed_group()
    configuration = describe_configuration()

    print("TonnageFlow Pulse - WhatsApp Web Observer (Phase 2, shadow mode)")
    print(f"Profile directory: {configuration['profile_dir']}")
    print(f"Shadow inbox directory: {get_shadow_inbox_dir()}")
    print(f"Allowed group configured: {configuration['allowed_group_configured']}")

    if not allowed_group:
        print("Refusing to start: WHATSAPP_ALLOWED_GROUP is not configured.")
        return

    profile_dir = get_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)

    store = WhatsAppMessageStore(get_shadow_inbox_dir())

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
        )

        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(WHATSAPP_WEB_URL)

            status = wait_for_connection_status(page, timeout_seconds=timeout_seconds)
            if status != "logged_in":
                print("Refusing to start: not logged in to WhatsApp Web.")
                return

            matched = wait_for_authorised_chat(page, allowed_group)
            if not matched:
                return

            print("Active chat confirmed to match the authorised group.")

            collect_historical_messages(
                page, store, allowed_group, timeout_seconds=historical_timeout_seconds
            )

            print(f"Known message count so far: {store.known_id_count()}")

            watch_new_messages(page, store, allowed_group)

        except KeyboardInterrupt:
            print("Shadow mode observer stopped by user.")

        finally:
            try:
                context.close()
            except PlaywrightError:
                # Already closed (e.g. the user closed the browser
                # window) - nothing left to clean up.
                pass


def build_arg_parser():
    """
    Build the CLI parser. Separated from main() so tests can inspect
    or exercise argument parsing (e.g. --help, unknown flags) without
    running the observer itself.
    """
    parser = argparse.ArgumentParser(
        description="TonnageFlow Pulse WhatsApp Web Observer"
    )
    parser.add_argument(
        "--shadow-mode",
        action="store_true",
        help=(
            "Run the Phase 2 shadow-mode trial (reads only the group "
            "named in WHATSAPP_ALLOWED_GROUP, which must already be "
            "open). Without this flag, only Phase 1 login is run."
        ),
    )
    return parser


def main(argv=None):
    """
    CLI entry point: parses argv and dispatches to the matching
    observer. Unknown arguments cause argparse to print an error and
    exit(2); --help prints usage and exits(0) - neither path touches
    run_observer() or run_shadow_observer().
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.shadow_mode:
        run_shadow_observer()
    else:
        run_observer()


if __name__ == "__main__":
    main()
