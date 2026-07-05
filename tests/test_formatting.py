from cri_leveliia.formatting import (
    count_rate_display,
    count_rate_display_4,
    rate_display_from_count,
    rate_display_from_count_4,
)


def test_count_rate_round_half_up_boundary_values():
    assert rate_display_from_count(1113, 1200) == "0.928"
    assert rate_display_from_count(75, 1200) == "0.063"
    assert count_rate_display(1113, 1200) == "1113/1200 (0.928)"
    assert count_rate_display(75, 1200) == "75/1200 (0.063)"


def test_count_rate_four_decimal_display_for_figure_annotations():
    assert rate_display_from_count_4(1113, 1200) == "0.9275"
    assert rate_display_from_count_4(75, 1200) == "0.0625"
    assert rate_display_from_count_4(0, 1200) == "0.0000"
    assert rate_display_from_count_4(1200, 1200) == "1.0000"
    assert count_rate_display_4(1113, 1200) == "1113/1200 (0.9275)"
    assert count_rate_display_4(75, 1200) == "75/1200 (0.0625)"
