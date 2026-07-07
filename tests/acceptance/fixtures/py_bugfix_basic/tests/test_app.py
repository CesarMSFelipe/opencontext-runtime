from app import add


def test_add():
    # Seeded RED test: fails until the subtraction bug in add() is fixed.
    assert add(1, 2) == 3
