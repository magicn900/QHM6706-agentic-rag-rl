# Frontend Demo

A simple Streamlit page for thesis/demo presentation.

## Features

- Question input box
- Showcase quick-fill from `reports/webqsp_smoke_30_showcase_cases.json`
- One-click run (`Send`)
- Live step-by-step trace:
  - agent context (`knowledge`, `candidate_edges`)
  - model output (`prompt`, `raw_response`, parsed action)
  - environment feedback (`reward`, `done`, termination)

## Run

From repo root:

```bash
streamlit run frontend/app.py
```

Then open the local URL shown in terminal.

## Notes

- `Policy=llm` requires action model API envs (for example `AGENTIC_RAG_ACTION_API_KEY` or fallback compatible keys).
- If no model key is available, switch to `Policy=heuristic` for an offline demo flow.
- The page defaults to `Graph Adapter=freebase` to match your validated smoke route.
- If you switch to `lightrag` without indexed local data, candidate edges may be empty and the agent can only return fallback answers.
