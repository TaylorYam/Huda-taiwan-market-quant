from scripts.check_persistence_gate import (
    check_market_score_migration,
    check_postgres_migration,
    run_local_smoke_test,
)


def test_local_persistence_gate() -> None:
    check_postgres_migration()
    check_market_score_migration()
    run_local_smoke_test()
