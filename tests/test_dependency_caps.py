# MIT License
# Copyright (c) 2026 Vitor Maia Rodovalho
"""Dependency-cap contract tests (issue #245).

Three dependencies carry an *upper* bound that exists for a reason written
beside it in ``pyproject.toml`` rather than for one a resolver can infer:

- ``mcp<2`` — the v2 SDK replaces the ``FastMCP`` API imported at
  ``src/mcp_server.py:61`` with ``McpServer``.
- ``pydantic<2.14`` — serialization drift moves the ADR-0014 canonical
  ``input_hash``, which is a forensic contract.
- ``ruff<0.17`` — the default rule set widens across minors, and CI gates on
  ``ruff format --check``.

Until now each bound was enforced by its comment alone, and a comment lost
once: #227 widened ``mcp`` to ``<3`` on 2026-09-04, left the ``Cap at 1.x``
comment directly above it intact, and broke ``src/mcp_server.py`` at import —
all 22 MCP tools — until an unrelated branch touched ``docs/`` fifteen hours
later (#244).

Nothing caught it because the failure is structural, not incidental: the only
job that imports the MCP server (``Doc sync check``) is path-filtered, so the
dependency-only pull request that breaks a cap is exactly the one that cannot
observe the break.  These tests run in the non-path-filtered ``Backend
(Python)`` job instead, which makes the cap something that fails rather than
something a reader is trusted to notice.
"""

from __future__ import annotations

import importlib
from importlib import metadata
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

#: ``(distribution, requirement string as written in pyproject, why the cap exists)``.
#: The requirement string is matched **byte-exactly** against the file, so
#: widening a bound fails here until the widener also edits this table — which
#: is the point: the bump becomes a decision instead of a bot's default.
CAPPED_DEPENDENCIES: tuple[tuple[str, str, str], ...] = (
    (
        "mcp",
        "mcp>=1.27.1,<2",
        "src/mcp_server.py:61 imports `mcp.server.fastmcp.FastMCP`, which the v2 "
        "SDK replaces with `McpServer`. Widening this cap breaks the MCP server "
        "at import (regression #227, fix #244). Bump only behind a v2 migration ADR.",
    ),
    (
        "pydantic",
        "pydantic>=2.13.4,<2.14",
        "serialization drift across pydantic minors moves the ADR-0014 canonical "
        "`input_hash`, which is a forensic contract with rows already persisted "
        "against it. See tests/test_canonical_hash.py::TestByteExactPin.",
    ),
    (
        "ruff",
        "ruff>=0.15.12,<0.17",
        "ruff's default rule set is not stable across minors: 0.16 widened it "
        "(UP/B/SIM/RUF/S) and turned a green suite into 801 findings with no "
        "source change. CI also gates on `ruff format --check`.",
    ),
)

_IDS = [dist for dist, _, _ in CAPPED_DEPENDENCIES]


def _pyproject_text() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


@pytest.mark.parametrize(("dist", "requirement", "why"), CAPPED_DEPENDENCIES, ids=_IDS)
def test_documented_cap_is_still_written_in_pyproject(
    dist: str, requirement: str, why: str
) -> None:
    """The cap string must survive byte-exact in ``pyproject.toml``.

    This is the check that would have failed #227 at review time.
    """
    assert requirement in _pyproject_text(), (
        f"The `{dist}` cap `{requirement}` is no longer present in pyproject.toml.\n\n"
        f"Why the cap exists: {why}\n\n"
        f"If the bump is deliberate, update CAPPED_DEPENDENCIES in this file in the "
        f"same commit, and update the explanatory comment above the dependency — a "
        f"widened pin under a comment that still says otherwise is what broke main "
        f"on 2026-09-04 (see #245)."
    )


@pytest.mark.parametrize(("dist", "requirement", "why"), CAPPED_DEPENDENCIES, ids=_IDS)
def test_installed_version_respects_documented_cap(dist: str, requirement: str, why: str) -> None:
    """The *resolved* version must satisfy the cap, not merely the declared one.

    Covers the case the string check cannot see: a constraint file, a stale
    lock, or a transitive resolution installing above the documented bound.
    """
    try:
        installed = metadata.version(dist)
    except metadata.PackageNotFoundError:
        pytest.skip(f"`{dist}` is not installed in this environment")

    specifier = SpecifierSet(requirement.removeprefix(dist))
    assert Version(installed) in specifier, (
        f"`{dist}` resolves to {installed}, outside its documented cap `{requirement}`.\n\n"
        f"Why the cap exists: {why}"
    )


def test_mcp_server_imports_under_the_capped_sdk() -> None:
    """Import the MCP server for real, and fail — never skip — when it breaks.

    ``tests/test_mcp_cli.py`` reached for ``pytest.importorskip("src.mcp_server")``,
    which turns *the module is broken* into *the module is absent* and reports a
    skip.  Under mcp 2.x the missing ``mcp.server.fastmcp`` raises
    ``ModuleNotFoundError`` — an ``ImportError`` subclass — so that guard would
    have stayed green through the very regression it looks like it covers.  The
    skip here is keyed on the **SDK**, so an absent extra skips and a broken
    import fails.
    """
    pytest.importorskip("mcp", reason="the `mcp` extra is not installed")

    module = importlib.import_module("src.mcp_server")

    assert module.mcp is not None, "FastMCP server object failed to initialise"
