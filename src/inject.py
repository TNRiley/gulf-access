#!/usr/bin/env python
"""Splice payload.json into template.html and write ../index.html.

The payload goes in gzipped and base64'd; the page inflates it with
DecompressionStream. It is the per-piece canal table, eight map plates
(elevation and water class rasters), county outlines and the per-tile
sea-level readings.

The last two steps re-run the catalog tools, so regenerating the page never
silently drops the doctype wrapper or the breadcrumb bar.
"""
import base64, gzip, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
PROJECT = HERE.parent
MARK = "__PAYLOAD__"


def workspace_root(start):
    p = start
    while True:
        if (p / "projects").is_dir() and (p / "catalog").is_dir():
            return p
        nxt = p.parent
        if nxt == p:
            sys.exit("could not find the workspace root")
        p = nxt


def main():
    template = (HERE / "template.html").read_text(encoding="utf-8")
    raw = (HERE / "payload.json").read_bytes()
    if MARK not in template:
        sys.exit("template.html has no %s placeholder" % MARK)

    blob = base64.b64encode(gzip.compress(raw, 9)).decode("ascii")
    page = template.replace(MARK, blob)

    out = PROJECT / "index.html"
    out.write_text(page, encoding="utf-8", newline="\n")
    print("index.html %.2f MB (payload %.2f MB raw -> %.2f MB base64)"
          % (out.stat().st_size / 1e6, len(raw) / 1e6, len(blob) / 1e6))

    root = workspace_root(HERE)
    tools = root / "catalog" / "tools"
    for script in ("wrap_for_pages.py", "add_catalog_link.py"):
        path = tools / script
        if not path.exists():
            print("  skipping %s (not found)" % script)
            continue
        subprocess.run([sys.executable, str(path), str(out)], check=True)


if __name__ == "__main__":
    sys.exit(main())
