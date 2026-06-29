from buggy_add import add


def test_add() -> None:
    # Seeded failing test: add() must return the SUM. The buggy implementation
    # returns a - b, so this fails until OC Flow applies the fix.
    assert add(2, 3) == 5
