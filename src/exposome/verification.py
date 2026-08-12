"""Verification facade for strict v2 Study releases."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .artifact_contract import RELEASE_MANIFEST_NAME, load_release
from .releases import canonical_enabled_layers
from .studies import StudyContext, load_study


@dataclass(frozen=True)
class ReleaseVerification:
    study_id: str
    release_path: Path
    checked_assets: int
    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def verify_release(context: StudyContext) -> ReleaseVerification:
    """Validate identity, exact Layer set, every checksum and release role."""
    release_path = Path(context.paths.processed) / RELEASE_MANIFEST_NAME
    try:
        release = load_release(
            context,
            verify=True,
            expected_layer_ids=canonical_enabled_layers(context),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        return ReleaseVerification(
            context.study.id,
            release_path,
            0,
            (str(exc),),
        )
    checked = len(release.assets)
    checked += len(release.layers)
    checked += sum(len(bundle.assets) for bundle in release.layers.values())
    return ReleaseVerification(context.study.id, release_path, checked, ())


def verify_study_release(
    study_ref: str | Path,
    *,
    repo_root_path: str | Path | None = None,
) -> ReleaseVerification:
    return verify_release(load_study(study_ref, repo_root_path=repo_root_path))
