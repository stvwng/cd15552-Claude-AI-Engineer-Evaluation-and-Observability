# Screenshot

`consistency-discrepancy-exit1.png`

Command shown:

```
.venv/bin/mortgage-extract fixtures/documents/income_sum_mismatch.txt --mode replay -v
```

What it shows: the two-pass classify-then-extract log (`type=income_verification`, then `tool=extract_income_verification`), the consistency validator reporting `"calculated": 9642.17` vs `"stated": 10892.17`, `"delta": -1250.0`, and the non-zero exit code `1`. The delta is exactly the $1,250 bonus the document's own total double-counts.

The same run is captured verbatim as text in `../discrepancy-run.txt`, which carries the full untruncated output.
Both are from the same command; the text capture is the one to search for exact values.
