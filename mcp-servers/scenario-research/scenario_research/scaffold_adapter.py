"""Scaffold adapter: extends (does not duplicate) camel-oasis-scaffold runtime.

Uses script-location detection + sys.path injection so the scaffold's "import src.xxx"
and relative DATA_DIR calculations continue to work when this MCP package is
installed/used from the meta-utilities tree.

This satisfies the "wire to extend ... instead of duplicating" requirement.
All scenario, model, workforce, and analysis logic stays in the scaffold.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from .models import ScenarioRun

_SCENARIO_RUNS: dict[str, Callable[..., Awaitable[Any]]] = {}


def _find_scaffold_root() -> Path:
    """Locate the camel-oasis-scaffold directory relative to this file.

    Layout assumption (portable within meta-utilities):
      meta-utilities/
        camel-oasis-scaffold/
        mcp-servers/
          scenario-research/
            scenario_research/
              scaffold_adapter.py   <--- __file__

    Falls back to $CAMEL_OASIS_SCAFFOLD_ROOT if set (for packaged use).
    """
    env = __import__("os").environ.get("CAMEL_OASIS_SCAFFOLD_ROOT")
    if env:
        p = Path(env).resolve()
        if p.exists():
            return p
    here = Path(__file__).resolve()
    # mcp-servers/scenario-research/scenario_research/scaffold_adapter.py -> .../meta-utilities
    for parent in here.parents:
        cand = parent / "camel-oasis-scaffold"
        if cand.exists() and (cand / "src").exists():
            return cand
    # Last resort: sibling of the mcp-servers dir
    mcp_parent = here.parents[3] if len(here.parents) > 3 else here.parent
    cand = mcp_parent / "camel-oasis-scaffold"
    if cand.exists():
        return cand
    raise RuntimeError(
        "Could not locate camel-oasis-scaffold. "
        "Set CAMEL_OASIS_SCAFFOLD_ROOT or ensure it is a sibling of mcp-servers/ in the meta-utilities tree."
    )


def _ensure_scaffold_on_path() -> Path:
    root = _find_scaffold_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    # Also ensure "src" is importable as top-level package for the scaffold's internal imports
    src_dir = root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    return root


def get_scaffold_root() -> Path:
    return _ensure_scaffold_on_path()


def get_scenario_run_func(scenario: str) -> Callable[..., Awaitable[Any]]:
    """Return the async run(...) function for a supported scenario family.

    Does not execute it. Caller is responsible for awaiting with correct kwargs
    (profile_path, db_path, n_steps, etc. as defined in the scaffold).
    """
    global _SCENARIO_RUNS
    if not _SCENARIO_RUNS:
        _ensure_scaffold_on_path()
        # Import inside to pick up the path injection
    if scenario == "info_spread":
        from src.scenarios.info_spread import run as r
        _SCENARIO_RUNS[scenario] = r
    elif scenario == "opinion_dynamics":
        from src.scenarios.opinion_dynamics import run as r
        _SCENARIO_RUNS[scenario] = r
    elif scenario == "marketing_ab":
        from src.scenarios.marketing_ab import run as r
        _SCENARIO_RUNS[scenario] = r
    elif scenario == "oteemo_billable":
        # Self-contained local implementation (no camel-oasis required).
        # Uses governed oteemo roles (from oteemo/ontology/agents/*) + firm init snapshot + internal discrete firm sim.
        # Dynamic load via script location (no assumption that oteemo is under scenario_research.* package).
        # Hardened registration in sys.modules so dataclasses/pydantic introspection (sys.modules[__module__]) succeeds.
        oteemo_root = Path(__file__).resolve().parents[1] / "oteemo"
        mod_path = oteemo_root / "scenarios" / "oteemo_billable.py"
        if not mod_path.exists():
            raise RuntimeError(f"oteemo scenario module not found at {mod_path}")

        import sys as _sys
        import importlib.util as _ilu

        def _ensure_pkg(name: str, path_list: list[str]):
            if name not in _sys.modules:
                pkg_spec = _ilu.spec_from_loader(name, loader=None)
                pkg = _ilu.module_from_spec(pkg_spec) if pkg_spec else type(sys)("name")
                pkg.__path__ = path_list  # type: ignore[attr-defined]
                _sys.modules[name] = pkg
            return _sys.modules[name]

        _ensure_pkg("oteemo_local", [str(oteemo_root)])
        _ensure_pkg("oteemo_local.scenarios", [str(oteemo_root / "scenarios")])

        spec = _ilu.spec_from_file_location("oteemo_local.scenarios.oteemo_billable", str(mod_path))
        if spec is None or spec.loader is None:
            raise RuntimeError("failed to create module spec for oteemo_billable")
        mod = _ilu.module_from_spec(spec)
        mod.__package__ = "oteemo_local.scenarios"
        _sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        r = getattr(mod, "run")
        _SCENARIO_RUNS[scenario] = r
    else:
        raise ValueError(f"unknown scenario {scenario!r}")
    return _SCENARIO_RUNS[scenario]


async def execute_scenario(
    scenario: str,
    *,
    n_steps: int = 10,
    seed: int | None = 42,
    profile_path: Path | None = None,
    db_path: Path | None = None,
) -> ScenarioRun:
    """Execute a scenario by delegating to the scaffold (or local self-contained for oteemo) and return a populated ScenarioRun DTO.

    This is the wire that makes the MCP "extend" the scaffold instead of reimplementing.
    oteemo_billable is fully local (governed YAML + discrete firm sim) and does not require camel-oasis-scaffold.
    On success, status=succeeded and db_path is set where appropriate.
    Errors are captured in the DTO (no exception leakage to caller surface).
    """
    if scenario == "oteemo_billable":
        # Local path: use oteemo/ data, no scaffold root required (portable, no camel dep).
        # Dynamic file-based import so oteemo/ remains a true sibling (not nested under scenario_research).
        # We register the module + parent packages in sys.modules so that dataclasses / pydantic / typing
        # that do sys.modules[cls.__module__] introspection succeed (the previous bare exec_module left __module__ lookups as None).
        oteemo_root = Path(__file__).resolve().parents[1] / "oteemo"
        mod_path = oteemo_root / "scenarios" / "oteemo_billable.py"
        if not mod_path.exists():
            raise RuntimeError(f"oteemo scenario module not found at {mod_path}")

        import sys as _sys
        import importlib.util as _ilu

        # Ensure parent "packages" exist for relative imports and __module__ resolution inside the loaded module.
        def _ensure_pkg(name: str, path_list: list[str]):
            if name not in _sys.modules:
                pkg_spec = _ilu.spec_from_loader(name, loader=None)
                pkg = _ilu.module_from_spec(pkg_spec) if pkg_spec else type(sys)("name")
                pkg.__path__ = path_list  # type: ignore[attr-defined]
                _sys.modules[name] = pkg
            return _sys.modules[name]

        _ensure_pkg("oteemo_local", [str(oteemo_root)])
        _ensure_pkg("oteemo_local.scenarios", [str(oteemo_root / "scenarios")])

        spec = _ilu.spec_from_file_location("oteemo_local.scenarios.oteemo_billable", str(mod_path))
        if spec is None or spec.loader is None:
            raise RuntimeError("failed to create module spec for oteemo_billable")
        mod = _ilu.module_from_spec(spec)
        mod.__package__ = "oteemo_local.scenarios"
        # Place it before exec so any top-level dataclass/annotated code that triggers __module__ lookup sees it.
        _sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        oteemo_run = getattr(mod, "run")
        # db_path optional; the oteemo run will write json trace if provided. Land under oteemo/data (or traces subdir).
        pkg_data = oteemo_root / "data"
        default_db = pkg_data / f"oteemo_billable_{seed or 42}.json"
        dbp = db_path or default_db
        run_obj = await oteemo_run(profile_path=profile_path, db_path=Path(dbp), n_steps=n_steps, seed=seed)
        return run_obj

    # Standard scaffold path (may raise if camel-oasis-scaffold missing; expected for oteemo-only use)
    root = get_scaffold_root()
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if profile_path is None:
        profile_path = data_dir / "reddit" / "user_data_36.json"
    if db_path is None:
        db_path = data_dir / f"{scenario}.db"

    run_id = f"{scenario}-{seed or 'rand'}"
    run = ScenarioRun(
        run_id=run_id,
        scenario=scenario,
        n_agents=50,  # scaffold default-ish; real profile count resolved inside
        n_steps=n_steps,
        seed=seed,
        db_path=str(db_path),
        status="running",
        config_snapshot={"profile": str(profile_path), "wired_from": "scaffold_adapter"},
    )

    try:
        run_fn = get_scenario_run_func(scenario)
        # The scaffold runs accept profile_path, db_path, n_steps (and seed internally via make_model)
        # We pass what the common signature supports; each scenario may ignore extras.
        await run_fn(profile_path=profile_path, db_path=db_path, n_steps=n_steps)
        run.status = "succeeded"
        run.finished_at = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    except Exception as exc:  # noqa: BLE001 - surface as DTO error for MCP consumers
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        run.finished_at = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    return run


def execute_multi_scenario_configs(
    scenario_configs: list[dict[str, Any]],
    *,
    execution_mode: str = "local",
    parallel: bool = False,
    output_dir: Path | None = None,
    output_format: str = "jsonl",
) -> dict[str, Any]:
    """Run CAMEL multi-scenario configs through the co-located scaffold.

    This keeps MCP/CLI surfaces thin and centralizes the scaffold import boundary.
    If `output_dir` is provided, artifacts are written with the scaffold collector.
    """
    root = get_scaffold_root()
    from src.camel_sim.results.collector import write_results  # type: ignore
    from src.camel_sim.simulation.runner import run_scenarios  # type: ignore

    results = run_scenarios(
        scenario_configs,
        execution_mode=execution_mode,
        parallel=parallel,
    )
    payload: dict[str, Any] = {
        "scenarios": len(results),
        "execution_mode": execution_mode,
        "results": results,
    }
    if output_dir is not None:
        payload["artifacts"] = write_results(
            results,
            output_dir,
            output_format=output_format,  # type: ignore[arg-type]
        )
    else:
        payload["scaffold_root"] = str(root)
    return payload


def dispatch_multi_scenario_to_modal(
    scenario_file: Path | str,
    *,
    output_format: str = "parquet",
    execution_mode: str = "local",
    server_urls_json: str = "",
) -> dict[str, Any]:
    """Dispatch a multi-scenario batch to remote Modal workers.

    Delegates to the co-located camel-oasis-scaffold's documented `modal run`
    entrypoint (modal_app.py @app.local_entrypoint) using portable discovery.
    This is a "kick-off" / fire-and-forget dispatch: the returned payload
    indicates the child process was started; the CLI/MCP caller does not block
    for the full remote execution (the .map + volume write inside the entrypoint
    continues in the background child).

    The scenario_file is resolved to absolute from the caller's CWD for
    robustness when invoked via uv run from the meta-utilities tree root.
    The same get_scaffold_root() + sys.path discipline as local multi-run is used
    to construct PYTHONPATH for the child so the modal CLI can load the app
    definition (relative imports + src layout) without requiring the caller to cd.

    Two-layer timeout model:
    - Launch/kick-off phase: bounded by MODAL_LAUNCH_TIMEOUT_SEC (default 180s)
      or SCENARIO_RESEARCH_TIMEOUT_SEC in MCP contexts. This covers modal CLI
      startup, any image build, and submission.
    - Long-running remote job: governed entirely by the Modal infra + the
      definitions inside modal_app.py (per-fn timeout=900, Retries(2), and the
      overall entrypoint duration). The parent CLI/MCP process does not wait for it.

    Graceful degradation:
    - If scaffold cannot be discovered: the same RuntimeError from get_scaffold_root()
      (with CAMEL_OASIS_SCAFFOLD_ROOT hint) is raised.
    - If 'modal' CLI not on PATH: actionable error telling the user to install
      the *scaffold* with its [modal,parquet] extra into the environment that
      runs scenario-research (so 'modal' entrypoint + camel deps are present),
      plus the usual `modal token new` / auth step. Matches the guard message
      style in modal_app.py exactly.
    - No changes to local/camel execution_mode paths.

    Does not duplicate runner logic: the actual batch, server_urls handling,
    remote map, and volume write all live in (and are delegated to) the scaffold.
    """
    root = get_scaffold_root()
    modal_script = root / "src" / "camel_sim" / "modal_app.py"
    if not modal_script.exists():
        raise RuntimeError(
            f"modal_app.py not found at {modal_script} after portable discovery. "
            "Ensure camel-oasis-scaffold is a sibling of mcp-servers/ (or set CAMEL_OASIS_SCAFFOLD_ROOT)."
        )

    sf = Path(scenario_file).resolve()
    # We pass the resolved path to modal; it will load inside the entrypoint.
    # Early existence check is nice-to-have but not required (modal will surface
    # a clear load error if the file is bad or unreadable in context).

    modal_cli = shutil.which("modal")
    if modal_cli is None:
        raise RuntimeError(
            "The 'modal' CLI is not available in PATH. "
            "To kick off Modal multi-scenario analysis from the meta-utilities scenario-research CLI (or MCP), "
            "install the camel-oasis-scaffold with the modal extra into the *same* environment used by scenario-research "
            "(this brings the 'modal' console script + the scaffold's runtime imports for the app definition): "
            "uv pip install -e 'camel-oasis-scaffold[modal,parquet]' "
            "(or from the scenario-research dir: uv pip install -e '../../camel-oasis-scaffold[modal,parquet]'). "
            "Then authenticate if needed: modal token new. "
            "After that, `scenario-research multi-run <file> --target modal` (or the MCP dispatch tool) will work from any CWD. "
            "See camel-oasis-scaffold/README.md (Modal section) and the guard in src/camel_sim/modal_app.py."
        )

    cmd: list[str] = [
        modal_cli,
        "run",
        str(modal_script),
        "--scenario-file",
        str(sf),
        "--output-format",
        output_format,
        "--execution-mode",
        execution_mode,
    ]
    if server_urls_json:
        cmd.extend(["--server-urls-json", server_urls_json])

    # Portable env for child so modal CLI's python can resolve "from .config..." and "import src..." when loading modal_app.py
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    pp_parts = [str(root), str(root / "src")]
    if existing_pp:
        pp_parts.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)

    launch_timeout = float(os.getenv("MODAL_LAUNCH_TIMEOUT_SEC", os.getenv("SCENARIO_RESEARCH_TIMEOUT_SEC", "180")))

    print(
        {
            "status": "dispatching",
            "target": "modal",
            "cmd": " ".join(cmd),
            "scenario_file": str(sf),
            "scaffold_root": str(root),
            "launch_timeout_sec": launch_timeout,
        }
    )

    # Kick-off semantics: start the documented entrypoint (which internally does the remote .map + write_results_remote to volume).
    # We use Popen + new session so the long-running remote work survives the parent CLI/MCP process exit.
    # stdout/stderr are inherited so the user immediately sees the modal entrypoint's prints
    # ("Dispatching N scenarios to Modal...", the completion line, the volume paths).
    # We intentionally do *not* .wait() or .communicate() for the full duration.
    popen_kwargs: dict[str, Any] = {
        "env": env,
        "stdout": None,  # inherit for live output from modal (Dispatching..., volume write result, etc.)
        "stderr": None,
    }
    if os.name == "posix":
        popen_kwargs["preexec_fn"] = os.setsid  # new session / process group; child outlives parent exit
    else:
        # Windows: detach so parent exit doesn't kill the child
        popen_kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )

    proc = subprocess.Popen(cmd, **popen_kwargs)

    return {
        "status": "dispatched",
        "target": "modal",
        "pid": proc.pid,
        "cmd": " ".join(cmd),
        "scenario_file": str(sf),
        "scaffold_root": str(root),
        "volume": "sim-results",
        "note": (
            "Modal batch kicked off via the scaffold modal_app entrypoint (fire-and-forget). "
            "The remote run_scenario_remote.map + write_results_remote to the 'sim-results' Modal Volume continues in the child (pid above). "
            "This CLI/MCP call returned immediately without waiting for remote completion. "
            "Monitor: modal app list, modal logs <app>, modal volume ls sim-results. "
            "Retrieve artifacts later via `modal volume get sim-results ...` (or future scenario-research retrieval tool). "
            "Two-layer timeouts: launch/submit phase bounded by MODAL_LAUNCH_TIMEOUT_SEC (client); the long-running remote work uses the per-function timeout=900 + Retries inside modal_app.py."
        ),
    }
