# Screenshot

`graceful-degradation-timeout.png`

Command shown:

```
.venv/bin/supply-chain-investigate meridian --offline --simulate-timeout
```

What it shows: the run completing with the dead source named at the top (`> Sources unavailable: logistics unavailable (timeout)`), and the two Incomplete entries keeping distinct causes — `timeout reading logistics` vs `no source reported this metric`. Also visible: `## Contested` now reads `_none_`, the degradation finding discussed in `../timeout-diff.txt`.

The same run is captured verbatim as text in `../timeout-run.txt`, which carries the full untruncated output.
Both are from the same command; the text capture is the one to search for exact values.
