# Contributing

Pull requests that change weights, thresholds, checks or the source table are welcome. Three rules apply.

## Argue the fake cost

A new check, or a change to an existing check's `cost`, needs one sentence in the pull request on what it would take a fraudster to produce that evidence. That sentence is the whole design of this repo. "It feels important" is not a cost.

## Keep it standard library only

Python 3.8+, no third party packages, so the script runs on a locked down compliance laptop. Before opening a pull request:

```bash
python3 -m py_compile legit_check.py
python3 -m unittest discover -s tests -v
python3 legit_check.py examples/northgate_supplies.json --today 2026-10-30; test $? -eq 0
python3 legit_check.py examples/quickship_trading.json --today 2026-10-30; test $? -eq 1
```

Every new rule gets a test in `tests/test_legit_check.py`, ideally one that shows a verdict changing.

## Sources and data

Registry and register links must point at the official body, never at an aggregator or a lookup reseller. Example profiles stay synthetic and use the reserved `.example` domain. Do not add profiles of real companies. Anything said about a named company in the README is limited to public signals with the date they were observed.

This is a reference implementation, not legal advice. Describe verification vendors as a layer your own program runs on, never as something that makes a business compliant.
