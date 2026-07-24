"""Command line interface.

Everything is reachable through ``hhpanel run``. The individual stages exist
for debugging and for re-running one step without re-downloading the world.
"""

from __future__ import annotations

import sys

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from . import catalog
from . import panel as panel_mod
from . import pull as pull_mod
from .config import PROCESSED_DIR, ensure_dirs, load_sources

app = typer.Typer(
    add_completion=False,
    help="Build a longitudinal home health ownership x quality panel from CMS data.",
)
console = Console()


def _fail(message: str) -> None:
    console.print(f"[bold red]Stopped.[/bold red] {message}")
    raise typer.Exit(code=1)


@app.command()
def discover(refresh: bool = typer.Option(False, help="Ignore the cached catalog.")):
    """Resolve every dataset in sources.json to a live CMS dataset id."""
    ensure_dirs()
    try:
        resolved = catalog.resolve(load_sources(), refresh=refresh)
    except (catalog.DatasetNotFound, FileNotFoundError, ValueError) as exc:
        _fail(str(exc))

    catalog.save_resolved(resolved)
    table = Table("key", "portal", "matched title", "modified")
    for item in resolved:
        table.add_row(item.key, item.portal, item.matched_title, item.modified or "-")
    console.print(table)
    console.print(f"[green]Resolved {len(resolved)} datasets.[/green]")


@app.command()
def pull(
    refresh: bool = typer.Option(False, help="Re-download instead of using the cache."),
    max_pages: int = typer.Option(
        0, help="Stop after N pages per dataset (0 = all). Useful for a smoke test."
    ),
):
    """Download a dated snapshot of every resolved dataset."""
    ensure_dirs()
    try:
        resolved = catalog.load_resolved()
    except FileNotFoundError as exc:
        _fail(str(exc))

    results = pull_mod.pull_all(
        resolved, refresh=refresh, max_pages=max_pages or None
    )
    table = Table("key", "rows", "file")
    for key, path, count in results:
        table.add_row(key, f"{count:,}", path.name)
    console.print(table)


@app.command()
def build():
    """Join the snapshots into data/processed/panel.parquet."""
    ensure_dirs()
    quality_files = pull_mod.all_snapshots("hha_quality")
    if not quality_files:
        _fail("No Care Compare snapshots on disk yet. Run:  hhpanel pull")

    quality = pd.concat(
        [panel_mod.prepare_quality(pd.read_parquet(f)) for f in quality_files],
        ignore_index=True,
    )

    owner_files = pull_mod.all_snapshots("hha_owners")
    enrl_files = pull_mod.all_snapshots("hha_enrollments")
    ownership = None
    if owner_files and enrl_files:
        frames = []
        for owner_file in owner_files:
            date = owner_file.stem.split("__")[-1]
            match = [f for f in enrl_files if f.stem.endswith(date)] or enrl_files[-1:]
            frames.append(
                panel_mod.prepare_ownership(
                    pd.read_parquet(owner_file), pd.read_parquet(match[-1])
                )
            )
        ownership = pd.concat(frames, ignore_index=True)
    else:
        console.print(
            "[yellow]No ownership snapshots found -- building a quality-only "
            "panel. Ownership columns will be zero-filled.[/yellow]"
        )

    result = panel_mod.build_panel(quality, ownership)
    paths = panel_mod.write_outputs(result)

    console.print(panel_mod.summarize(result).to_string(index=False))
    console.print(f"[green]Wrote {paths['panel']}[/green]")


@app.command()
def run(
    max_pages: int = typer.Option(0, help="Stop after N pages per dataset (0 = all).")
):
    """Do everything: discover, pull, build. This is the normal entry point."""
    discover(refresh=False)
    pull(refresh=False, max_pages=max_pages)
    build()


@app.command()
def status():
    """Show what has been downloaded and built so far."""
    ensure_dirs()
    table = Table("artifact", "state")
    for key in ("hha_quality", "hha_owners", "hha_enrollments"):
        snaps = pull_mod.all_snapshots(key)
        table.add_row(
            key,
            f"{len(snaps)} snapshot(s), latest {snaps[-1].stem.split('__')[-1]}"
            if snaps
            else "[dim]none[/dim]",
        )
    built = PROCESSED_DIR / "panel.parquet"
    table.add_row("panel.parquet", "built" if built.exists() else "[dim]not built[/dim]")
    console.print(table)


def main() -> int:
    app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
