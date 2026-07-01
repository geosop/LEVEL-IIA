from cri_leveliia.formatting import count_rate_display, rate_display_from_count


def test_count_rate_round_half_up_boundary_values():
    assert rate_display_from_count(1113, 1200) == "0.928"
    assert rate_display_from_count(75, 1200) == "0.063"
    assert count_rate_display(1113, 1200) == "1113/1200 (0.928)"
    assert count_rate_display(75, 1200) == "75/1200 (0.063)"
