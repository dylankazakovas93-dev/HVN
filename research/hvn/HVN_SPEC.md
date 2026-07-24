# HVN Specification

An HVN is a contiguous zone around a locally prominent peak in a frozen profile
proxy. It is not a top-percentile bin set and is not a profitable grade.

Equal-weight adjacent maximum bins form one plateau. A plateau is locally
eligible only when both adjacent weights are lower (missing edges are treated as
lower). Its representative uses the POC proximity hierarchy and its full range
is preserved.

The local baseline is the median weight of non-plateau bins whose centers lie
within ±0.50 ATR of the representative center. At least two surrounding bins
are required. Prominence is peak weight divided by baseline. A positive peak
over a zero baseline is recorded as infinite prominence. Thresholds are 1.5,
2.0, and 2.5; equality qualifies.

For a qualifying peak, expand through contiguous bins with weight at least 50%
of peak weight. The first lower bin on each side is excluded. Zones that overlap
or touch merge and bins are counted once.

Representative peak order after merge is greater peak weight, greater node
weight share, greater prominence, closer to POC, then lower price. Ledgers retain
all constituent candidate IDs, boundaries, center, width, weight/share, bin
count, peak, baseline, and prominence.
