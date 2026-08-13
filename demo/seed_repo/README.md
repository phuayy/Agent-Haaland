# seed_repo — orders-api

A deliberately broken service for exercising the debug loop end to end
without needing a real production incident. The bug: `average_item_price`
in `app/pricing.py` divides by `len(items)` with no guard for an empty
cart — `POST /orders/quote` with `items: []` raises `ZeroDivisionError`.

`error.log` is a captured traceback from exactly that failure, including a
fake account number (`ACC-8829301`) so the same fixture also exercises the
redaction boundary (docs/05's canary-test pattern).

## Using it

The debug loop clones a repo over HTTPS, so this directory needs to exist as
an actual pushable GitHub repository — it can't be handed to the loop as a
local path. Two ways to get there:

1. **Fastest**: create an empty GitHub repo yourself, then:
   ```bash
   cd demo/seed_repo
   git init && git add -A && git commit -m "seed: broken orders-api"
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
2. Or run `../../scripts/bootstrap_demo_repo.sh <owner>/<repo>` from the repo
   root, which does the same thing.

Then edit `sample_request.json`'s `repo_url` to point at it, set
`HAALAND_GITHUB_TOKEN` in `.env` to a PAT with contents + pull-request
read/write on that repo, and run:

```bash
make debug-sample
```

With `HAALAND_LLM_PROVIDER=fake` (the default), the loop runs end to end
with zero API spend and zero network calls to an LLM — useful for proving
the orchestration and the GitHub push/PR path work before spending real
tokens on diagnosis quality.
