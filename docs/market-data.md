# Market data semantics

PPT provides raw market quotes and dimensioned history, recent graded medians and reported graded sales aggregates. Direct eBay provides screened asking listings. Existing legacy market observations and daily history remain available as dated fallback and graph provenance.

The pricing response exposes `market_history_series` for continuation and `provider_history` for original PPT backfill. Raw points join only across matching language, currency, printing, known condition and metric after a recorded transition. No average across printings, gap filling or fabricated current-date anchors is used. Graded daily averages and seven-day current medians are distinct metrics.

Trending uses `/market/graded-sales-activity`: count by grade, latest reported sale date and independent snapshot freshness. Counts have provider-defined coverage, not a selectable period. Missing counts remain unknown. `/market/sales-activity` remains a compatibility endpoint for explicitly reported raw volume; it is not the Trending graded ranking.

Catalog health reads stored PPT set checkpoints. Public reads do not call providers. See [PPT](pokemon-price-tracker.md), [cutover](ppt-cutover.md), and [the archived original contract](archive/pre-ppt/market-data.md).
