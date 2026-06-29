"""A tiny sample module so first-run indexing has real symbols to ingest."""


def greet(name: str) -> str:
    return f"hello, {name}"


class Counter:
    def __init__(self) -> None:
        self.value = 0

    def increment(self) -> int:
        self.value += 1
        return self.value
