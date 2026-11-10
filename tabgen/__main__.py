"""CLI: python3 -m tabgen build <spec.json> [-o out.twb] [--open]"""
import argparse
import json
import os
import subprocess
import sys

from .compiler import build


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tabgen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="compile a spec into a .twb")
    b.add_argument("spec")
    b.add_argument("-o", "--out", help="output .twb (default: next to the spec)")
    b.add_argument("--open", action="store_true", help="open the result in Tableau Desktop")
    i = sub.add_parser("introspect", help="print spec datasources (connections, columns, calcs) from a .twb")
    i.add_argument("twb")
    args = ap.parse_args(argv)

    if args.cmd == "introspect":
        from .introspect import introspect
        print(json.dumps(introspect(args.twb), indent=2))
        return

    spec_path = os.path.abspath(args.spec)
    with open(spec_path) as fh:
        spec = json.load(fh)
    out = args.out or os.path.splitext(spec_path)[0] + ".twb"
    xml = build(spec, os.path.dirname(spec_path))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("<?xml version='1.0' encoding='utf-8' ?>\n" + xml + "\n")
    print("wrote", out)
    if args.open and sys.platform == "darwin":
        subprocess.run(["open", out], check=False)


if __name__ == "__main__":
    main()
