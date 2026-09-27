from helpdesk_toolkit import diskcheck
from helpdesk_toolkit.utils import Status


def _make_file(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_find_largest_files_orders_by_size(tmp_path):
    _make_file(tmp_path / "small.txt", 10)
    _make_file(tmp_path / "videos" / "big.mp4", 5000)
    _make_file(tmp_path / "docs" / "medium.pdf", 800)

    largest, skipped = diskcheck.find_largest_files(tmp_path, top_n=2)

    assert [e.size for e in largest] == [5000, 800]
    assert largest[0].path.endswith("big.mp4")
    assert skipped == 0


def test_find_largest_files_respects_min_size(tmp_path):
    _make_file(tmp_path / "a.bin", 100)
    _make_file(tmp_path / "b.bin", 2000)
    largest, _ = diskcheck.find_largest_files(tmp_path, top_n=10, min_size=1000)
    assert len(largest) == 1


def test_folder_sizes_totals_subfolders(tmp_path):
    _make_file(tmp_path / "Downloads" / "a.iso", 3000)
    _make_file(tmp_path / "Downloads" / "nested" / "b.zip", 1000)
    _make_file(tmp_path / "Documents" / "c.docx", 500)

    folders = diskcheck.folder_sizes(tmp_path)

    assert folders[0].path.endswith("Downloads") and folders[0].size == 4000
    assert folders[1].path.endswith("Documents") and folders[1].size == 500


def test_folder_sizes_missing_folder_returns_empty(tmp_path):
    assert diskcheck.folder_sizes(tmp_path / "nope") == []


def test_check_disks_returns_results_for_this_machine():
    results = diskcheck.check_disks()
    assert results, "expected at least one drive"
    assert all(r.status in {Status.PASS, Status.WARN, Status.FAIL} for r in results)
