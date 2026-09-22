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
