from pathlib import Path
import json
import pytest
from vision_foundation.media import MediaStore


def test_retention_excludes_active_clip_and_removes_sidecar(tmp_path, store):
    media = MediaStore(tmp_path/'evidence', store)
    media.max_files = 1
    old = media.directory/'old.jpg'
    old.write_bytes(b'old')
    old.with_suffix('.json').write_text('{}')
    newer = media.directory/'new.jpg'
    newer.write_bytes(b'new')
    import os
    os.utime(old, (1,1)); os.utime(newer, (2,2))
    partial=media.directory/'cam_clip_job.part.avi'
    partial.write_bytes(b'in progress')
    media._retention()
    assert not old.exists() and not old.with_suffix('.json').exists()
    assert newer.exists() and partial.exists()


def test_startup_removes_only_interrupted_owned_clips(tmp_path, store):
    path=tmp_path/'evidence';path.mkdir()
    partial=path/'cam_clip_abcd.part.avi';partial.write_bytes(b'partial')
    final=path/'cam_clip_efgh.avi';final.write_bytes(b'committed')
    unrelated=path/'personal.part.avi';unrelated.write_bytes(b'not ours')
    media=MediaStore(path,store)
    assert not partial.exists() and final.exists() and unrelated.exists()
