"""Dagster: the Line Down pipeline as assets, from the raw download to the Tableau extracts.

    DAGSTER_HOME=$PWD/data/dagster .venv/bin/dagster dev -f orchestration/definitions.py   (UI on :3000)

On the Mac mini, launchd keeps dagster-daemon (schedules, sensors) and the web UI running
(collectors/install_launchd.sh). The live collectors are not here: they stay on launchd and
system Python, so collection carries on if Dagster is down.

Every asset calls the same script or function a person would run by hand. Only whole-job runs
are supported for the warehouse: staging, the dbt models and publish all work on one temporary
DuckDB file, which publish swaps in.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import dagster as dg
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "warehouse"))
import build  # noqa: E402

VENV_PYTHON = str(ROOT / ".venv" / "bin" / "python")
SYSTEM_PYTHON = "/usr/bin/python3"  # collectors and the download pipeline are stdlib-only


def run(context, *cmd):
    """Run a project script from the repo root; its output goes to the Dagster run log."""
    context.log.info(" ".join(cmd))
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if p.stdout:
        context.log.info(p.stdout[-20000:])
    if p.returncode != 0:
        raise dg.Failure(f"{' '.join(cmd[1:])} exited {p.returncode}", metadata={"stderr": p.stderr[-5000:]})


@dg.asset(group_name="raw", description="Toronto Open Data history files (pipelines/download_history.py).")
def raw_history(context):
    run(context, SYSTEM_PYTHON, "pipelines/download_history.py")


# One asset per staging table, keyed like dbt's sources (staging/<table>), so lineage runs table to model.
@dg.multi_asset(specs=[dg.AssetSpec(["staging", t], deps=[raw_history], group_name="warehouse",
                                    description="All-text copy of data/raw in the temporary build file.")
                       for t in build.STAGING if t != "stg_rejects"])
def warehouse_staging(context):
    build.stage(int(time.time()), log=context.log.info)


DBT_EXE = str(ROOT / ".venv" / "bin" / "dbt")  # launchd's PATH has no venv
dbt_project = DbtProject(project_dir=build.DBT, profiles_dir=build.DBT)
# dbt parse so Dagster sees every model as it is now. The daemon, the UI and each run all load
# this file at once, so each parses into its own folder and moves the manifest in whole.
MANIFEST = build.DBT / "target" / "dagster" / "manifest.json"
MANIFEST.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=MANIFEST.parent.parent) as parse_dir:
    subprocess.run([DBT_EXE, "parse", "--quiet", "--project-dir", str(build.DBT), "--profiles-dir", str(build.DBT),
                    "--target-path", parse_dir], check=True)
    os.replace(Path(parse_dir) / "manifest.json", MANIFEST)


class WarehouseGroup(DagsterDbtTranslator):
    def get_group_name(self, dbt_resource_props):
        return "warehouse"


@dbt_assets(manifest=MANIFEST, dagster_dbt_translator=WarehouseGroup())
def warehouse_dbt(context, dbt: DbtCliResource):
    os.environ["LINEDOWN_DB"] = str(build.TMP)
    yield from dbt.cli(["build"], context=context).stream()


@dg.asset(group_name="warehouse", deps=[warehouse_dbt],
          description="Checks pass, staging dropped, data/warehouse/linedown.duckdb replaced.")
def warehouse(context):
    fp = build.publish(log=context.log.info)
    return dg.MaterializeResult(metadata={t: dg.MetadataValue.int(int(n)) for t, (n, _) in fp.items()})


@dg.asset(group_name="analysis", deps=[warehouse],
          description="Difference-in-differences finding and its plots (analysis/output/).")
def disruption_finding(context):
    run(context, VENV_PYTHON, "analysis/disruption_effect.py")
    run(context, VENV_PYTHON, "analysis/plot_effect.py")


@dg.asset(group_name="analysis", deps=[warehouse], description="Pixel map replay data (map/data.js).")
def map_data(context):
    run(context, VENV_PYTHON, "map/export.py")


@dg.asset(group_name="models", deps=[warehouse], description="Delay-length model, scored once on 2025-2026.")
def delay_length_model(context):
    run(context, VENV_PYTHON, "models/delay_length.py")


@dg.asset(group_name="models", deps=[warehouse], description="Walk-or-wait rule, scored on 2022.")
def walk_or_wait_model(context):
    run(context, VENV_PYTHON, "models/walk_or_wait.py")


@dg.asset(group_name="bi", deps=[warehouse, disruption_finding],
          description="CSV extracts for the Tableau Public dashboards (data/exports/, bi/TABLEAU.md).")
def tableau_extracts(context):
    run(context, VENV_PYTHON, "bi/export_extracts.py")


# Published results are rerun by hand, on purpose: the models (test years spent) and the finding
# and map, whose committed outputs match analysis/FINDING.md. A schedule rewriting them would
# leave the repo disagreeing with its own write-ups.
published = dg.AssetSelection.assets(delay_length_model, walk_or_wait_model, disruption_finding, map_data)
weekly_refresh = dg.define_asset_job(
    "weekly_refresh", selection=dg.AssetSelection.all() - published,
    description="Download new history, rebuild the warehouse, refresh the Tableau extracts.")
daily_live = dg.define_asset_job(
    "daily_live", selection=dg.AssetSelection.assets(warehouse_staging, warehouse_dbt, warehouse, tableau_extracts),
    description="Rebuild the warehouse with the latest live snapshots and refresh the Tableau extracts.")


@dg.run_failure_sensor(default_status=dg.DefaultSensorStatus.RUNNING, description="macOS notification when a run fails, like collectors/check_fresh.py.")
def notify_on_failure(context):
    msg = f"{context.dagster_run.job_name} failed: {context.failure_event.message or ''}"[:200]
    msg = msg.replace("\\", "").replace('"', "'")
    subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Line Down pipeline failed"'])


defs = dg.Definitions(
    assets=[raw_history, warehouse_staging, warehouse_dbt, warehouse, disruption_finding, map_data,
            delay_length_model, walk_or_wait_model, tableau_extracts],
    jobs=[weekly_refresh, daily_live],
    schedules=[
        # the city publishes monthly; weekly keeps us within a week of it (was a launchd job)
        dg.ScheduleDefinition(job=weekly_refresh, cron_schedule="0 4 * * 0", execution_timezone="America/Toronto",
                              default_status=dg.DefaultScheduleStatus.RUNNING),
        dg.ScheduleDefinition(job=daily_live, cron_schedule="0 5 * * 1-6", execution_timezone="America/Toronto",
                              default_status=dg.DefaultScheduleStatus.RUNNING),
    ],
    sensors=[notify_on_failure],
    resources={"dbt": DbtCliResource(project_dir=dbt_project, profiles_dir=str(build.DBT),
                                     dbt_executable=DBT_EXE)},
    executor=dg.in_process_executor,  # one step at a time: the Mac mini has 16 GB and the build uses most of it
)
