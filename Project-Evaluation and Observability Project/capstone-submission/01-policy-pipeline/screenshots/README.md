# Screenshot

`calibration-report-sliced.png`

Command shown:

```
.venv/bin/python calibration_report.py
```

What it shows: the sliced calibration report — `umbrella/exclusions` at `conf=0.93 acc=0.00 brier=0.865` while `OVERALL brier=0.291`. The aggregate hides a cell that is confidently wrong every time.

The same run is captured verbatim as text in `../calibration-report.txt`, which carries the full untruncated output.
Both are from the same command; the text capture is the one to search for exact values.
