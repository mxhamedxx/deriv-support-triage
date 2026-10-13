# Deriv Support Triage

A replayable Python pipeline for ticket normalization, single-batch AI triage, required human review, queue routing, summary generation, and validation.

## Setup

Use Python 3.10+ (Windows PowerShell):

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Configure `GEMINI_API_KEY` (do **not** commit your key):

```powershell
$secret = Read-Host "Gemini API key" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
```

## Run

```powershell
.\.venv\Scripts\python.exe main.py
```

The program reads `tickets.json` and `triage_config.json` each run. The model is called once for all normalized tickets. At the review prompt, enter `ticket_id,category,priority` for each correction; submit a blank line to complete review.

Example: `T-1001,account_access,urgent`

After the run, open `dashboard.html` in your browser for a read-only, searchable agent queue. Review/overrides remain in the terminal.

Then validate:

```powershell
.\.venv\Scripts\python.exe validate.py
```

## Offline testing only

If your API provider is unavailable, exercise normalization, review, queue generation and validation **without calling an LLM**:

```powershell
.\.venv\Scripts\python.exe main.py --offline
```

`--offline` is a clearly marked deterministic **test double**, **not** an LLM solution. The normal `python main.py` path uses Gemini. Do not treat offline predictions as satisfying the AI-call requirement.

## Outputs

- `normalized_tickets.json` — deterministic preprocessing results.
- `triage_predictions.json` — initial predictions, never mutated by human review.
- `review_overrides.json` — changed values with before/after values.
- `final_queue.json` — post-review routing and output.
- `queue_summary.md` — final category, priority, destination counts and overridden tickets.
- `pipeline_states.json` — ordered stage transition record.

The submitted solution must be run again after changing the input fixtures. No results are hardcoded from sample ticket IDs. All route assignments are controlled by `triage_config.json`.

## Files / submission

`main.py`, `llm_service.py`, `dashboard.py`, and `validate.py` are the application.
The evaluator can delete generated artifacts and regenerate them with `python main.py`.
Use a genuine Gemini API key for the default run. `--offline` is only for local demonstrations.
The HTML dashboard is regenerated after the required review and is not a separate service.
