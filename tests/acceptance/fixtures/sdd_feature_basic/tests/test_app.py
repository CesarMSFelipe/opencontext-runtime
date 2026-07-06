from app import greet


def test_greet():
    assert greet("bob") == "hello bob"
