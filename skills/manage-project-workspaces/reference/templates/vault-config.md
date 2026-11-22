## `.vault-config.json`

Written at scaffold time; this file is what marks a workspace structured.

```json
{
  "project": "<short-slug>",
  "generated_types": ["index", "log-index"],
  "index_types": ["index", "log-index", "overview", "meta", "glossary", "summary"],
  "min_hits": 3,
  "title_weight": 4,
  "topics": {}
}
```

The folder skeleton is fixed by the contract and is not configured here. What varies per project is
the vocabulary: `topics`, `min_hits`, `title_weight`, and optionally `root_notes`.
