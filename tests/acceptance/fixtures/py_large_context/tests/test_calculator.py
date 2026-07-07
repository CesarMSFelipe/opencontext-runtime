from calculator import multiply_values


def test_multiply_values():
    # Seeded RED test: fails until the multiply bug in calculator.py is fixed.
    assert multiply_values(3, 4) == 12
