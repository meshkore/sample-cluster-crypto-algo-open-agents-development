"""Deliberate downloaders, one per source. Nothing in this package fetches at read time.

A backtest that reaches the internet halfway through a run is not a backtest: it is not
reproducible, it is not offline, and it fails in a way that looks like a bad result rather
than like a broken network. So harvesting is always an explicit command with its own entry
point, its own rate limiting, and its own report.

Planned, in the order they pay for themselves:
    fred.py       already exists as quantlab_catalog.fetch_reference; moves here
    gdelt.py      GDELT 2.0 tone and volume by country and theme, free, 2015 onward
    wiki.py       Wikipedia pageviews as an attention proxy, by language
    alfred.py     real vintages for the heavily revised series, so revisions stop being a flag
"""
