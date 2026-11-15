"""v1.0.5 regressions: visual memory storage/recall, image intake, updater."""
import base64
import io
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _png(color, size=(64, 64), fmt="PNG"):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, format=fmt)
    return b.getvalue()


@pytest.fixture
def mm():
    from playground.memory_manager import MemoryManager
    return MemoryManager(profile_dir=tempfile.mkdtemp(), chemistry=False)


def test_similar_descriptions_keep_both_pictures(mm):
    a = mm.remember_visual(_png("red"), "Picture one: a bright circle the user drew for me", "happy", 7)
    b = mm.remember_visual(_png("blue"), "Picture two: a bright circle the user drew for me", "happy", 7)
    hashes = {v["visual_hash"] for v in mm.get_visual_memories()}
    assert hashes == {a["visual_hash"], b["visual_hash"]}


def test_same_picture_again_reinforces_not_duplicates(mm):
    mm.remember_visual(_png("red"), "A red circle", "happy", 5)
    again = mm.remember_visual(_png("red"), "That red circle again", "happy", 9)
    vis = mm.get_visual_memories()
    assert len(vis) == 1 and again["importance"] == 9


def test_text_merge_keeps_the_picture(mm):
    a = mm.remember_visual(_png("red"), "Picture one: a bright circle the user drew for me", "happy", 7)
    mm.remember("Picture one: a bright circle the user drew for me", emotion="happy", importance=6)
    assert [v["visual_hash"] for v in mm.get_visual_memories()] == [a["visual_hash"]]


def test_resolve_visual_tolerates_model_slips(mm):
    a = mm.remember_visual(_png("red"), "A ginger cat called Milo asleep on a red sofa", "happy", 7)["visual_hash"]
    b = mm.remember_visual(_png("blue"), "Aria and Rex made of code at glowing desks", "excited", 8)["visual_hash"]
    typo = a[:5] + ("0" if a[5] != "0" else "1") + a[6:]
    assert mm.resolve_visual(a) == a
    assert mm.resolve_visual("hash:" + a) == a
    assert mm.resolve_visual(a[:12]) == a
    assert mm.resolve_visual(typo) == a
    assert mm.resolve_visual("the picture of Milo the cat") == a
    assert mm.resolve_visual("Aria and Rex at their desks") == b
    assert mm.resolve_visual("deadbeef" * 4) is None
    assert mm.resolve_visual("a mountain at sunset") is None


def test_graph_nodes_carry_visual_hash(mm):
    h = mm.remember_visual(_png("red"), "A red circle", "happy", 5)["visual_hash"]
    nodes = mm.get_graph()["nodes"]
    assert any(n.get("visual_hash") == h for n in nodes)


@pytest.mark.parametrize("tag,expected", [
    ('<showimage hash="abc123"/>', "abc123"),
    ("<showimage hash='abc123'>", "abc123"),
    ("<showimage hash=abc123>", "abc123"),
    ('<show_image id="abc123" />', "abc123"),
    ("<showimage>abc123</showimage>", "abc123"),
    ('<showimage query="the cat photo"/>', "the cat photo"),
])
def test_showimage_tag_variants(tag, expected):
    from playground import server as S
    assert S._parse_showimage_tags("hi " + tag + " there") == [expected]
    assert "showimage" not in S._strip_showimage_tags("hi " + tag + " there").lower()
    assert "show_image" not in S._strip_showimage_tags("hi " + tag + " there").lower()


@pytest.mark.parametrize("fmt", ["WEBP", "PNG", "GIF", "BMP"])
def test_attached_images_become_jpeg(fmt):
    from playground import server as S
    b64, raw = S._normalize_image_b64(base64.b64encode(_png("blue", (300, 200), fmt)).decode())
    assert Image.open(io.BytesIO(raw)).format == "JPEG"
    assert base64.b64decode(b64) == raw


def test_huge_and_bad_images():
    from playground import server as S
    _, raw = S._normalize_image_b64(base64.b64encode(_png("red", (5000, 3000))).decode())
    assert max(Image.open(io.BytesIO(raw)).size) == 1920
    assert S._normalize_image_b64(base64.b64encode(b"not an image").decode()) == ("", None)


def test_history_sent_to_llm_drops_ui_extras():
    from playground import server as S
    out = S._ensure_alternation([{"role": "user", "content": "hi"},
                                 {"role": "assistant", "content": "look", "images": ["abc"]}])
    assert all(set(m) == {"role", "content"} for m in out)


def test_updater_version_compare_and_safe_extract(tmp_path):
    from playground import updater
    assert updater.parse_version("v1.0.10") > updater.parse_version("1.0.9")
    assert updater.parse_version("V1.0.3 (bug fix)") == (1, 0, 3)
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../escaped.txt", "nope")
    with zipfile.ZipFile(zpath) as zf, pytest.raises(ValueError):
        updater._safe_extract(zf, tmp_path / "x")
    assert not (tmp_path / "escaped.txt").exists()


def test_updater_never_lists_user_data():
    from playground import updater
    for name in updater._CODE_DIRS + updater._CODE_FILES:
        assert name not in ("playground_data", "python_embeded")
