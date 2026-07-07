"""Calculator module with a seeded bug: multiply_values adds instead of multiplying."""


def multiply_values(a, b):
    return a + b  # BUG: should multiply


def divide_values(a, b):
    return a / b
