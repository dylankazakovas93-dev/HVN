# Hand-calculated fixtures

These three fixtures are intentionally tiny.

- `uniform_single_and_multi.csv`: a 12-volume bar spans four 0.25 bins, so each
  receives 3; a 4-volume zero-range bar at 100.25 adds 4 to bin 401. Expected
  weights: 400=3, 401=7, 402=3, 403=3. Total 16.
- `tpo_overlap.csv`: the first range intersects bin 400 only; the second
  intersects 400 and 401. Expected TPO: 400=2, 401=1.
- `plateau_hvn.csv`: weights 1,5,5,1 form one plateau over bins 1–2, with a
  representative chosen by the POC hierarchy and a node spanning the plateau.

They use exact decimal prices and the global zero-origin half-open grid.
