import shutil
from pathlib import Path
import logging

from backend.adapters.fs import create_hardlink, rename_and_move, rollback_moves
from backend.domain.mode import resolve_link_dir, resolve_mode
from backend.domain.naming import build_video_stems_by_episode, compute_target_plan
from backend.models import BatchTriageJob, TriageResult, TriageStatus
from backend.config import AppConfig

logger = logging.getLogger(__name__)

async def execute_triage_job(
    job: BatchTriageJob,
    config: AppConfig,
    dry_run: bool = False,
) -> TriageResult:
    download_dir = Path(config.download_dir)
    storage_dir = Path(config.storage_dir)
    anime_name = job.effective_title
    season = job.effective_season
    mode = resolve_mode(job, config)
    link_dir = resolve_link_dir(job, config, mode)
    
    overall_success = True
    error_msg = None
    executed_moves: list[tuple[Path, Path]] = []
    video_stems_by_ep = build_video_stems_by_episode(job, download_dir)

    for it in job.items:
        if it.ignored:
            continue

        plan = compute_target_plan(job, it, config, video_stems_by_ep, mode, link_dir)
        source_file = plan.source_file
        if not source_file.exists():
            continue
        if plan.target_file != source_file:
            res = rename_and_move(source_file, plan.target_file, dry_run)
            if res.success and not dry_run:
                executed_moves.append((source_file, plan.target_file))
            if not res.success:
                overall_success = False
                error_msg = res.error_msg
                rollback_moves(executed_moves)
                break

        if plan.link_target:
            if plan.link_target.exists() and not dry_run:
                plan.link_target.unlink()
            link_source = plan.target_file if plan.target_file.exists() or dry_run else source_file
            link_res = create_hardlink(link_source, plan.link_target, dry_run)
            if not link_res.success:
                overall_success = False
                error_msg = f"Hardlink failed: {link_res.error_msg}"
                break
            
    # Cleanup only in confirm mode
    if mode != "auto" and overall_success:
        source_dir_path = download_dir / job.source_dir
        if source_dir_path.exists() and source_dir_path.is_dir() and job.source_dir != ".":
            for child in source_dir_path.rglob("*"):
                if child.is_file() and child.exists():
                    try:
                        rel_to_anime = child.relative_to(source_dir_path)
                    except ValueError:
                        rel_to_anime = Path(child.name)
                    
                    season_str = f"{season:02d}"
                    target_file = storage_dir / anime_name / f"Season {season_str}" / rel_to_anime
                    rename_and_move(child, target_file, dry_run)
            
            try:
                shutil.rmtree(source_dir_path)
            except Exception:
                logger.debug("Failed to remove source dir %s", source_dir_path, exc_info=True)

    return TriageResult(
        success=overall_success, 
        source_path=job.source_dir, 
        dest_path=str(download_dir / job.source_dir) if mode == "auto" else str(storage_dir / anime_name),
        hardlink_path=str(link_dir / anime_name) if link_dir else None,
        error_msg=error_msg
    )
