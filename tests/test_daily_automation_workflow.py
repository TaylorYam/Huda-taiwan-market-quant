from pathlib import Path

WORKFLOW = Path(".github/workflows/daily-market-automation.yml")


def test_automatic_score_cutoff_refreshes_after_all_source_steps() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    refresh_marker = "name: Refresh automatic score cutoff after collection"
    score_marker = "name: Calculate and persist Market Score"

    assert refresh_marker in text
    assert text.index(refresh_marker) < text.index(score_marker)
    assert '"${GITHUB_EVENT_NAME:-}" == "schedule" || -z "${REQUESTED_AS_OF:-}"' in text
    assert 'echo "AS_OF_TAIPEI=$AS_OF_TAIPEI" >> "$GITHUB_ENV"' in text
    assert 'isoformat(timespec="microseconds")' in text
    assert 'echo "Preserving explicit manual score cutoff: $AS_OF_TAIPEI"' in text


def test_manual_live_run_can_omit_cutoff_and_unavailable_score_fails() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    as_of_input = text.split("      as_of:\n", 1)[1].split("      confirm_write:", 1)[0]
    score_step = text.split("      - name: Calculate and persist Market Score", 1)[1]

    assert "required: false" in as_of_input
    assert 'elif [[ -z "${REQUESTED_AS_OF:-}" ]]; then' in text
    assert "score cutoff will be set after source collection" in text
    assert "--require-available" in score_step
    assert "- Market Score: available and persisted" in score_step
    assert "missing required factors were rejected before persistence" in score_step
    assert 'echo "unavailable" > "$score_status"' in score_step
    assert 'echo "scoring_error" > "$score_status"' in score_step


def test_workflow_has_taipei_midnight_confirmation_and_preserves_guards() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '- cron: "30 8 * * 1-5"' in text
    assert '- cron: "0 14 * * 1-5"' in text
    for utc_weekday in range(1, 6):
        assert f'- cron: "30 16 * * {utc_weekday}"' in text
    for utc_weekday in range(2, 7):
        assert f'- cron: "30 2 * * {utc_weekday}"' in text
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
    assert "10:30 Taipei" in text
    assert "official TWSE calendar could not validate the target date" in text
