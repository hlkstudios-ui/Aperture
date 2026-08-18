"""Read one literal dotenv value for shell scripts without sourcing executable text."""

import argparse
from pathlib import Path


def read(path: Path, label: str) -> str:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid line {number}")
        key, value = line.split("=", 1)
        if key in values:
            raise ValueError(f"duplicate label: {key}")
        values[key] = value
    if label not in values or not values[label]:
        raise ValueError(f"missing label: {label}")
    return values[label]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    print(read(args.input, args.label))


if __name__ == "__main__":
    main()
