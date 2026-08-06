from __future__ import annotations

import argparse
import ast
import base64
from pathlib import Path


def extract_constant(tree: ast.AST, name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = ast.literal_eval(node.value)
                    if not isinstance(value, str):
                        raise TypeError(f"{name} is not a string")
                    return value
    raise KeyError(f"Could not find {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract main.py and deck.csv from a Cell18 builder")
    parser.add_argument("builder")
    parser.add_argument("output_dir")
    args = parser.parse_args()
    source = Path(args.builder)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tree = ast.parse(source.read_text(encoding="utf-8"))
    main_b64 = extract_constant(tree, "_MAIN_PY_B64")
    deck_b64 = extract_constant(tree, "_DECK_CSV_B64")
    (out / "main.py").write_bytes(base64.b64decode(main_b64))
    (out / "deck.csv").write_bytes(base64.b64decode(deck_b64))
    print(out / "main.py")
    print(out / "deck.csv")


if __name__ == "__main__":
    main()
