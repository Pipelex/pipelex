"""Command to check all URLs defined in pipelex/urls.py for broken links."""

from __future__ import annotations

import asyncio
import inspect
import sys

import httpx
from pydantic import BaseModel
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from pipelex.service_hub import get_console
from pipelex.urls import URLs

# Default timeout in seconds for HTTP requests
DEFAULT_TIMEOUT = 10

# Connection limits for httpx client
# - max_connections: Total concurrent connections across all hosts
# - max_keepalive_connections: Connections to keep alive for reuse
HTTP_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

# Status codes treated as OK: the URL exists but requires authentication (e.g. billing dashboards).
AUTH_REQUIRED_STATUS_CODES = {401, 403}

# Status codes treated as OK: the URL is reachable but the probe was rate-limited or bot-blocked.
RATE_LIMITED_STATUS_CODES = {429}

# All status codes that indicate a reachable URL despite being non-2xx.
REACHABLE_STATUS_CODES = AUTH_REQUIRED_STATUS_CODES | RATE_LIMITED_STATUS_CODES


class URLCheckResult(BaseModel):
    """Result of checking a single URL."""

    name: str
    url: str
    status_code: int | None
    is_ok: bool
    error_message: str | None = None


def get_all_urls_from_class() -> list[tuple[str, str]]:
    """Extract all URL attributes from the URLs class.

    Returns:
        List of tuples containing (attribute_name, url_value)
    """
    url_pairs: list[tuple[str, str]] = []
    for name, value in inspect.getmembers(URLs):
        # Skip private attributes and methods
        if name.startswith("_"):
            continue
        # Only include string values that look like URLs
        if isinstance(value, str) and value.startswith("http"):
            url_pairs.append((name, value))
    return url_pairs


async def check_single_url_async(*, client: httpx.AsyncClient, name: str, url: str) -> URLCheckResult:
    """Check if a single URL is accessible asynchronously.

    Args:
        client: The async HTTP client to use
        name: The attribute name of the URL
        url: The URL to check

    Returns:
        URLCheckResult with the check outcome
    """
    try:
        response = await client.head(url)
        # Some servers don't support HEAD, fallback to GET
        if response.status_code == 405:
            response = await client.get(url)
        is_ok = response.status_code < 400 or response.status_code in REACHABLE_STATUS_CODES
        return URLCheckResult(
            name=name,
            url=url,
            status_code=response.status_code,
            is_ok=is_ok,
            error_message=None if is_ok else f"HTTP {response.status_code}",
        )
    except httpx.TimeoutException:
        return URLCheckResult(
            name=name,
            url=url,
            status_code=None,
            is_ok=False,
            error_message="Timeout",
        )
    except httpx.ConnectError as exc:
        return URLCheckResult(
            name=name,
            url=url,
            status_code=None,
            is_ok=False,
            error_message=f"Connection error: {exc}",
        )
    except httpx.HTTPError as exc:
        return URLCheckResult(
            name=name,
            url=url,
            status_code=None,
            is_ok=False,
            error_message=f"HTTP error: {exc}",
        )


async def check_all_urls_async(
    url_pairs: list[tuple[str, str]],
    *,
    request_timeout: int,
) -> list[URLCheckResult]:
    """Check all URLs concurrently with connection pooling.

    Uses httpx.Limits for connection management which automatically handles
    per-host connection limits and connection reuse.

    Args:
        url_pairs: List of (name, url) tuples to check
        request_timeout: Request timeout in seconds

    Returns:
        List of URLCheckResult for all URLs
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=request_timeout,
        limits=HTTP_LIMITS,
    ) as client:
        tasks = [check_single_url_async(client=client, name=name, url=url) for name, url in url_pairs]
        results = await asyncio.gather(*tasks)
    return list(results)


def check_urls_cmd(*, quiet: bool = False, timeout: int = DEFAULT_TIMEOUT) -> None:
    """Check all URLs defined in pipelex/urls.py for broken links.

    Args:
        quiet: If True, output only a single validation line (for use in Make targets)
        timeout: Request timeout in seconds
    """
    console = get_console()

    # Get all URLs from the URLs class
    url_pairs = get_all_urls_from_class()

    if not url_pairs:
        if quiet:
            console.print("[yellow]⚠ URL check: No URLs found[/yellow]")
        else:
            console.print()
            console.print("[yellow]⚠[/yellow] No URLs found in pipelex/urls.py")
            console.print()
        return

    if not quiet:
        console.print()
        console.print("[bold]Checking URLs defined in pipelex/urls.py...[/bold]")
        console.print(f"  Found [cyan]{len(url_pairs)}[/cyan] URLs to check (running in parallel)")
        console.print()

    # Check all URLs concurrently
    results = asyncio.run(check_all_urls_async(url_pairs, request_timeout=timeout))

    # Sort results by name for consistent output
    results.sort(key=lambda result: result.name)

    # Display individual results if not quiet
    if not quiet:
        for result in results:
            if not result.is_ok:
                console.print(f"  [dim]{escape(result.name)}[/dim] [red]✗[/red] {escape(result.error_message or '')}")
            elif result.status_code in AUTH_REQUIRED_STATUS_CODES:
                console.print(f"  [dim]{escape(result.name)}[/dim] [yellow]✓[/yellow] {result.status_code} (auth required)")
            elif result.status_code in RATE_LIMITED_STATUS_CODES:
                console.print(f"  [dim]{escape(result.name)}[/dim] [yellow]✓[/yellow] {result.status_code} (rate limited)")
            else:
                console.print(f"  [dim]{escape(result.name)}[/dim] [green]✓[/green] {result.status_code}")

    # Count successes and failures
    ok_count = sum(1 for result in results if result.is_ok)
    broken_count = len(results) - ok_count
    broken_results = [result for result in results if not result.is_ok]

    if broken_count == 0:
        # All URLs are OK
        if quiet:
            console.print(f"[green]✓ URL check: PASSED[/green] ({ok_count} URLs checked)")
        else:
            console.print()
            success_message = (
                f"[green]✓[/green] All {ok_count} URLs are accessible!\n\n"
                "[dim]All URLs defined in pipelex/urls.py returned successful responses.[/dim]"
            )
            success_panel = Panel(
                success_message,
                title="[bold green]URL Check: PASSED[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
            console.print(success_panel)
            console.print()
    else:
        # Some URLs are broken
        if quiet:
            console.print(f"[red]✗ URL check: FAILED[/red] ({broken_count} broken out of {len(results)})")
            console.print("  Run [cyan]make cu[/cyan] for details")
        else:
            console.print()
            error_panel = Panel(
                f"[red]✗[/red] Found [bold]{broken_count}[/bold] broken URL(s)!\n\n[dim]{ok_count} URLs are OK, {broken_count} need attention.[/dim]",
                title="[bold red]URL Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()

            # Display table of broken URLs
            table = Table(title="Broken URLs", show_header=True, header_style="bold red")
            table.add_column("Attribute", style="cyan")
            table.add_column("URL", style="dim")
            table.add_column("Error", style="red")

            for result in broken_results:
                table.add_row(result.name, result.url, result.error_message or "Unknown error")

            console.print(table)
            console.print()

            console.print("[bold yellow]Recommended Actions:[/bold yellow]")
            console.print("  • Verify the URLs are correct in [cyan]pipelex/urls.py[/cyan]")
            console.print("  • Check if the target pages have moved or been removed")
            console.print("  • Update any broken URLs with correct paths")
            console.print()

        sys.exit(1)
