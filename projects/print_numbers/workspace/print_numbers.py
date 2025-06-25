#!/usr/bin/env python3
"""Script to print numbers from 1 to 10."""


def print_numbers():
    """Print numbers from 1 to 10 using a for loop."""
    try:
        for number in range(1, 11):
            print(number)
    except Exception as e:
        print(f"An error occurred: {e}")
        raise


if __name__ == "__main__":
    print_numbers()