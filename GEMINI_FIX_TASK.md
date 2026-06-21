# AnimeRenamer v2 — 验收失败报告 & 修复任务

> **本文件是给 Gemini 的工作指令。请按顺序完成所有任务，最后运行验证脚本确认全部通过。**

---

## 当前状态

| 模块 | 状态 |
|---|---|
| `backend/parser.py` + `models.py` | ✅ 75/75 测试通过 |
| `backend/triage.py` | ❌ Bug 1：接口不匹配，运行时崩溃 |
| `backend/main.py` | ❌ Bug 2：字段名引用错误，修改 job 时崩溃 |
| `backend/config.py` | ⚠️ Bug 3：需确认 AppConfig 可无环境变量初始化 |
| `backend/tests/test_triage.py` | ❌ 不存在，需补写 |

---

## Bug 1：TriageResult 模型与 triage.py 接口不匹配（严重）

### 症状

运行以下代码会崩溃：

```python
from backend.triage import create_hardlink
from pathlib import Path
create_hardlink(Path('/tmp/a.mkv'), Path('/tmp/b/a.mkv'))
```

错误信息：
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for TriageResult
dest_path
  Field required [type=missing, ...]
```

### 根本原因

`backend/models.py` 中 `TriageResult.dest_path` 是必填字段（`str`，无默认值），
但 `backend/triage.py` 在 `create_hardlink` 的成功路径里没有传 `dest_path`。

同时，`triage.py` 多处传了 `error_msg=` 参数，但该字段在 `TriageResult` 里根本不存在。

### 修复方案

修改 `backend/models.py` 的 `TriageResult` 类，将 `dest_path` 改为可选，并新增 `error_msg` 字段：

```python
class TriageResult(BaseModel):
    success: bool = Field(..., description="True if the operation succeeded")
    source_path: str = Field(..., description="Absolute path to the source file")
    dest_path: str | None = Field(None, description="Absolute path to the renamed destination")
    hardlink_path: str | None = Field(None, description="Absolute path to the hardlink (if created)")
    error_msg: str | None = Field(None, description="Error message if operation failed")
    rollback_info: dict[str, Any] = Field(
        default_factory=dict,
        description="Data required to roll back this operation",
    )
    model_config = {"frozen": True}
```

不需要改 triage.py，只改 models.py。

---

## Bug 2：main.py 引用了错误的 TriageJob 字段名（严重）

### 根本原因

`backend/main.py` 的 `patch_job` 函数里写的是：
```python
job.title_override = updates["title"]
job.season_override = updates["season"]
job.episode_override = updates["episode"]
```

但 `backend/models.py` 里 `TriageJob` 的字段实际叫：
```python
override_title: str | None = ...
override_season: int | None = ...
override_episode: int | None = ...
```

另外，`TriageJob` 的 `model_config` 需要检查：如果是 `frozen=True`，则不能直接赋值 `job.status = ...`，
需要改为 `frozen=False`（status 必须可在运行时更新）。

### 修复方案

**第一步**：确认 `backend/models.py` 里 `TriageJob` 的 model_config，如果是 `{"frozen": True}` 改为 `{"frozen": False}`。

**第二步**：修改 `backend/main.py` 的 `patch_job` 函数，使用正确字段名：
```python
@app.patch("/api/queue/{job_id}")
async def patch_job(job_id: str, updates: dict[str, Any]) -> TriageJob:
    if job_id not in queue:
        raise HTTPException(status_code=404, detail="Job not found")
    job = queue[job_id]
    if "title" in updates:
        job.override_title = updates["title"]
    if "season" in updates:
        job.override_season = updates["season"]
    if "episode" in updates:
        job.override_episode = updates["episode"]
    return job
```

---

## Bug 3：AppConfig 需要在无环境变量时也能初始化（中等）

### 验证命令

```bash
python -c "
from backend.config import load_config
c = load_config('/nonexistent/series_config.yaml')
print('tmdb_api_key:', repr(c.tmdb_api_key))
print('OK')
"
```

期望输出：
```
tmdb_api_key: ''
OK
```

如果崩溃，修复 `AppConfig.tmdb_api_key` 确保有 `default=""`。

---

## 补写测试：`backend/tests/test_triage.py`

必须新建此文件，覆盖以下场景（用 `tmp_path` fixture，不依赖真实目录）：

```python
import pytest
from pathlib import Path
from backend.triage import build_target_path, rename_and_move, create_hardlink, rollback


class TestBuildTargetPath:
    def test_format(self):
        result = build_target_path("无职转生", 2, 13, "mkv", Path("/anime"))
        assert result == Path("/anime/无职转生/Season 2/无职转生 S02E13.mkv")

    def test_season_zero_padding(self):
        result = build_target_path("TestAnime", 1, 5, "mkv", Path("/anime"))
        assert "S01E05" in result.name

    def test_episode_zero_padding(self):
        result = build_target_path("TestAnime", 1, 1, "mkv", Path("/anime"))
        assert "S01E01" in result.name


class TestRenameAndMove:
    def test_dry_run_always_succeeds(self, tmp_path):
        src = tmp_path / "nonexistent.mkv"
        dst = tmp_path / "subdir" / "target.mkv"
        res = rename_and_move(src, dst, dry_run=True)
        assert res.success is True

    def test_moves_file(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dst = tmp_path / "sub" / "dest.mkv"
        res = rename_and_move(src, dst, dry_run=False)
        assert res.success is True
        assert dst.exists()
        assert not src.exists()

    def test_creates_parent_dirs(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dst = tmp_path / "a" / "b" / "c" / "dest.mkv"
        res = rename_and_move(src, dst, dry_run=False)
        assert res.success is True
        assert dst.exists()

    def test_refuses_existing_target(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dst = tmp_path / "dest.mkv"
        dst.write_text("existing")
        res = rename_and_move(src, dst, dry_run=False)
        assert res.success is False
        assert src.exists()

    def test_missing_source_fails(self, tmp_path):
        src = tmp_path / "nonexistent.mkv"
        dst = tmp_path / "dest.mkv"
        res = rename_and_move(src, dst, dry_run=False)
        assert res.success is False


class TestCreateHardlink:
    def test_creates_hardlink(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        link = tmp_path / "sub" / "link.mkv"
        res = create_hardlink(src, link, dry_run=False)
        assert res.success is True
        assert link.exists()
        assert src.stat().st_ino == link.stat().st_ino

    def test_dry_run_succeeds(self, tmp_path):
        src = tmp_path / "source.mkv"
        link = tmp_path / "link.mkv"
        res = create_hardlink(src, link, dry_run=True)
        assert res.success is True

    def test_refuses_overwrite_different_file(self, tmp_path):
        src = tmp_path / "a.mkv"
        src.write_text("data A")
        other = tmp_path / "b.mkv"
        other.write_text("data B")
        res = create_hardlink(src, other, dry_run=False)
        assert res.success is False
        assert src.exists()
        assert other.exists()

    def test_idempotent_same_inode(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        link = tmp_path / "link.mkv"
        create_hardlink(src, link, dry_run=False)
        res = create_hardlink(src, link, dry_run=False)
        assert res.success is True


class TestRollback:
    def test_rollback_move(self, tmp_path):
        src = tmp_path / "original.mkv"
        src.write_text("data")
        dst = tmp_path / "moved.mkv"
        mv_res = rename_and_move(src, dst, dry_run=False)
        assert dst.exists()
        ok = rollback(mv_res)
        assert ok is True
        assert src.exists()
        assert not dst.exists()

    def test_rollback_link(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        link = tmp_path / "link.mkv"
        link_res = create_hardlink(src, link, dry_run=False)
        assert link.exists()
        ok = rollback(link_res)
        assert ok is True
        assert not link.exists()
        assert src.exists()

    def test_rollback_empty_info_is_noop(self):
        from backend.models import TriageResult
        r = TriageResult(success=True, source_path="/foo")
        ok = rollback(r)
        assert ok is True
```

---

## 最终验证步骤（必须全部通过才算完成）

### 步骤 1：运行所有测试

```bash
cd /workspaces/anime_triage
python -m pytest backend/tests/ -v
```

期望：所有测试绿色，0 个失败

### 步骤 2：运行验收脚本

```bash
cd /workspaces/anime_triage && python -c "
import sys
from backend.triage import build_target_path, rename_and_move, create_hardlink, rollback
from backend.models import TriageResult
from backend.config import load_config
from pathlib import Path
import tempfile

errors = []

try:
    r = TriageResult(success=False, source_path='/foo', error_msg='test')
    assert r.error_msg == 'test'
    print('✅ TriageResult.error_msg 字段存在')
except Exception as e:
    errors.append(f'❌ TriageResult.error_msg: {e}')

try:
    r = TriageResult(success=True, source_path='/foo', hardlink_path='/bar')
    print('✅ TriageResult.dest_path 是可选字段')
except Exception as e:
    errors.append(f'❌ TriageResult.dest_path optional: {e}')

with tempfile.TemporaryDirectory() as d:
    src = Path(d) / 'source.mkv'
    src.write_text('data')
    link = Path(d) / 'sub' / 'link.mkv'
    try:
        res = create_hardlink(src, link, dry_run=False)
        assert res.success and src.stat().st_ino == link.stat().st_ino
        print('✅ create_hardlink 正常工作')
    except Exception as e:
        errors.append(f'❌ create_hardlink: {e}')

with tempfile.TemporaryDirectory() as d:
    src = Path(d) / 'a.mkv'
    src.write_text('A')
    other = Path(d) / 'b.mkv'
    other.write_text('B')
    try:
        res = create_hardlink(src, other, dry_run=False)
        assert not res.success
        print('✅ create_hardlink 拒绝覆盖不同文件')
    except Exception as e:
        errors.append(f'❌ create_hardlink refuse: {e}')

with tempfile.TemporaryDirectory() as d:
    src = Path(d) / 'orig.mkv'
    src.write_text('data')
    dst = Path(d) / 'moved.mkv'
    mv = rename_and_move(src, dst)
    ok = rollback(mv)
    assert ok and src.exists()
    print('✅ rollback 成功还原')

try:
    c = load_config('/nonexistent/path.yaml')
    assert isinstance(c.tmdb_api_key, str)
    print('✅ load_config 无 YAML 时正常初始化')
except Exception as e:
    errors.append(f'❌ load_config: {e}')

try:
    from backend.main import app
    print('✅ backend.main 导入成功')
except Exception as e:
    errors.append(f'❌ backend.main: {e}')

print()
if errors:
    for e in errors: print(e)
    sys.exit(1)
else:
    print('🎉 所有验收测试通过！')
"
```

### 步骤 3：Git commit

```bash
cd /workspaces/anime_triage
git add -A
git commit -m "fix: 修复 TriageResult 字段缺失、接口不匹配 bug，补写 test_triage.py"
```

---

## 完成标准

以下全部达到才算完成：

- [ ] `python -m pytest backend/tests/ -v` 全部绿色，0 个失败
- [ ] 验收脚本 7 个 ✅ 全部输出，无 ❌
- [ ] `backend/tests/test_triage.py` 文件存在
- [ ] git commit 完成
