"""KeySmith command-line interface (typer).

Subcommands:
    ping         — open the board and verify it responds
    list         — list configured actions
    run <name>   — execute a named action sequence from config
    tap <key>    — ad-hoc: tap a single key (no config needed)
    release-all  — emergency: release every held key
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import typer

from keysmith import __version__
from keysmith.config import Config, ConfigError, DeviceConfig, Step, load_config
from keysmith.discovery import discover_port
from keysmith.keymap import UnknownKeyError, resolve_key
from keysmith.protocol import Protocol, KeySmithError, PingFailedError


app = typer.Typer(
    name="keysmith",
    help="USB HID keyboard relay — drives the KeySmith Pro Micro firmware.",
    no_args_is_help=True,
    add_completion=False,
)


# ---- Shared options ---------------------------------------------------


def _config_option() -> Optional[Path]:
    return typer.Option(
        None,
        "--config", "-c",
        help="Path to YAML config file (overrides $KEYSMITH_CONFIG_FILE and standard locations).",
    )


def _port_option() -> Optional[str]:
    return typer.Option(
        None,
        "--port", "-p",
        help="Serial port path. Overrides config and autodiscovery.",
    )


# ---- Helpers ----------------------------------------------------------


def _resolve_port(cli_port: Optional[str], cfg: Config) -> str:
    """Pick the device port to use, in priority order.

    1. --port flag
    2. config.device.port (if it doesn't contain wildcards)
    3. autodiscovery (honors cfg.device.open_delay_s and baud)
    """
    if cli_port:
        return cli_port
    if cfg.device.port and "*" not in cfg.device.port and "?" not in cfg.device.port:
        return cfg.device.port
    try:
        return discover_port(
            baud=cfg.device.baud,
            open_delay_s=cfg.device.open_delay_s,
        )
    except KeySmithError as err:
        typer.secho(f"error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from err


def _open_protocol(port: str, cfg_device: DeviceConfig) -> Protocol:
    return Protocol(
        port,
        baud=cfg_device.baud,
        open_delay_s=cfg_device.open_delay_s,
    )


def _load_or_die(explicit: Optional[Path]) -> Config:
    try:
        return load_config(explicit)
    except ConfigError as err:
        typer.secho(f"config error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from err


# ---- Commands ---------------------------------------------------------


@app.command()
def version() -> None:
    """Print the keysmith host CLI version."""
    typer.echo(f"keysmith {__version__}")


@app.command()
def ping(
    config: Optional[Path] = _config_option(),
    port: Optional[str] = _port_option(),
) -> None:
    """Open the board and verify it responds to PING."""
    cfg = _load_or_die(config)
    chosen = _resolve_port(port, cfg)
    try:
        with _open_protocol(chosen, cfg.device) as p:
            ver = p.ping()
    except (PingFailedError, OSError, KeySmithError) as err:
        typer.secho(f"PING failed on {chosen}: {err}",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from err
    typer.echo(f"OK  port={chosen}  protocol_version={ver}")


@app.command("list")
def list_actions(
    config: Optional[Path] = _config_option(),
) -> None:
    """List all named actions in the loaded config."""
    cfg = _load_or_die(config)
    if cfg.source is None:
        typer.secho(
            "No config file loaded. Set $KEYSMITH_CONFIG_FILE or pass --config.",
            fg=typer.colors.YELLOW, err=True,
        )
        raise typer.Exit(code=1)
    if not cfg.actions:
        typer.echo(f"(no actions defined in {cfg.source})")
        return
    typer.echo(f"# actions in {cfg.source}")
    for name in cfg.list_actions():
        steps = cfg.actions[name]
        summary = " ".join(_summarize_step(s) for s in steps)
        typer.echo(f"  {name:20s}  {summary}")


def _summarize_step(step: Step) -> str:
    (op, val), = step.items()
    # Step ops without a meaningful argument print as bare names. The
    # match here uses the kebab-case keys that pass config validation
    # (snake_case is rejected upstream by config._reject_unknown_keys).
    if op == "release-all":
        return "release-all"
    return f"{op}({val})"


@app.command()
def run(
    action: str = typer.Argument(..., help="Name of the action to run."),
    config: Optional[Path] = _config_option(),
    port: Optional[str] = _port_option(),
) -> None:
    """Execute a named action sequence from the config.

    On any error mid-sequence, makes a best-effort `release_all()` call
    so that a half-finished `press: cmd` step doesn't leave the modifier
    stuck down system-wide.
    """
    cfg = _load_or_die(config)
    if not cfg.has_action(action):
        avail = ", ".join(cfg.list_actions()) or "(none)"
        typer.secho(
            f"unknown action: {action!r}. Available: {avail}",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    steps = cfg.actions[action]
    chosen = _resolve_port(port, cfg)
    try:
        with _open_protocol(chosen, cfg.device) as p:
            try:
                for i, step in enumerate(steps):
                    _execute_step(p, step, action_name=action, index=i)
            except BaseException:
                # Any failure mid-sequence — KeyboardInterrupt, exception,
                # or Typer.Exit — could leave a key held. Best-effort
                # release_all over the same still-open serial connection.
                # We swallow secondary errors from release_all so the
                # original cause propagates unchanged.
                try:
                    p.release_all()
                except Exception:
                    pass
                raise
    except UnknownKeyError as err:
        typer.secho(f"key error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from err
    except (KeySmithError, OSError) as err:
        typer.secho(f"runtime error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from err


def _execute_step(
    p: Protocol,
    step: Step,
    *,
    action_name: str,
    index: int,
) -> None:
    (op, val), = step.items()
    if op == "press":
        p.press(resolve_key(val))
    elif op == "release":
        p.release(resolve_key(val))
    elif op == "tap":
        p.tap(resolve_key(val))
    elif op == "delay-ms":
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            raise KeySmithError(
                f"action {action_name!r} step {index}: delay-ms must be a "
                f"non-negative integer, got {val!r}"
            )
        time.sleep(val / 1000.0)
    elif op == "release-all":
        p.release_all()
    else:  # pragma: no cover — config validator already rejects this
        raise KeySmithError(f"unknown step op: {op}")


@app.command()
def tap(
    key: str = typer.Argument(..., help="Key alias or HID code (e.g. 'a', 'cmd', '0x89')."),
    config: Optional[Path] = _config_option(),
    port: Optional[str] = _port_option(),
) -> None:
    """Ad-hoc: tap a single key without needing a config file."""
    cfg = _load_or_die(config)
    try:
        code = resolve_key(key)
    except UnknownKeyError as err:
        typer.secho(f"key error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from err
    chosen = _resolve_port(port, cfg)
    try:
        with _open_protocol(chosen, cfg.device) as p:
            p.tap(code)
    except (KeySmithError, OSError) as err:
        typer.secho(f"error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from err
    typer.echo(f"tapped {key} (0x{code:02X})")


@app.command("release-all")
def release_all_cmd(
    config: Optional[Path] = _config_option(),
    port: Optional[str] = _port_option(),
) -> None:
    """Emergency: release every held key."""
    cfg = _load_or_die(config)
    chosen = _resolve_port(port, cfg)
    try:
        with _open_protocol(chosen, cfg.device) as p:
            p.release_all()
    except (KeySmithError, OSError) as err:
        typer.secho(f"error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from err
    typer.echo("released all keys")


def main() -> None:  # pragma: no cover
    """Console-script entry point (also exposed as `keysmith.cli:app`)."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
