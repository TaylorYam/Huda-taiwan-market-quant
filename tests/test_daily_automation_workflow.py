from pathlib import Path

WORKFLOW = Path(".github/workflows/daily-market-automation.yml")


def test_scheduled_score_cutoff_refreshes_after_all_source_steps() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    refresh_marker = "name: Refresh scheduled score cutoff after collection"
    score_marker = "name: Calculate and persist Market Score"

    assert refresh_marker in text
    assert text.index(refresh_marker) < text.index(score_marker)
    assert "if: ${{ github.event_name == 'schedule' }}" in text
    assert 'echo "AS_OF_TAIPEI=$AS_OF_TAIPEI" >> "$GITHUB_ENV"' in text


def test_workflow_has_taipei_midnight_confirmation_and_preserves_guards() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '- cron: "30 8 * * 1-5"' in text
    assert '- cron: "0 14 * * 1-5"' in text
    for utc_weekday in range(1, 6):
        assert f'- cron: "30 16 * * {utc_weekday}"' in text
    assert (
        'python -m src.automation.scheduled_target \\\n              --schedule "$SCHEDULE_CRON"'
        in text
    )
    assert (
        'python -m scripts.collect_taifex_institutional --write --expected-date "$TARGET_DATE"'
        in text
    )
    assert "group: daily-market-automation" in text
    assert "institutional snapshot gate" in text
    assert "official institutional futures observation_date mismatch:" in text
    assert "the mismatched snapshot was rejected before persistence" in text
    assert "Market Score: not run" in text
    assert "preceding TWSE trading date" in text
    assert "official TWSE calendar could not validate the target date" in text
