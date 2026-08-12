"""Dependency-aware in-process execution for configured exposome Studies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .artifact_contract import load_layer_bundle, load_release
from .execution import LayerRequirements, StudyExecutionGraph, build_execution_graph
from .layers import (
    LayerExecutionError,
    LayerRunPlan,
    build_run_plan,
    build_study_master_from_catalog,
    execute_run_plan,
    layer_execution_identity,
    load_layer_catalog,
)
from .releases import canonical_enabled_layers, write_release_manifest
from .studies import StudyContext, load_study


@dataclass(frozen=True)
class StudyRun:
    context: StudyContext
    plans: tuple[LayerRunPlan, ...]
    build_master: bool
    graph: StudyExecutionGraph | None = None
    results: tuple[Any, ...] = ()
    master: Any | None = None
    release_manifest: Any | None = None

    @property
    def has_blockers(self) -> bool:
        return any(not plan.preflight.runnable and not plan.skip for plan in self.plans)


def materialize_study_release(study: str) -> StudyRun:
    """Rebuild the aggregate master and v2 release from verified local bundles.

    This is the deliberate final step after one or more partial ``run``
    commands.  It performs no provider work: every enabled Layer must already
    have a verified v2 bundle.  Keeping it separate prevents a partial run
    from silently combining fresh Layer outputs with a stale master/release.
    """
    context = load_study(study)
    if context.is_native:
        raise ValueError("materialize targets aggregate studies; native studies have no master")
    catalog = load_layer_catalog()
    enabled = canonical_enabled_layers(context)
    available = _verified_bundle_ids(context, catalog, enabled)
    missing = tuple(layer_id for layer_id in enabled if layer_id not in available)
    if missing:
        raise ValueError(
            "Cannot materialize a Study release; enabled Layer bundles are not "
            f"verified v2 artifacts: {', '.join(missing)}. "
            "Run the required recovery commands, then explicitly migrate any "
            "remaining verified v1 artifacts."
        )
    master = build_study_master_from_catalog(
        context,
        catalog=catalog,
        layer_ids=enabled,
        strict_required=True,
        write=True,
    )
    release_manifest = write_release_manifest(context, master)
    return StudyRun(
        context=context,
        plans=(),
        build_master=True,
        master=master,
        release_manifest=release_manifest,
    )


def run_study(
    study: str,
    *,
    layer_ids: Sequence[str] | None = None,
    resume: bool = False,
    force: bool = False,
    dry_run: bool = False,
    build_master: bool = True,
) -> StudyRun:
    """Plan and execute one Study through a validated dependency DAG."""
    if resume and force:
        raise ValueError("--resume and --force are mutually exclusive")
    context = load_study(study)
    if context.is_native:
        build_master = False
    catalog = load_layer_catalog()
    enabled = canonical_enabled_layers(context)
    requested = tuple(
        catalog.resolve_id(layer_id)
        for layer_id in (layer_ids if layer_ids is not None else context.enabled_layers)
    )
    available = _verified_bundle_ids(context, catalog, enabled)
    graph = build_execution_graph(
        catalog.layers,
        requested,
        available_bundle_ids=available,
    )
    plans = build_run_plan(
        context,
        catalog=catalog,
        layer_ids=graph.ordered_layer_ids,
        resume=resume,
        force=force,
    )
    summary = StudyRun(
        context=context,
        plans=plans,
        build_master=build_master,
        graph=graph,
    )
    if dry_run:
        return summary

    is_full_run = set(requested) == set(enabled)
    results: list[Any] = []
    completed = set(available)
    for stage in graph.stages:
        if stage.materialize_master_before:
            if not is_full_run:
                _require_existing_release_master(context, enabled)
            else:
                build_study_master_from_catalog(
                    context,
                    catalog=catalog,
                    layer_ids=tuple(
                        layer_id
                        for layer_id in enabled
                        if layer_id in completed
                        and not LayerRequirements.from_mapping(
                            catalog.get(layer_id).requirements
                        ).requires_master
                    ),
                    strict_required=True,
                    write=True,
                )
        stage_plans = build_run_plan(
            context,
            catalog=catalog,
            layer_ids=stage.layer_ids,
            resume=resume,
            force=force,
        )
        stage_results = execute_run_plan(context, stage_plans)
        results.extend(stage_results)
        for result in stage_results:
            if result.action in {"executed", "skipped"}:
                completed.add(result.layer_id)
        if any(result.action == "failed" for result in stage_results):
            break

    failed = tuple(result for result in results if result.action == "failed")
    master = None
    release_manifest = None
    if not failed and is_full_run:
        if build_master:
            master = build_study_master_from_catalog(
                context,
                catalog=catalog,
                layer_ids=enabled,
                strict_required=True,
                write=True,
            )
            release_manifest = write_release_manifest(context, master)
        elif context.is_native:
            release_manifest = write_release_manifest(context, None)

    summary = StudyRun(
        context=context,
        plans=plans,
        build_master=build_master,
        graph=graph,
        results=tuple(results),
        master=master,
        release_manifest=release_manifest,
    )
    if failed:
        details = "; ".join(f"{result.layer_id} ({result.error})" for result in failed)
        error = LayerExecutionError(
            f"{len(failed)} Layer(s) failed for Study {study!r}: {details}. "
            "The master and Study release were not replaced; successful bundles remain."
        )
        error.summary = summary  # type: ignore[attr-defined]
        raise error
    return summary


def _verified_bundle_ids(context: Any, catalog: Any, layer_ids: Sequence[str]) -> set[str]:
    verified: set[str] = set()
    for layer_id in layer_ids:
        spec = catalog.get(layer_id)
        try:
            identity = layer_execution_identity(context, spec)
            load_layer_bundle(
                context,
                layer_id,
                verify=True,
                expected_execution_fingerprint=identity.fingerprint,
                spec=spec,
            )
        except (FileNotFoundError, OSError, TypeError, ValueError):
            continue
        verified.add(layer_id)
    return verified


def _require_existing_release_master(context: Any, enabled: Sequence[str]) -> None:
    """A partial run may consume, but never replace, an existing full master."""
    release = load_release(
        context,
        verify=True,
        expected_layer_ids=enabled,
    )
    if release.asset("master_csv") is None:
        raise ValueError(
            "A partial master-dependent run requires a verified existing master_csv"
        )
