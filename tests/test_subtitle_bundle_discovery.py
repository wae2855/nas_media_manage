from media_importer.features.import_flow.scan_service import FileScanner


def _scanner():
    return FileScanner({
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt", ".ass"],
    })


def test_subtitle_matching_uses_normalized_boundary_not_contains(tmp_path):
    movie = tmp_path / "Movie.mkv"
    movie_two = tmp_path / "Movie.Extended.mkv"
    correct = tmp_path / "Movie.zh.srt"
    other = tmp_path / "Movie.Extended.en.srt"
    for path in (movie, movie_two, correct, other):
        path.write_bytes(b"x")

    groups = _scanner().scan_path(str(tmp_path))
    by_video = {group["video_file"]: group["subtitle_files"] for group in groups}
    assert by_video["Movie.mkv"] == [str(correct)]
    assert by_video["Movie.Extended.mkv"] == [str(other)]


def test_subtitle_subdirectory_is_supported_but_unrelated_nested_dir_is_not(tmp_path):
    movie_dir = tmp_path / "Film"
    subtitle_dir = movie_dir / "Subs"
    unrelated = movie_dir / "Extras"
    subtitle_dir.mkdir(parents=True)
    unrelated.mkdir()
    movie = movie_dir / "Film.mkv"
    correct = subtitle_dir / "Film.eng.srt"
    ignored = unrelated / "Film.zh.srt"
    for path in (movie, correct, ignored):
        path.write_bytes(b"x")

    groups = _scanner().scan_path(str(tmp_path))
    assert groups[0]["subtitle_files"] == [str(correct)]
