# Generation 3 Post-Touch Activity Specification

Status: **LOCKED BEFORE ANY FORWARD OUTCOME WAS INSPECTED**

## 1. Frozen reference bands

Per event, both frozen at the touch bar close and never altered by later price:

```text
ATR band   = [node_low - 1.0 * ATR_touch, node_high + 1.0 * ATR_touch]
Width band = [node_low - 2.0 * node_width, node_high + 2.0 * node_width]
```

Clipped only at valid instrument price bounds.

## 2. Post-touch allocation

Each post-touch bar's volume is allocated uniformly across its occupied tick
bins using the existing Stage 1 allocation convention. TPO occupancy counts
completed post-touch bars per bin. This is a **proxy**, never transaction-level
volume at price.

## 3. Capture and concentration

Per horizon and per reference band:

```text
V_node_h, V_band_h   allocated post-touch volume inside node and band
T_node_h, T_band_h   post-touch TPO occupancy inside node and band

node_volume_capture_share_h = V_node_h / V_band_h
node_TPO_capture_share_h    = T_node_h / T_band_h

node_width_share = node_width_bins / reference_band_width_bins

post_touch_volume_concentration_ratio_h = node_volume_capture_share_h / node_width_share
post_touch_TPO_concentration_ratio_h    = node_TPO_capture_share_h    / node_width_share

post_touch_activity_concentration_ratio_h =
    sqrt(volume_concentration_ratio_h * TPO_concentration_ratio_h)
```

A ratio of 1.0 means activity per price bin inside the node equals the local
band average. 2.0 means the node captured twice the local average per bin.

**Primary activity metric: `post_touch_activity_concentration_ratio_30` on the
+/- 1 ATR band.** The +/- 2-node-width band is robustness evidence.

Zero denominators are handled explicitly: a zero band volume or TPO yields an
`undefined` ratio recorded as such, counted and reported. Invalid observations
are never silently discarded.

## 4. Overall market activity after the tap

```text
post_market_volume_rate_ratio_h =
    mean one-minute volume after touch / mean one-minute volume over the 15
    completed minutes before touch

post_market_range_rate_ratio_h =
    mean true range after touch / mean true range over the same 15 minutes
```

These measure whether the interaction coincides with a general rise in market
activity. They are reported **separately** from node-local concentration and
must never be presented as evidence of concentration inside the node.
