"""GitHub-specific runtime-state bridge."""

from __future__ import annotations

from pathlib import Path

from github.schemas import GitHubProgress

from shared.runtime_state.admin import rebuild_compat_projections
from shared.runtime_state.store import RuntimeStateStore


class GitHubRuntimeStateBridge:
    """Keeps GitHub progress/resume semantics DB-authoritative."""

    def __init__(
        self,
        *,
        store: RuntimeStateStore,
        output_dir: str | Path,
        brief_id: str,
        brief_name: str,
    ):
        self.store = store
        self.output_dir = Path(output_dir)
        self.brief_id = brief_id
        self.brief_name = brief_name
        self.progress_path = self.output_dir / "progress.json"

    def start_or_resume_run(self, *, resume: bool) -> tuple[int, GitHubProgress]:
        self.store.reconcile_open_attempts(source="github", brief_id=self.brief_id)
        latest_run = self.store.get_latest_run(source="github", brief_id=self.brief_id)

        if resume and latest_run and self.store.has_work_units(int(latest_run["id"])):
            run_id = self.store.start_run(
                source="github",
                brief_id=self.brief_id,
                output_dir=str(self.output_dir),
                mode="resume",
                resume_state=self.store.get_run_resume_state(int(latest_run["id"])),
                resumed_from_run_id=int(latest_run["id"]),
                clone_work_units_from_run_id=int(latest_run["id"]),
            )
            self.rebuild_artifacts(run_id)
            return run_id, self.store.load_github_progress(run_id)

        run_id = self.store.start_run(
            source="github",
            brief_id=self.brief_id,
            output_dir=str(self.output_dir),
            mode="resume" if resume else "fresh",
            resume_state={"brief_name": self.brief_name},
            resumed_from_run_id=int(latest_run["id"]) if resume and latest_run else None,
        )

        if resume and self.progress_path.exists():
            try:
                progress = GitHubProgress.from_file(str(self.progress_path))
                self.sync_progress(run_id, progress)
                return run_id, self.store.load_github_progress(run_id)
            except Exception:
                pass

        progress = GitHubProgress(brief_name=self.brief_name)
        self.sync_progress(run_id, progress)
        return run_id, progress

    def sync_progress(self, run_id: int, progress: GitHubProgress) -> None:
        self.store.sync_github_progress(run_id, progress)
        self.rebuild_artifacts(run_id)

    def load_progress(self, run_id: int) -> GitHubProgress:
        return self.store.load_github_progress(run_id)

    def load_blocked_usernames(self, usernames: list[str]) -> set[str]:
        return self.store.get_github_blocked_usernames(self.brief_id, usernames)

    def rebuild_artifacts(self, run_id: int) -> None:
        rebuild_compat_projections(
            self.store,
            run_id=run_id,
            output_dir=self.output_dir,
        )
