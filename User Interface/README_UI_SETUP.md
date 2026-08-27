# NeuroCapstone — UI Ready Package

## Run backend

From `User Interface/backend`:

```bash
python -m pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

The adapter exposes:
- `GET /health`
- `POST /analyze`

It imports the existing project's `pipeline.run_pipeline` from the project root.

## Run frontend

From `User Interface/frontend`:

```bash
npm install
npm run build
npm run dev
```

Open:

`http://localhost:5173`

The frontend calls:

`http://127.0.0.1:8000/analyze`

## Expected pipeline contract

The existing project pipeline must provide:

```python
pdb_path, context_data, physics_json_path = run_pipeline(gene, variant)
```

The UI renders those returned values; it does not fabricate scientific results.
