"""A saved key's line names the organization it acts for, by name and id, with what the hosted API states of it."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.commands.login.command import KeySource, LoginOutcome, check_and_save_api_key
from pipelex.hosted.api_key_check import ApiKeyCheck, ApiKeyVerdict, KeyOrganization
from tests.helpers.login_browser import API_URL, TEST_KEY, saved_key

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

APP_URL = "https://app.test"


class TestLoginNamesOrganization:
    @pytest.mark.parametrize(
        ("organization", "expected"),
        [
            (
                KeyOrganization(org_id="org_01ANALYTICAL", name="Analytical Engines"),
                "Your Pipelex API key acts for the organization Analytical Engines (org_01ANALYTICAL) and is saved to",
            ),
            (KeyOrganization(org_id="org_01SETTINGUP", name=None), "Your Pipelex API key acts for the organization org_01SETTINGUP and is saved to"),
            (KeyOrganization(org_id="org_01SETTINGUP", name=""), "Your Pipelex API key acts for the organization org_01SETTINGUP and is saved to"),
            (None, "Your Pipelex API key is saved to"),
        ],
    )
    def test_the_saved_line_names_what_is_known_of_the_organization(
        self,
        mocker: MockerFixture,
        pipelex_home: Path,
        organization: KeyOrganization | None,
        expected: str,
    ) -> None:
        """A nameless organization is named by its id, and an answer stating none, as an older platform's, names none."""
        mocker.patch(
            "pipelex.cli.commands.login.command.check_pipelex_api_key",
            return_value=ApiKeyCheck(verdict=ApiKeyVerdict.ACCEPTED, base_url=API_URL, account_email="ada@example.com", organization=organization),
        )
        buffer = StringIO()

        outcome = check_and_save_api_key(console=Console(file=buffer, width=400), api_key=TEST_KEY, source=KeySource.BROWSER, app_origin=APP_URL)

        assert outcome == LoginOutcome.SAVED
        assert saved_key(home=pipelex_home) == TEST_KEY
        printed = " ".join(buffer.getvalue().split())
        assert f"Logged in as ada@example.com. {expected} {pipelex_home / '.env'}" in printed
        assert TEST_KEY not in printed

    @pytest.mark.usefixtures("pipelex_home")
    def test_an_organization_name_is_printed_as_written(self, mocker: MockerFixture) -> None:
        """A name holding the console's markup is printed, never read as markup."""
        mocker.patch(
            "pipelex.cli.commands.login.command.check_pipelex_api_key",
            return_value=ApiKeyCheck(
                verdict=ApiKeyVerdict.ACCEPTED,
                base_url=API_URL,
                account_email="ada@example.com",
                organization=KeyOrganization(org_id="org_01BRACKETS", name="[bold]Lab[/bold]"),
            ),
        )
        buffer = StringIO()

        check_and_save_api_key(console=Console(file=buffer, width=400), api_key=TEST_KEY, source=KeySource.BROWSER, app_origin=APP_URL)

        assert "acts for the organization [bold]Lab[/bold] (org_01BRACKETS)" in buffer.getvalue()
