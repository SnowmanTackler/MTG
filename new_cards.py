#!/usr/bin/env python3
"""List the cards added to each deck, so you know what to buy.

Compares Cockatrice .cod decklists between two git revisions and prints the
cards whose count went up.

    ./new_cards.py                 # uncommitted changes (HEAD vs working tree)
    ./new_cards.py HEAD~3          # HEAD~3 vs working tree
    ./new_cards.py HEAD~3 HEAD     # the last three commits
    ./new_cards.py --removed       # also show what came out of each deck
"""

import argparse
import collections
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

WORKTREE = None  # sentinel for "the files on disk"


def git(*args):
    return subprocess.run(
        ["git"] + list(args), capture_output=True, text=True, check=True
    ).stdout


def repo_root():
    return git("rev-parse", "--show-toplevel").strip()


def changed_decks(from_rev, to_rev):
    """Deck paths that differ between the two revisions."""
    args = ["diff", "--name-only", "--diff-filter=ACMR", from_rev]
    if to_rev is not WORKTREE:
        args.append(to_rev)
    paths = set(p for p in git(*args).splitlines() if p.endswith(".cod"))
    if to_rev is WORKTREE:
        # brand new decks that were never committed
        paths |= set(
            p
            for p in git("ls-files", "--others", "--exclude-standard").splitlines()
            if p.endswith(".cod")
        )
    return sorted(paths)


def read_deck(path, rev):
    """Deck XML at a revision, or None if the deck did not exist there."""
    if rev is WORKTREE:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None
    result = subprocess.run(
        ["git", "show", "{}:{}".format(rev, path)], capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else None


def card_counts(xml_text):
    """{card name: copies} for a deck, summed over the main deck and sideboard."""
    counts = collections.Counter()
    if not xml_text:
        return counts
    for card in ET.fromstring(xml_text).iter("card"):
        name = card.get("name")
        if not name:
            continue
        try:
            number = int(card.get("number", 1))
        except ValueError:
            number = 1
        counts[name] += number
    return counts


def deck_name(path):
    return os.path.splitext(path)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("from_rev", nargs="?", default="HEAD",
                        help="revision to compare from (default: HEAD)")
    parser.add_argument("to_rev", nargs="?", default=None,
                        help="revision to compare to (default: working tree)")
    parser.add_argument("--removed", action="store_true",
                        help="also list cards taken out of each deck")
    args = parser.parse_args()

    os.chdir(repo_root())
    from_rev, to_rev = args.from_rev, args.to_rev if args.to_rev else WORKTREE

    any_output = False

    for path in changed_decks(from_rev, to_rev):
        old = card_counts(read_deck(path, from_rev))
        new = card_counts(read_deck(path, to_rev))

        added = {n: c for n, c in ((n, new[n] - old.get(n, 0)) for n in new) if c > 0}
        removed = {n: c for n, c in ((n, old[n] - new.get(n, 0)) for n in old) if c > 0}

        if not added and not (args.removed and removed):
            continue

        any_output = True
        print(deck_name(path))
        for name in sorted(added):
            print("  {} {}".format(added[name], name))
        if args.removed:
            for name in sorted(removed):
                print("  - {} {}".format(removed[name], name))
        print()

    if not any_output:
        print("No cards added.")
        return


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.stderr.strip() or "git command failed")
