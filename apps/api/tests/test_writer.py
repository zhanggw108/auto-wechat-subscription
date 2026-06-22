from ai_radar.writer import rewrite_khazix_style


def test_rewrite_khazix_style_reduces_report_tone_and_adds_human_judgment():
    draft = "本文首先介绍该论文。其次分析方法。最后总结启示。"

    rewritten = rewrite_khazix_style(draft)

    assert "首先" not in rewritten
    assert "其次" not in rewritten
    assert "我的判断" in rewritten
    assert "不是因为" in rewritten
