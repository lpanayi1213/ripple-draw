#!/usr/bin/env python3
# ripple-draw: the fairness core of a referral giveaway's draw.
#
# MIT License
#
# Copyright (c) 2026 ShopsWare
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""How a giveaway's winner is picked, in one file anyone can read and run (Python 3, standard library only).

The draw has three public parts, and this file is all the math between them:

1. **The frozen list.** When entries close, every counted entry becomes one line, ``<entry number>,<private code>``,
   sorted by entry number (smallest first), each line ending in a line feed (``\\n``), nothing else: no names, no
   phone numbers. That text is the list (``list_text``). Its fingerprint is the SHA-256 of the list's UTF-8 bytes,
   written as 64 lowercase hex digits (``fingerprint``). The fingerprint is published as soon as the list is frozen,
   before the random number exists, so the list can't be changed afterwards without everyone seeing it.

2. **The public random number.** The rules name, before entries close, one round of the drand "quicknet" beacon run by
   the League of Entropy (https://drand.love): a new random number every 3 seconds, made jointly by independent
   organizations, that nobody (the shop included) can know before its time or change after. Its ``randomness`` is 32
   bytes, written as 64 hex digits.

3. **The pick.** For counter = 0, 1, 2, ...::

       digest  = SHA-256( randomness bytes || fingerprint bytes || counter as 8 bytes, big-endian )
       index   = (digest read as one big-endian unsigned number) mod N      (N = the number of entries)
       pick    = the entry number on line ``index`` of the list (line 0 is the first)

   An entry number already picked is passed over, and the counter moves on. The first pick is the winner; the next
   ones, in order, are the backups (alternates). ``picks`` gives this order, ``pick`` the first ``count`` of it.
   (The bias of "mod N" on a 256-bit number is below 1 in 2**200 for any real list: none worth naming.)

**Backups that belong to someone already picked.** A person can hold several entries (bonus entries for friends who
joined). The list can't show whose entry is whose (it reveals no one), so this file picks distinct *entry numbers*.
The shop's system then walks the same order and passes over a number whose person already holds a place (the winner or
an earlier backup), taking the next number in the order. Anyone can re-run the order with ``picks`` and see that every
published backup comes from it, in order; the numbers passed over are the ones whose person already had a place.

Check a draw yourself::

    python3 draw_core.py verify --list list.txt --randomness <64 hex digits> --winner <entry number>
    python3 draw_core.py order --list list.txt --randomness <64 hex digits> --count 10

``verify`` prints the list's fingerprint (compare it with the one published when entries closed), the first picks, and
whether the winner matches. It exits 0 when it does, 1 when it doesn't, 2 for a list it can't read.
"""
import argparse
import hashlib
import re
import sys

__version__ = '1.0.0'

_LINE = re.compile(r'(\d{1,18}),([A-Za-z0-9]{1,32})')


class ListError(ValueError):
    """A list that isn't in the frozen list's exact form."""


def list_text(entries):
    """The frozen list from ``entries`` (pairs of (entry number, private code)): one line per entry, "number,code",
    sorted by number, each line ending in a line feed. Raises ListError for a repeated number or a code with anything
    but letters and digits."""
    seen = set()
    lines = []
    for number, code in sorted(((int(number), str(code)) for number, code in entries), key=lambda pair: pair[0]):
        if number < 0 or number in seen:
            raise ListError(f'entry number {number} is repeated or negative')
        if not re.fullmatch(r'[A-Za-z0-9]{1,32}', code):
            raise ListError(f'entry {number} has a code that is not letters and digits')
        seen.add(number)
        lines.append(f'{number},{code}\n')
    return ''.join(lines)


def fingerprint(text):
    """The list's fingerprint: SHA-256 of its UTF-8 bytes, 64 lowercase hex digits."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def numbers(text):
    """The entry numbers of a frozen list, in its order. Raises ListError unless ``text`` is exactly in the frozen
    list's form (the same text always gives the same fingerprint)."""
    if text and not text.endswith('\n'):
        raise ListError('the list must end with a line feed')
    found = []
    last = None
    for at, line in enumerate(text.split('\n')[:-1] if text else [], start=1):
        matched = _LINE.fullmatch(line)
        if not matched:
            raise ListError(f'line {at} is not "number,code"')
        number = int(matched.group(1))
        if str(number) != matched.group(1):
            raise ListError(f'line {at} has a number with leading zeros')
        if last is not None and number <= last:
            raise ListError(f'line {at} is out of order or repeated')
        last = number
        found.append(number)
    return found


def _randomness(randomness_hex):
    value = str(randomness_hex or '').strip().lower()
    if not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('the randomness must be 64 hex digits')
    return bytes.fromhex(value)


def picks(randomness_hex, text):
    """Every entry number of the list, each once, in the order the draw picks them (a generator; see the notes at the
    top). Yields (entry number, counter that picked it)."""
    seed = _randomness(randomness_hex) + bytes.fromhex(fingerprint(text))
    found = numbers(text)
    total = len(found)
    taken = set()
    counter = 0
    while len(taken) < total:
        digest = hashlib.sha256(seed + counter.to_bytes(8, 'big')).digest()
        number = found[int.from_bytes(digest, 'big') % total]
        if number not in taken:
            taken.add(number)
            yield number, counter
        counter += 1


def pick(randomness_hex, text, count):
    """The first ``count`` entry numbers the draw picks: [winner, first backup, ...] (fewer when the list is
    shorter)."""
    order = []
    if count <= 0:
        return order
    for number, _counter in picks(randomness_hex, text):
        order.append(number)
        if len(order) >= count:
            break
    return order


def _main(argv=None):
    parser = argparse.ArgumentParser(prog='draw_core.py', description='Check a giveaway draw.')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('verify', 'order'):
        one = sub.add_parser(name)
        one.add_argument('--list', required=True, help='the published list file (number,code lines)')
        one.add_argument('--randomness', required=True, help="the beacon round's randomness (64 hex digits)")
        one.add_argument('--count', type=int, default=4, help='how many picks to show')
        if name == 'verify':
            one.add_argument('--winner', type=int, required=True, help='the published winning entry number')
            one.add_argument('--fingerprint', help='the published list fingerprint, to compare')
    args = parser.parse_args(argv)
    try:
        with open(args.list, 'rb') as handle:
            text = handle.read().decode('utf-8')
        numbers(text)
        order = pick(args.randomness, text, max(1, args.count))
    except (OSError, UnicodeDecodeError, ListError, ValueError) as error:
        print(f'Could not read the draw: {error}', file=sys.stderr)
        return 2
    print(f'entries:     {len(numbers(text))}')
    print(f'fingerprint: {fingerprint(text)}')
    print('picks:       ' + ', '.join(f'#{number}' for number in order))
    if args.command == 'order':
        return 0
    ok = bool(order) and order[0] == args.winner
    if args.fingerprint:
        same = args.fingerprint.strip().lower() == fingerprint(text)
        print('fingerprint matches the published one' if same else 'FINGERPRINT DOES NOT MATCH the published one')
        ok = ok and same
    print(f'winner #{args.winner}: ' + ('MATCHES the draw' if order and order[0] == args.winner
                                         else f'does NOT match (the draw picks #{order[0] if order else "none"})'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(_main())
