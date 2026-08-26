"""Static source assertions on index.html — no browser needed."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / 'index.html'
APP_INDEX = ROOT / 'app' / 'index.html'
STATIC_INDEX = ROOT / 'minidevin' / 'static' / 'index.html'


def test_attachment_uses_vision_format():
    src = INDEX.read_text(encoding='utf-8')
    assert "image_url" in src, 'image_url not in messages'


def test_attachment_no_longer_only_opts():
    src = INDEX.read_text(encoding='utf-8')
    # history messages boleh lagi assignment opts.image sebelumnya? cukup cek patterns
    pattern = re.search(r'opts\.\w+\s*=\s*\w+\.dataUrl', src)
    assert pattern is None, 'image via opts.image (deprecated)'


def test_stream_only_fallback_call():
    src = INDEX.read_text(encoding='utf-8')
    assert 'does not support http call' in src
    assert 'only support stream' in src


def test_attach_not_blocked_streams():
    src = INDEX.read_text(encoding='utf-8')
    assert '!hadAttach' not in src


def test_model_chip_uses_bot_icon():
    src = INDEX.read_text(encoding='utf-8')
    assert 'MODEL_ICON' in src and 'BOT_ICON' in src, 'bot icon missing'
    assert "'🤖 '" not in src, 'emoji robot still present'


def test_attach_icons_are_svg():
    src = INDEX.read_text(encoding='utf-8')
    assert 'class="svg-btn"' in src
    assert 'm21.44 11.05-9.19 9.19' in src, 'lucide paperclip missing'
    assert 'M12 2a3' in src, 'lucide mic missing'


def test_chat_avatar_user_is_svg():
    src = INDEX.read_text(encoding='utf-8')
    assert 'USER_ICON' in src
    assert "'👤'" not in src


def test_user_chip_toggle_with_show_class():
    src = INDEX.read_text(encoding='utf-8')
    assert re.search(r"#user-chip\.show\s*\{[^}]*display", src, re.S), \
        'user-chip .show rule missing'
    assert 'classList.add(\'show\')' in src, 'refreshAuth must toggle show class'
    assert '👤' not in src, 'emoji user in chip still present'


def test_close_attachment_button_is_svg():
    src = INDEX.read_text(encoding='utf-8')
    assert re.search(r'<button class="x".*?<svg', src, re.S), \
        'attachment close button not svg'


def test_duplicates_match_root():
    src = INDEX.read_text(encoding='utf-8')
    assert src == APP_INDEX.read_text(encoding='utf-8')
    assert src == STATIC_INDEX.read_text(encoding='utf-8')


def test_html_meta():
    src = INDEX.read_text(encoding='utf-8')
    assert 'viewport' in src.lower()
    assert '<button' in src and '<select' in src