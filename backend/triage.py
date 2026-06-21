import os
import shutil
from pathlib import Path
from backend.models import BatchTriageJob, TriageResult, TriageStatus
from backend.config import AppConfig

def rename_and_move(
    source: Path,
    target: Path,
    dry_run: bool = False,
) -> TriageResult:
    if not source.exists() and not dry_run:
        return TriageResult(success=False, source_path=str(source), error_msg=f"Source does not exist: {source}")
        
    if target.exists() and not dry_run:
        try:
            if source.resolve() == target.resolve():
                return TriageResult(success=True, source_path=str(source), dest_path=str(target))
        except Exception:
            pass
        return TriageResult(success=False, source_path=str(source), dest_path=str(target), error_msg="Target already exists")

    if not dry_run:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            return TriageResult(success=True, source_path=str(source), dest_path=str(target))
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
        if source.stat().st_ino == link_target.stat().st_ino:
            return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target))
        return TriageResult(success=False, source_path=str(source), hardlink_path=str(link_target), error_msg="Link target exists and is a different file")

    if not dry_run:
        try:
            link_target.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, link_target)
            return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target))
        except Exception as e:
            return TriageResult(success=False, source_path=str(source), hardlink_path=str(link_target), error_msg=str(e))
    else:
        return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target))

async def execute_triage_job(
    job: BatchTriageJob,
    config: AppConfig,
    dry_run: bool = False,
) -> TriageResult:
    anime_name = job.effective_title
    season = job.effective_season
    
    download_dir = Path(config.download_dir)
    storage_dir = Path(config.storage_dir)
    
    mode = "confirm"
    if job.series_config and job.series_config.mode:
        mode = job.series_config.mode
    elif job.default_mode:
        mode = job.default_mode
    else:
        mode = config.default_mode
        
    if mode == "auto":
        link_dir = Path(config.jellyfin_airing_dir) if config.jellyfin_airing_dir else None
    else:
        link_dir = Path(config.jellyfin_collect_dir) if config.jellyfin_collect_dir else None
    
    overall_success = True
    error_msg = None
    
    # Pre-calculate video stems for each episode so subtitles can inherit the complex extension
    from collections import defaultdict
    video_stems_by_ep: dict[int, list[str]] = defaultdict(list)
    for it in job.items:
        if it.ignored:
            continue
        if it.is_video and it.parsed and it.parsed.episode is not None:
            src = download_dir / it.relative_path
            if src.exists():
                video_stems_by_ep[it.parsed.episode].append(src.stem)

    # Process videos and matched subtitles
    for it in job.items:
        if it.ignored:
            continue
            
        source_file = download_dir / it.relative_path
        if not source_file.exists():
            continue
            
        ext = "".join(source_file.suffixes)
        episode = it.parsed.episode if it.parsed else None
        
        # Determine target path
        if episode is not None:
            # We have a clear episode number
            season_str = f"{season:02d}"
            episode_str = f"{episode:02d}"
            target_stem = f"{anime_name} S{season_str}E{episode_str}"
            
            target_filename = None
            for v_stem in video_stems_by_ep.get(episode, []):
                if source_file.name.startswith(v_stem):
                    target_filename = source_file.name.replace(v_stem, target_stem, 1)
                    break
                    
            if not target_filename:
                target_filename = f"{target_stem}{ext}"
                
            if mode == "auto":
                target_file = source_file.parent / target_filename
            else:
                target_file = storage_dir / anime_name / f"Season {season_str}" / target_filename
            
            res = rename_and_move(source_file, target_file, dry_run)
            if not res.success:
                overall_success = False
                error_msg = res.error_msg
                break
                
            # Hardlink if it's a video or subtitle
            if link_dir and (it.is_video or source_file.suffix.lower() in [".ass", ".srt", ".ssa"]):
                if mode == "auto":
                    link_target = link_dir / anime_name / target_filename
                else:
                    link_target = link_dir / anime_name / f"Season {season_str}" / target_filename
                create_hardlink(target_file, link_target, dry_run)
                
        else:
            # No episode detected, it might be a movie or an extra
            if job.source_dir != ".":
                try:
                    rel_to_anime = source_file.relative_to(download_dir / job.source_dir)
                except ValueError:
                    rel_to_anime = Path(source_file.name)
            else:
                rel_to_anime = Path(source_file.name)
                
            if mode == "auto":
                target_file = source_file
            else:
                target_file = storage_dir / anime_name / rel_to_anime
                res = rename_and_move(source_file, target_file, dry_run)
                if not res.success:
                    overall_success = False
                    error_msg = res.error_msg
                    break
            
            if link_dir and (it.is_video or source_file.suffix.lower() in [".ass", ".srt", ".ssa"]):
                # Do not hardlink extras (files in subfolders not named Season) to the TV link directory
                is_extra = False
                if len(rel_to_anime.parts) > 1:
                    for p in rel_to_anime.parts[:-1]:
                        if not p.lower().startswith("season"):
                            is_extra = True
                            break
                            
                if not is_extra:
                    if mode == "auto":
                        link_target = link_dir / anime_name / rel_to_anime
                    else:
                        link_target = link_dir / anime_name / rel_to_anime
                    create_hardlink(target_file, link_target, dry_run)
            
    # Cleanup only in confirm mode
    if mode != "auto":
        source_dir_path = download_dir / job.source_dir
        if source_dir_path.exists() and source_dir_path.is_dir() and job.source_dir != ".":
            for child in source_dir_path.rglob("*"):
                if child.is_file() and child.exists():
                    try:
                        rel_to_anime = child.relative_to(source_dir_path)
                    except ValueError:
                        rel_to_anime = Path(child.name)
                    target_file = storage_dir / anime_name / rel_to_anime
                    rename_and_move(child, target_file, dry_run)
            
            try:
                shutil.rmtree(source_dir_path)
            except:
                pass

    return TriageResult(
        success=overall_success, 
        source_path=job.source_dir, 
        dest_path=str(download_dir / job.source_dir) if mode == "auto" else str(storage_dir / anime_name),
        hardlink_path=str(link_dir / anime_name) if link_dir else None,
        error_msg=error_msg
    )
