#!/usr/bin/env python3
"""Normalize Cockatrice .cod decklists: sorted cards, no scratch metadata.

Every card becomes `<card number="N" name="..."/>` -- Cockatrice's setShortName,
collectorNumber, uuid and price attributes are dropped, as are the file level
lastLoadedTimestamp / format / bannerCard / tags elements, so saving a deck does
not churn the diff. Cards are alphabetized within each zone.

    ./format_decks.py                  # rewrite every deck in the repo
    ./format_decks.py Commander/*.cod  # rewrite just these decks
    ./format_decks.py --check          # report unformatted decks, change nothing
"""

import argparse
import collections
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

ZONE_ORDER = ["main", "side"]

HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<cockatrice_deck version="1">\n'
FOOTER = "</cockatrice_deck>\n"


def git(*args):
    return subprocess.run(
        ["git"] + list(args), capture_output=True, text=True, check=True
    ).stdout


def repo_root():
    return git("rev-parse", "--show-toplevel").strip()


def all_decks():
    return sorted(p for p in git("ls-files").splitlines() if p.endswith(".cod"))


def attr(text):
    """XML escape a string for use inside a double quoted attribute."""
    for old, new in [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;")]:
        text = text.replace(old, new)
    return text


def sort_key(name):
    return (name.casefold(), name)


def zone_key(name):
    order = ZONE_ORDER.index(name) if name in ZONE_ORDER else len(ZONE_ORDER)
    return (order, name)


def formatted(xml_text):
    """The canonical text for a deck, or raise ET.ParseError on bad XML."""
    root = ET.fromstring(xml_text)

    lines = [HEADER, "    <deckname></deckname>\n", "    <comments></comments>\n"]

    zones = sorted(root.findall("zone"), key=lambda z: zone_key(z.get("name", "")))
    for zone in zones:
        counts = collections.Counter()
        for card in zone.findall("card"):
            name = card.get("name")
            if not name:
                continue
            try:
                number = int(card.get("number", 1))
            except ValueError:
                number = 1
            counts[name] += number

        lines.append('    <zone name="{}">\n'.format(attr(zone.get("name", ""))))
        for name in sorted(counts, key=sort_key):
            lines.append(
                '        <card number="{}" name="{}"/>\n'.format(
                    counts[name], attr(name)
                )
            )
        lines.append("    </zone>\n")

    lines.append(FOOTER)
    return "".join(lines)


def format_file(path, check):
    """True if the file is already formatted. Rewrites it unless check is set."""
    with open(path, encoding="utf-8") as f:
        current = f.read()

    wanted = formatted(current)
    if current == wanted:
        return True

    if not check:
        with open(path, "w", encoding="utf-8") as f:
            f.write(wanted)
    return False


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("decks", nargs="*", help="decks to format (default: all)")
    parser.add_argument("--check", action="store_true",
                        help="only report which decks need formatting")
    args = parser.parse_args()

    paths = [os.path.abspath(p) for p in args.decks]
    os.chdir(repo_root())
    if not paths:
        paths = all_decks()

    changed = []
    for path in paths:
        try:
            if not format_file(path, args.check):
                changed.append(path)
        except ET.ParseError as e:
            sys.exit("{}: not valid XML: {}".format(path, e))
        except FileNotFoundError:
            sys.exit("{}: no such deck".format(path))

    for path in changed:
        print("{} {}".format("unformatted:" if args.check else "formatted:",
                             os.path.relpath(path)))

    if changed and args.check:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        sys.exit(e.stderr.strip() or "git command failed")
