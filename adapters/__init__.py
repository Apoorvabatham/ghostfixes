"""Per-city ingestion adapters — one file per portal.

Everything a specific portal needs lives in its single module here: category
strings, window constants, endpoints, field mapping, image hosts, TLS
policy, artifact parsers. `pipeline/` must stay free of all of them
(docs/adapter-interface.md is the binding contract; CLAUDE.md Stage 6/7 is
the rule a pipeline edit would break).
"""
