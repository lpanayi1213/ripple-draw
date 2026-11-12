# ripple-draw: check a giveaway draw yourself

`draw_core.py` is the whole of the math that picks a giveaway's winner. The shop's system runs this exact file for
the real draw, so the code you read is the code that ran. It needs only Python 3 (no packages) and holds no customer
data.

## What gets published, and when

1. **Before entries close:** the rules and the draw page name the public random number that will be used: one round of
   the drand "quicknet" beacon, run by the League of Entropy (https://drand.love). Nobody, the shop included, can know
   that number before its time or change it after.
2. **When entries close:** the list is frozen and its fingerprint is published. The list is one line per entry,
   `entry number,private code`, sorted by number, and nothing else. Your own entry numbers and their private codes
   are on your "My entries" page, so you can find yourself on the list and nobody else can.
3. **At the draw:** the beacon publishes the round's randomness, and the winner and backups follow from it and the
   list.

## Check it

Download the list from the draw page (`list.txt`), and copy the round's randomness from the draw page (or from
drand's own address for that round, which the draw page links to). Then:

```
python3 draw_core.py verify --list list.txt --randomness <64 hex digits> --winner <winning entry number> --fingerprint <published fingerprint>
```

It prints the list's fingerprint (it must match the one published when entries closed), the first picks in order, and
whether the winner matches. `order` prints more of the order, for the backups:

```
python3 draw_core.py order --list list.txt --randomness <64 hex digits> --count 10
```

## How the pick works

For counter = 0, 1, 2, ...: SHA-256 of (the randomness's 32 bytes, then the fingerprint's 32 bytes, then the counter
as 8 bytes, big-endian), read as one number, mod the number of entries, gives a line of the list. A number already
picked is passed over. The first pick wins; the next ones, in order, are the backups.

One person can hold several entries (bonus entries for friends who joined). The list can't show whose entry is whose,
so a backup number whose person already holds a place is passed over and the next number in the order is taken. Every
published backup is in the order `order` prints, in the same sequence.

## Checking the beacon itself

quicknet's chain hash is `52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971`. For this chain a round's
randomness is the SHA-256 of its signature, and the signature is a BLS signature anyone can check against the chain's
public key with drand's own tools (https://github.com/drand). The shop's system checks the chain hash, the round
number and that the randomness is the SHA-256 of the signature; it does not check the BLS signature itself.

License: MIT.
