import os

from media_importer.core.db import (
    create_subtitles,
    create_task,
    get_subtitles_by_task,
    get_task,
    init_db,
    update_subtitle,
    update_task,
)
from media_importer.features.import_flow.bundle_recovery import (
    recover_interrupted_bundle,
)
from media_importer.infrastructure.filesystem import hash_file


def _setup(tmp_path):
    library = tmp_path / "library"
    source = tmp_path / "source"
    library.mkdir()
    source.mkdir()
    conn = init_db(str(tmp_path / "tasks.db"))
    task = create_task(
        conn,
        str(source / "Movie.mkv"),
        "Movie.mkv",
        task_id="restart-bundle",
    )
    update_task(conn, task["task_id"], status="PENDING", stage="RUNNING")
    config = {
        "source_dir": str(source),
        "library_roots": [
            {"id": "movies", "name": "电影", "path": str(library), "enabled": True}
        ],
    }
    return conn, config, source, library, task["task_id"]


def _manifest(source, library, task_id, *, locations):
    source_video = source / "Movie.mkv"
    source_subtitle = source / "Movie.zh.srt"
    video_dest = library / "Movie (2020).mkv"
    subtitle_dest = library / "Movie (2020).zh.srt"
    members = []
    for index, (kind, source_path, dest_path, content) in enumerate((
        ("video", source_video, video_dest, b"video"),
        ("subtitle", source_subtitle, subtitle_dest, b"subtitle"),
    ), start=1):
        stage_path = type(dest_path)(f"{dest_path}.{task_id}.{index}.bundle.tmp")
        source_path.write_bytes(content)
        selected = {"stage": stage_path, "dest": dest_path}.get(locations[kind])
        if selected is not None:
            selected.write_bytes(content)
        members.append({
            "kind": kind,
            "source_path": str(source_path),
            "stage_path": str(stage_path),
            "dest_path": str(dest_path),
            "fingerprint": hash_file(str(source_path)),
            "transfer_mode": "copy",
            "state": locations[kind],
        })
    return members


def test_restart_before_video_publish_cleans_task_owned_target_staging(tmp_path):
    conn, config, source, library, task_id = _setup(tmp_path)
    manifest = _manifest(
        source,
        library,
        task_id,
        locations={"video": "stage", "subtitle": "dest"},
    )
    update_task(
        conn,
        task_id,
        bundle_state="PUBLISHING",
        bundle_manifest=manifest,
        video_path=manifest[0]["source_path"],
        file_location="source",
    )

    result = recover_interrupted_bundle(get_task(conn, task_id), config, conn)

    assert result and result.state == "ROLLED_BACK"
    assert os.path.isfile(manifest[0]["source_path"])
    assert os.path.isfile(manifest[1]["source_path"])
    assert list(library.iterdir()) == []
    recovered = get_task(conn, task_id)
    assert recovered["status"] == "FAILED"
    assert recovered["file_location"] == "source"
    assert recovered["bundle_committed"] == 0
    conn.close()


def test_restart_direct_copy_removes_only_task_owned_target_copies(tmp_path):
    conn, config, _temp, library, task_id = _setup(tmp_path)
    source_video = tmp_path / "source" / "Movie.mkv"
    source_subtitle = tmp_path / "source" / "Movie.zh.srt"
    source_video.write_bytes(b"video")
    source_subtitle.write_bytes(b"subtitle")
    destinations = (
        ("video", source_video, library / "Movie (2020).mkv"),
        ("subtitle", source_subtitle, library / "Movie (2020).zh.srt"),
    )
    manifest = []
    for index, (kind, source, destination) in enumerate(destinations, start=1):
        stage = type(destination)(f"{destination}.{task_id}.{index}.bundle.tmp")
        target = stage if kind == "video" else destination
        target.write_bytes(source.read_bytes())
        manifest.append({
            "kind": kind,
            "source_path": str(source),
            "stage_path": str(stage),
            "dest_path": str(destination),
            "fingerprint": hash_file(str(source)),
            "transfer_mode": "copy",
            "state": "staged" if kind == "video" else "published",
        })
    update_task(
        conn,
        task_id,
        bundle_state="PUBLISHING",
        bundle_manifest=manifest,
        video_path=str(source_video),
        file_location="source",
    )

    result = recover_interrupted_bundle(get_task(conn, task_id), config, conn)

    assert result and result.state == "ROLLED_BACK"
    assert source_video.read_bytes() == b"video"
    assert source_subtitle.read_bytes() == b"subtitle"
    assert list(library.iterdir()) == []
    recovered = get_task(conn, task_id)
    assert recovered["file_location"] == "source"
    conn.close()


def test_restart_direct_copy_cleans_unjournaled_partial_without_hashing_it(tmp_path):
    conn, config, _temp, library, task_id = _setup(tmp_path)
    source_video = tmp_path / "source" / "Movie.mkv"
    source_video.write_bytes(b"video")
    destination = library / "Movie (2020).mkv"
    stage = type(destination)(f"{destination}.{task_id}.1.bundle.tmp")
    partial = type(destination)(f"{stage}.copying")
    partial.write_bytes(b"partial")
    manifest = [{
        "kind": "video",
        "source_path": str(source_video),
        "stage_path": str(stage),
        "dest_path": str(destination),
        "fingerprint": "",
        "transfer_mode": "copy",
        "state": "source",
    }]
    update_task(
        conn,
        task_id,
        bundle_state="PREPARED",
        bundle_manifest=manifest,
        video_path=str(source_video),
        file_location="source",
    )

    result = recover_interrupted_bundle(get_task(conn, task_id), config, conn)

    assert result and result.state == "ROLLED_BACK"
    assert source_video.read_bytes() == b"video"
    assert not partial.exists()
    assert list(library.iterdir()) == []
    conn.close()


def test_restart_after_video_publish_recovers_committed_bundle_without_rewrite(tmp_path):
    conn, config, source, library, task_id = _setup(tmp_path)
    manifest = _manifest(
        source,
        library,
        task_id,
        locations={"video": "dest", "subtitle": "dest"},
    )
    subtitle_source = tmp_path / "source" / "Movie.zh.srt"
    subtitle_source.write_bytes(b"subtitle")
    rows = create_subtitles(conn, task_id, [str(subtitle_source)])
    update_subtitle(
        conn,
        rows[0]["id"],
        planned_filename="Movie (2020).zh.srt",
        target_path=manifest[1]["source_path"],
    )
    update_task(
        conn,
        task_id,
        bundle_state="COMMITTED",
        bundle_manifest=manifest,
        bundle_committed=1,
        video_path=manifest[0]["source_path"],
        file_location="source",
    )

    result = recover_interrupted_bundle(get_task(conn, task_id), config, conn)

    assert result and result.state == "COMMITTED_RECOVERED"
    recovered = get_task(conn, task_id)
    assert recovered["status"] == "SUCCESS"
    assert recovered["import_success"] == 1
    assert recovered["import_video_path"] == manifest[0]["dest_path"]
    assert recovered["bundle_committed"] == 1
    assert recovered["source_cleanup_status"] == "SKIPPED"
    assert recovered["source_disposition"] == "kept"
    assert "保留来源" in recovered["source_disposition_message"]
    assert source.joinpath("Movie.mkv").read_bytes() == b"video"
    subtitle = get_subtitles_by_task(conn, task_id)[0]
    assert subtitle["status"] == "SUCCESS"
    assert subtitle["import_path"] == manifest[1]["dest_path"]
    assert (library / "Movie (2020).mkv").read_bytes() == b"video"
    conn.close()


def test_restart_with_video_marker_and_missing_subtitle_preserves_library_for_review(tmp_path):
    conn, config, source, library, task_id = _setup(tmp_path)
    manifest = _manifest(
        source,
        library,
        task_id,
        locations={"video": "dest", "subtitle": "dest"},
    )
    os.unlink(manifest[1]["dest_path"])
    update_task(
        conn,
        task_id,
        bundle_state="COMMITTED",
        bundle_manifest=manifest,
        bundle_committed=1,
    )

    result = recover_interrupted_bundle(get_task(conn, task_id), config, conn)

    assert result and result.state == "RECOVERY_REQUIRED"
    assert (library / "Movie (2020).mkv").read_bytes() == b"video"
    recovered = get_task(conn, task_id)
    assert recovered["status"] == "FAILED"
    assert recovered["bundle_state"] == "RECOVERY_REQUIRED"
    conn.close()


def test_restart_rejects_manifest_that_claims_foreign_stage_path(tmp_path):
    conn, config, source, library, task_id = _setup(tmp_path)
    manifest = _manifest(
        source,
        library,
        task_id,
        locations={"video": "source", "subtitle": "source"},
    )
    foreign = library / "foreign.bundle.tmp"
    foreign.write_bytes(b"do-not-touch")
    manifest[0]["stage_path"] = str(foreign)
    update_task(
        conn,
        task_id,
        bundle_state="PREPARED",
        bundle_manifest=manifest,
    )

    result = recover_interrupted_bundle(get_task(conn, task_id), config, conn)

    assert result and result.state == "RECOVERY_REQUIRED"
    assert foreign.read_bytes() == b"do-not-touch"
    assert os.path.isfile(manifest[0]["source_path"])
    conn.close()


def test_restart_ignores_normally_completed_bundle_journal(tmp_path):
    conn, config, source, library, task_id = _setup(tmp_path)
    manifest = _manifest(
        source,
        library,
        task_id,
        locations={"video": "dest", "subtitle": "dest"},
    )
    update_task(
        conn,
        task_id,
        status="SUCCESS",
        stage="DONE",
        import_success=1,
        bundle_state="COMMITTED",
        bundle_manifest=manifest,
        bundle_committed=1,
        video_path=manifest[0]["dest_path"],
        import_video_path=manifest[0]["dest_path"],
        file_location="import",
    )

    before = get_task(conn, task_id)
    result = recover_interrupted_bundle(before, config, conn)

    assert result is None
    after = get_task(conn, task_id)
    assert after["status"] == "SUCCESS"
    assert after["bundle_state"] == "COMMITTED"
    assert after["import_video_path"] == manifest[0]["dest_path"]
    conn.close()


def _reorganization_manifest(library, task_id, *, locations):
    fallback = library / "待整理"
    target = library / "电影" / "小姐"
    fallback.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    pairs = (
        ("video", fallback / "小姐.2016.mkv", target / "小姐.2016.mkv", b"video"),
        ("subtitle", fallback / "小姐.2016.zh.srt", target / "小姐.2016.zh.srt", b"subtitle"),
    )
    members = []
    for index, (kind, source_path, dest_path, content) in enumerate(pairs, start=1):
        stage_path = type(dest_path)(f"{dest_path}.{task_id}.{index}.bundle.tmp")
        selected = {"source": source_path, "stage": stage_path, "dest": dest_path}[locations[kind]]
        selected.write_bytes(content)
        members.append({
            "kind": kind,
            "source_path": str(source_path),
            "stage_path": str(stage_path),
            "dest_path": str(dest_path),
            "fingerprint": hash_file(str(selected)),
            "state": locations[kind],
        })
    return members


def _mark_reorganization(conn, task_id, library):
    parent = create_task(
        conn,
        str(library / "待整理" / "小姐.2016.mkv"),
        "小姐.2016.mkv",
        task_id="parent-fallback",
    )
    update_task(
        conn,
        parent["task_id"],
        status="SUCCESS",
        stage="DONE",
        import_success=1,
        organization_status="FALLBACK_PENDING",
    )
    update_task(
        conn,
        task_id,
        task_kind="REORGANIZE",
        parent_task_id=parent["task_id"],
        used_fallback=0,
        source_cleanup_status="SKIPPED",
    )
    return parent["task_id"]


def test_restart_before_reorganization_publish_rolls_back_to_original_library(tmp_path):
    conn, config, _temp, library, task_id = _setup(tmp_path)
    parent_id = _mark_reorganization(conn, task_id, library)
    manifest = _reorganization_manifest(
        library,
        task_id,
        locations={"video": "stage", "subtitle": "dest"},
    )
    update_task(
        conn,
        task_id,
        bundle_state="PUBLISHING",
        bundle_manifest=manifest,
        video_path=manifest[0]["source_path"],
        file_location="import",
    )

    result = recover_interrupted_bundle(get_task(conn, task_id), config, conn)

    assert result and result.state == "ROLLED_BACK"
    assert os.path.isfile(manifest[0]["source_path"])
    assert os.path.isfile(manifest[1]["source_path"])
    recovered = get_task(conn, task_id)
    assert recovered["status"] == "FAILED"
    assert recovered["file_location"] == "import"
    assert get_task(conn, parent_id)["organization_status"] == "FALLBACK_PENDING"
    conn.close()


def test_restart_after_reorganization_commit_resolves_linked_parent(tmp_path):
    conn, config, _temp, library, task_id = _setup(tmp_path)
    parent_id = _mark_reorganization(conn, task_id, library)
    manifest = _reorganization_manifest(
        library,
        task_id,
        locations={"video": "dest", "subtitle": "dest"},
    )
    subtitle_source = library / "待整理" / "小姐.2016.zh.srt"
    subtitle_source.write_bytes(b"subtitle-source-row")
    rows = create_subtitles(conn, task_id, [str(subtitle_source)])
    update_subtitle(
        conn,
        rows[0]["id"],
        planned_filename="小姐.2016.zh.srt",
    )
    update_task(
        conn,
        task_id,
        bundle_state="COMMITTED",
        bundle_manifest=manifest,
        bundle_committed=1,
        video_path=manifest[0]["source_path"],
        file_location="import",
    )

    result = recover_interrupted_bundle(get_task(conn, task_id), config, conn)

    assert result and result.state == "COMMITTED_RECOVERED"
    recovered = get_task(conn, task_id)
    assert recovered["status"] == "SUCCESS"
    assert recovered["organization_status"] == "ORGANIZED"
    assert recovered["source_cleanup_status"] == "SKIPPED"
    assert recovered["source_disposition"] == ""
    assert recovered["source_disposition_message"] == ""
    parent = get_task(conn, parent_id)
    assert parent["organization_status"] == "ORGANIZED"
    assert parent["reorganized_by_task_id"] == task_id
    conn.close()
