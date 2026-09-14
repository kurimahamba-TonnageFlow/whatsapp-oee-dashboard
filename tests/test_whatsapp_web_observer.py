"""
Focused, offline tests for the Phase 1 WhatsApp Web Observer's
configuration and profile-path handling in
src/adapters/whatsapp_web_observer.py.

These tests never launch a browser and never access web.whatsapp.com -
they only exercise pure functions that resolve the local profile
directory path and read (synthetic) environment configuration.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src.adapters import whatsapp_web_observer
from src.adapters.whatsapp_web_observer import (
    PROFILE_DIR_NAME,
    SHADOW_INBOX_DIR_NAME,
    confirm_active_chat_matches,
    describe_configuration,
    get_allowed_group,
    get_profile_dir,
    get_shadow_inbox_dir,
    main,
)
from src.adapters.whatsapp_message_store import WhatsAppMessageStore
from playwright.sync_api import Error as PlaywrightError


def test_get_profile_dir_defaults_to_project_root():
    profile_dir = get_profile_dir()

    assert profile_dir.name == PROFILE_DIR_NAME
    assert profile_dir.parent == PROJECT_ROOT


def test_get_profile_dir_respects_custom_project_root(tmp_path):
    profile_dir = get_profile_dir(project_root=tmp_path)

    assert profile_dir == tmp_path / PROFILE_DIR_NAME


def test_get_allowed_group_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ALLOWED_GROUP", raising=False)

    assert get_allowed_group() is None


def test_get_allowed_group_returns_configured_value(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_GROUP", "Line 3 Alerts")

    assert get_allowed_group() == "Line 3 Alerts"


def test_describe_configuration_reports_profile_dir_as_string(tmp_path):
    configuration = describe_configuration(project_root=tmp_path)

    assert configuration["profile_dir"] == str(tmp_path / PROFILE_DIR_NAME)


def test_describe_configuration_flags_group_as_unconfigured(monkeypatch, tmp_path):
    monkeypatch.delenv("WHATSAPP_ALLOWED_GROUP", raising=False)

    configuration = describe_configuration(project_root=tmp_path)

    assert configuration["allowed_group_configured"] is False


def test_describe_configuration_flags_group_as_configured_without_leaking_value(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("WHATSAPP_ALLOWED_GROUP", "Line 3 Alerts")

    configuration = describe_configuration(project_root=tmp_path)

    assert configuration["allowed_group_configured"] is True
    assert "Line 3 Alerts" not in configuration.values()


# ==========================================================
# PHASE 2: SHADOW INBOX PATH
# ==========================================================


def test_get_shadow_inbox_dir_defaults_to_project_root():
    inbox_dir = get_shadow_inbox_dir()

    assert inbox_dir.name == SHADOW_INBOX_DIR_NAME
    assert inbox_dir.parent == PROJECT_ROOT


def test_get_shadow_inbox_dir_respects_custom_project_root(tmp_path):
    inbox_dir = get_shadow_inbox_dir(project_root=tmp_path)

    assert inbox_dir == tmp_path / SHADOW_INBOX_DIR_NAME


# ==========================================================
# PHASE 2: EXACT ALLOWED-GROUP VALIDATION
# ==========================================================


def test_confirm_active_chat_matches_exact_group_name():
    assert (
        confirm_active_chat_matches(
            "Rovema production line 1", "Rovema production line 1"
        )
        is True
    )


def test_confirm_active_chat_rejects_different_group():
    assert (
        confirm_active_chat_matches("Some other group", "Rovema production line 1")
        is False
    )


def test_confirm_active_chat_rejects_case_or_whitespace_variation():
    # "Exactly matches" - no case-folding or trimming leniency.
    assert (
        confirm_active_chat_matches(
            "rovema production line 1", "Rovema production line 1"
        )
        is False
    )
    assert (
        confirm_active_chat_matches(
            "Rovema production line 1 ", "Rovema production line 1"
        )
        is False
    )


def test_confirm_active_chat_refuses_when_allowed_group_missing():
    assert confirm_active_chat_matches("Rovema production line 1", None) is False
    assert confirm_active_chat_matches("Rovema production line 1", "") is False


def test_confirm_active_chat_refuses_when_active_title_unknown():
    assert confirm_active_chat_matches(None, "Rovema production line 1") is False
    assert confirm_active_chat_matches("", "Rovema production line 1") is False


# ==========================================================
# CLI ROUTING (offline - run_observer/run_shadow_observer are
# replaced with fakes, so no browser is ever launched)
# ==========================================================


def test_main_with_no_flag_calls_run_observer_only(monkeypatch):
    observer_calls = []
    shadow_calls = []
    monkeypatch.setattr(
        whatsapp_web_observer, "run_observer", lambda: observer_calls.append(1)
    )
    monkeypatch.setattr(
        whatsapp_web_observer,
        "run_shadow_observer",
        lambda: shadow_calls.append(1),
    )

    main([])

    assert observer_calls == [1]
    assert shadow_calls == []


def test_main_with_shadow_mode_flag_calls_run_shadow_observer_only(monkeypatch):
    observer_calls = []
    shadow_calls = []
    monkeypatch.setattr(
        whatsapp_web_observer, "run_observer", lambda: observer_calls.append(1)
    )
    monkeypatch.setattr(
        whatsapp_web_observer,
        "run_shadow_observer",
        lambda: shadow_calls.append(1),
    )

    main(["--shadow-mode"])

    assert shadow_calls == [1]
    assert observer_calls == []


def test_main_help_exits_cleanly_and_describes_both_modes(monkeypatch, capsys):
    monkeypatch.setattr(
        whatsapp_web_observer,
        "run_observer",
        lambda: pytest.fail("run_observer must not run for --help"),
    )
    monkeypatch.setattr(
        whatsapp_web_observer,
        "run_shadow_observer",
        lambda: pytest.fail("run_shadow_observer must not run for --help"),
    )

    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    assert exit_info.value.code == 0

    help_text = capsys.readouterr().out
    assert "--shadow-mode" in help_text
    assert "Phase 2 shadow-mode trial" in help_text
    assert "Phase 1 login" in help_text


def test_main_with_unknown_argument_fails_safely(monkeypatch):
    monkeypatch.setattr(
        whatsapp_web_observer,
        "run_observer",
        lambda: pytest.fail("run_observer must not run for an unknown argument"),
    )
    monkeypatch.setattr(
        whatsapp_web_observer,
        "run_shadow_observer",
        lambda: pytest.fail(
            "run_shadow_observer must not run for an unknown argument"
        ),
    )

    with pytest.raises(SystemExit) as exit_info:
        main(["--bogus-flag"])

    assert exit_info.value.code == 2


# ==========================================================
# PHASE 2: STARTUP TIMING (offline - fake page + fake clock,
# no browser, no DOM, no real sleeping)
# ==========================================================

ALLOWED_GROUP = "Rovema production line 1"


class _FakeClock:
    """A controllable stand-in for time.time()."""

    def __init__(self, start=0.0):
        self.now = start

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class _FakeRowLocator:
    """A locator that always reports zero message rows."""

    def count(self):
        return 0

    def nth(self, index):
        raise AssertionError("no rows were configured for this fake locator")


class _FakeTitlePage:
    """
    A fake Playwright page for CLI-adjacent startup-timing tests. It
    never touches a real DOM: get_active_chat_title is monkeypatched
    to read from `titles` instead of this page's locators.
    wait_for_timeout advances a fake clock and counts calls; message
    row locators always report zero rows, so _process_row/the store
    are never exercised here (that is covered by other test modules).
    """

    def __init__(self, clock, stop_after_waits=None, stop_exception=KeyboardInterrupt):
        self._clock = clock
        self._stop_after_waits = stop_after_waits
        self._stop_exception = stop_exception
        self.wait_calls = 0
        self.locator_calls = 0

    def locator(self, selector):
        self.locator_calls += 1
        return _FakeRowLocator()

    def wait_for_timeout(self, ms):
        self.wait_calls += 1
        self._clock.advance(ms / 1000)
        if self._stop_after_waits is not None and self.wait_calls >= self._stop_after_waits:
            raise self._stop_exception


def _patch_active_titles(monkeypatch, titles):
    """Make get_active_chat_title return successive values from titles."""
    remaining = iter(titles)
    monkeypatch.setattr(
        whatsapp_web_observer,
        "get_active_chat_title",
        lambda page: next(remaining),
    )


def test_wait_for_authorised_chat_waits_until_exact_match(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(whatsapp_web_observer.time, "time", clock.time)
    _patch_active_titles(monkeypatch, [None, "Some other chat", ALLOWED_GROUP])
    page = _FakeTitlePage(clock)

    result = whatsapp_web_observer.wait_for_authorised_chat(
        page, ALLOWED_GROUP, timeout_seconds=30, poll_interval_seconds=2
    )

    assert result is True
    assert page.wait_calls == 2


def test_wait_for_authorised_chat_ignores_mismatched_chats(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(whatsapp_web_observer.time, "time", clock.time)
    _patch_active_titles(
        monkeypatch,
        [
            None,
            "rovema production line 1",  # case mismatch - not exact
            "Rovema production line 1 ",  # trailing space - not exact
            "Some other chat",
            ALLOWED_GROUP,
        ],
    )
    page = _FakeTitlePage(clock)

    result = whatsapp_web_observer.wait_for_authorised_chat(
        page, ALLOWED_GROUP, timeout_seconds=60, poll_interval_seconds=2
    )

    assert result is True
    assert page.wait_calls == 4


def test_wait_for_authorised_chat_times_out_without_match(monkeypatch, capsys):
    clock = _FakeClock()
    monkeypatch.setattr(whatsapp_web_observer.time, "time", clock.time)
    monkeypatch.setattr(
        whatsapp_web_observer,
        "get_active_chat_title",
        lambda page: "Some other chat",
    )
    page = _FakeTitlePage(clock)

    result = whatsapp_web_observer.wait_for_authorised_chat(
        page, ALLOWED_GROUP, timeout_seconds=6, poll_interval_seconds=2
    )

    assert result is False

    output = capsys.readouterr().out
    assert "timed out" in output.lower()
    assert ALLOWED_GROUP not in output
    assert "Some other chat" not in output


def test_wait_for_authorised_chat_waits_indefinitely_by_default(monkeypatch):
    """
    With no timeout_seconds given, the wait must not give up even
    after far more polls than the old fixed 5-minute / 2-second-poll
    cap (150 polls) would have allowed - it keeps waiting until the
    group matches.
    """
    clock = _FakeClock()
    monkeypatch.setattr(whatsapp_web_observer.time, "time", clock.time)

    mismatches_beyond_old_cap = 200
    titles = ["Some other chat"] * mismatches_beyond_old_cap + [ALLOWED_GROUP]
    _patch_active_titles(monkeypatch, titles)
    page = _FakeTitlePage(clock)

    result = whatsapp_web_observer.wait_for_authorised_chat(page, ALLOWED_GROUP)

    assert result is True
    assert page.wait_calls == mismatches_beyond_old_cap


def test_wait_for_authorised_chat_stops_cleanly_when_browser_closes(
    monkeypatch, capsys
):
    clock = _FakeClock()
    monkeypatch.setattr(whatsapp_web_observer.time, "time", clock.time)
    _patch_active_titles(monkeypatch, ["Some other chat", "Some other chat"])
    page = _FakeTitlePage(
        clock,
        stop_after_waits=2,
        stop_exception=PlaywrightError(
            "Target page, context or browser has been closed"
        ),
    )

    result = whatsapp_web_observer.wait_for_authorised_chat(page, ALLOWED_GROUP)

    assert result is False

    output = capsys.readouterr().out
    assert "Shadow mode stopped because the browser was closed." in output
    assert ALLOWED_GROUP not in output
    assert "Some other chat" not in output


def test_run_shadow_observer_closes_cleanly_when_browser_closes_during_wait(
    monkeypatch, tmp_path
):
    """
    If the browser is closed while waiting for the authorised group,
    run_shadow_observer must not crash even though closing an
    already-closed context also raises, and must never proceed to
    historical collection or watching.
    """
    monkeypatch.setenv("WHATSAPP_ALLOWED_GROUP", ALLOWED_GROUP)
    monkeypatch.setattr(
        whatsapp_web_observer,
        "get_profile_dir",
        lambda project_root=None: tmp_path / "profile",
    )
    monkeypatch.setattr(
        whatsapp_web_observer,
        "get_shadow_inbox_dir",
        lambda project_root=None: tmp_path / "inbox",
    )

    class _FakeStubPage:
        def goto(self, url):
            pass

    class _FakeContext:
        def __init__(self):
            self.pages = []
            self.close_calls = 0

        def new_page(self):
            return _FakeStubPage()

        def close(self):
            self.close_calls += 1
            raise PlaywrightError(
                "Target page, context or browser has been closed"
            )

    class _FakeChromium:
        def __init__(self, context):
            self._context = context

        def launch_persistent_context(self, **kwargs):
            return self._context

    class _FakePlaywright:
        def __init__(self, context):
            self.chromium = _FakeChromium(context)

    class _FakeSyncPlaywrightCtx:
        def __init__(self, context):
            self._context = context

        def __enter__(self):
            return _FakePlaywright(self._context)

        def __exit__(self, *exc_info):
            return False

    fake_context = _FakeContext()
    monkeypatch.setattr(
        whatsapp_web_observer,
        "sync_playwright",
        lambda: _FakeSyncPlaywrightCtx(fake_context),
    )
    monkeypatch.setattr(
        whatsapp_web_observer,
        "wait_for_connection_status",
        lambda page, timeout_seconds=120: "logged_in",
    )
    monkeypatch.setattr(
        whatsapp_web_observer,
        "wait_for_authorised_chat",
        lambda page, allowed_group: False,
    )

    collect_calls = []
    watch_calls = []
    monkeypatch.setattr(
        whatsapp_web_observer,
        "collect_historical_messages",
        lambda *args, **kwargs: collect_calls.append(1),
    )
    monkeypatch.setattr(
        whatsapp_web_observer,
        "watch_new_messages",
        lambda *args, **kwargs: watch_calls.append(1),
    )

    whatsapp_web_observer.run_shadow_observer()

    assert collect_calls == []
    assert watch_calls == []
    assert fake_context.close_calls == 1


def test_watch_new_messages_pauses_when_leaving_authorised_group(
    monkeypatch, tmp_path, capsys
):
    clock = _FakeClock()
    monkeypatch.setattr(whatsapp_web_observer.time, "time", clock.time)
    _patch_active_titles(
        monkeypatch, [ALLOWED_GROUP, "Some other chat", "Some other chat"]
    )
    page = _FakeTitlePage(clock, stop_after_waits=3)
    store = WhatsAppMessageStore(tmp_path)

    result = whatsapp_web_observer.watch_new_messages(page, store, ALLOWED_GROUP)

    assert result == {"collected": 0}
    # Rows are only ever read while the authorised group is active -
    # one authorised iteration, then two paused ones that skip reading.
    assert page.locator_calls == 1

    output = capsys.readouterr().out
    assert output.count("pausing extraction") == 1
    assert output.count("resuming extraction") == 0
    assert ALLOWED_GROUP not in output
    assert "Some other chat" not in output


def test_watch_new_messages_resumes_after_returning_to_authorised_group(
    monkeypatch, tmp_path, capsys
):
    clock = _FakeClock()
    monkeypatch.setattr(whatsapp_web_observer.time, "time", clock.time)
    _patch_active_titles(
        monkeypatch,
        [ALLOWED_GROUP, "Some other chat", ALLOWED_GROUP, ALLOWED_GROUP],
    )
    page = _FakeTitlePage(clock, stop_after_waits=4)
    store = WhatsAppMessageStore(tmp_path)

    result = whatsapp_web_observer.watch_new_messages(page, store, ALLOWED_GROUP)

    assert result == {"collected": 0}
    # Rows are read on the authorised iterations (1st, 3rd, 4th) and
    # skipped on the mismatched one (2nd).
    assert page.locator_calls == 3

    output = capsys.readouterr().out
    assert output.count("pausing extraction") == 1
    assert output.count("resuming extraction") == 1
    assert ALLOWED_GROUP not in output
    assert "Some other chat" not in output
