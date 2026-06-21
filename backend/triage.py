import os
import shutil
from pathlib import Path
from backend.models import TriageJob, TriageResult, TriageStatus
from backend.config import AppConfig

def build_target_path(
    anime_name: str,
    season: int,
    episode: int,
    extension: str,
    storage_dir: Path,
) -> Path:
    """
    Returns the target path under the storage directory.
    Format: {storage_dir}/{anime_name}/Season {season}/{anime_name} S{SS}E{EE}.{ext}
    """
    season_str = f"{season:02d}"
    episode_str = f"{episode:02d}"
    filename = f"{anime_name} S{season_str}E{episode_str}.{extension}"
    return storage_dir / anime_name / f"Season {season}" / filename

def rename_and_move(
    source: Path,
    target: Path,
    dry_run: bool = False,
) -> TriageResult:
    if not source.exists() and not dry_run:
        return TriageResult(success=False, source_path=str(source), error_msg="Source does not exist")
        
    if target.exists() and not dry_run:
        return TriageResult(success=False, source_path=str(source), dest_path=str(target), error_msg="Target already exists")

    if not dry_run:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Need to copy then delete to ensure hardlinks can be safely tracked?
            # Actually shutil.move works, but let's just use it
            shutil.move(str(source), str(target))
            rollback_info = {"original_source": str(source), "moved_to": str(target), "action": "move"}
            return TriageResult(success=True, source_path=str(source), dest_path=str(target), rollback_info=rollback_info)
        except Exception as e:
            return TriageResult(success=False, source_path=str(source), dest_path=str(target), error_msg=str(e))
    else:
        return TriageResult(success=True, source_path=str(source), dest_path=str(target))

def create_hardlink(
    source: Path,
    link_target: Path,
    dry_run: bool = False,
) -> TriageResult:
    if not source.exists() and not dry_run:
        return TriageResult(success=False, source_path=str(source), dest_path=str(source), error_msg="Source does not exist")
        
    if link_target.exists() and not dry_run:
        # Check if they are the same file (same inode)
        if source.stat().st_ino == link_target.stat().st_ino:
            return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target))
        return TriageResult(success=False, source_path=str(source), hardlink_path=str(link_target), error_msg="Link target exists and is a different file")

    if not dry_run:
        try:
            link_target.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, link_target)
            rollback_info = {"link_path": str(link_target), "action": "link"}
            return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target), rollback_info=rollback_info)
        except Exception as e:
            return TriageResult(success=False, source_path=str(source), hardlink_path=str(link_target), error_msg=str(e))
    else:
        return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target))

def rollback(result: TriageResult) -> bool:
    if not result.rollback_info:
        return True
        
    try:
        if result.rollback_info.get("action") == "move":
            src = result.rollback_info["original_source"]
            dst = result.rollback_info["moved_to"]
            if Path(dst).exists():
                shutil.move(dst, src)
        elif result.rollback_info.get("action") == "link":
            link = result.rollback_info["link_path"]
            if Path(link).exists():
                os.remove(link)
        return True
    except Exception:
        return False

async def execute_triage_job(
    job: TriageJob,
    config: AppConfig,
    dry_run: bool = False,
) -> TriageResult:
    anime_name = job.effective_title
    season = job.effective_season or 1
    episode = job.effective_episode or 0
    extension = job.parsed.extension
    
    source_file = Path(config.download_dir) / job.parsed.raw_filename
    
    # Storage target
    storage_target = build_target_path(
        anime_name=anime_name,
        season=season,
        episode=episode,
        extension=extension,
        storage_dir=config.storage_dir
    )
    
    # Jellyfin target
    jellyfin_base = config.jellyfin_airing_dir if job.status == TriageStatus.confirmed else config.jellyfin_collect_dir
    if getattr(job, "mode", "confirm") == "auto":
        jellyfin_base = config.jellyfin_airing_dir
    else:
        jellyfin_base = config.jellyfin_collect_dir
        
    jellyfin_target = build_target_path(
        anime_name=anime_name,
        season=season,
        episode=episode,
        extension=extension,
        storage_dir=jellyfin_base
    )

    # 1. Rename and move
    move_res = rename_and_move(source_file, storage_target, dry_run=dry_run)
    if not move_res.success:
        return move_res

    # 2. Hardlink
    link_source = storage_target if not dry_run else source_file
    link_res = create_hardlink(link_source, jellyfin_target, dry_run=dry_run)
    
    if not link_res.success:
        # Rollback move
        if not dry_run:
            rollback(move_res)
        return TriageResult(
            success=False,
            source_path=str(source_file),
            dest_path=str(storage_target),
            error_msg=f"Link failed: {link_res.error_msg}. Move rolled back."
        )

    # Both succeeded
    # Combine rollback info
    combined_rollback = {
        "action": "move_and_link",
        "original_source": str(source_file),
        "moved_to": str(storage_target),
        "link_path": str(jellyfin_target)
    }
    
    # Note: rollback for combined would be custom or we can just keep them separate
    # But as per signature, rollback takes a result.
    
    return TriageResult(
        success=True,
        source_path=str(source_file),
        dest_path=str(storage_target),
        hardlink_path=str(jellyfin_target),
        rollback_info=combined_rollback
    )
