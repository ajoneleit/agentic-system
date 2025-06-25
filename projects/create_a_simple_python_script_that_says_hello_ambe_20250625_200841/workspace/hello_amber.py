#!/usr/bin/env python3
"""
A simple Python script that prints a greeting message.
"""


def main():
    """Main function that prints a greeting."""
    try:
        print("Hello, Amber!")
    except Exception as e:
        print(f"An error occurred: {e}")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())