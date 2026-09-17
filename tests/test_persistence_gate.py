from scripts.check_persistence_gate import (
    check_postgres_migration,
    run_local_smoke_test,
)


def test_local_persistence_gate() -> None:
    check_postgres_migration()
    run_local_smoke_test()
