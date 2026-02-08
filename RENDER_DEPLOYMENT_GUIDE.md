# Render Deployment - Recommended Configuration

## render.yaml

```yaml
services:
  - type: web
    name: medical-bill-verifier
    env: python
    region: oregon
    plan: standard
    buildCommand: |
      apt-get update && apt-get install -y poppler-utils
      pip install -r backend/requirements.txt
    startCommand: cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
    
    envVars:
      - key: ENV
        value: production
      - key: MONGO_URI
        sync: false  # Add via Render dashboard (secret)
      - key: MONGO_DB_NAME
        value: medical_bills
      - key: OCR_CONFIDENCE_THRESHOLD
        value: "0.6"
      - key: DISABLE_OLLAMA
        value: "true"
      # Optional: If using external Ollama
      # - key: LLM_BASE_URL
      #   value: https://your-ollama-service.com
```

## Environment Variables

Set these in Render → Environment:

| Variable              | Required | Value                                      |
| --------------------- | -------- | ------------------------------------------ |
| `ENV`                 | ✅       | `production`                               |
| `MONGO_URI`           | ✅       | Your MongoDB connection string (secret)    |
| `MONGO_DB_NAME`       | ✅       | `medical_bills`                            |
| `DISABLE_OLLAMA`      | ✅       | `true` (recommended initially)             |
| `OCR_CONFIDENCE_THRESHOLD` | ❌  | `0.6` (optional, has default)              |
| `LLM_BASE_URL`        | ❌       | Only if using external Ollama              |

## Important Notes

1. **Embedding Cache**: Automatically uses `/tmp` on Render (ephemeral storage). Embeddings are regenerated on restart.
2. **Tie-up JSONs**: Read from `backend/data/tieups/` (included in Git repository).
3. **MongoDB**: Must be external (MongoDB Atlas recommended).
4. **Ollama**: Disabled by default. Enable only if you have an external Ollama service.
5. **Port Binding**: Application automatically binds to `$PORT` environment variable set by Render.

## Build Command Breakdown

```bash
apt-get update && apt-get install -y poppler-utils  # For PDF processing
pip install -r backend/requirements.txt              # Python dependencies
```

## Start Command Breakdown

```bash
cd backend                                           # Change to backend directory
uvicorn app.verifier.api:app                        # Run FastAPI app
  --host 0.0.0.0                                    # Bind to all interfaces
  --port $PORT                                       # Use Render's port
  --workers 2                                        # 2 worker processes
```

## Deployment Checklist

- [ ] Create Render Web Service
- [ ] Set runtime to Python
- [ ] Configure build command
- [ ] Configure start command
- [ ] Add environment variables (especially `MONGO_URI`)
- [ ] Deploy and monitor logs
- [ ] Test `/health` endpoint
- [ ] Test `/verify` endpoint with sample bill

## Troubleshooting

### Service won't start
- Check logs for MongoDB connection errors
- Verify `MONGO_URI` is set correctly
- Ensure tie-up JSONs exist in `backend/data/tieups/`

### Verification fails
- Check if tie-up rate sheets loaded successfully (startup logs)
- Verify MongoDB contains bill documents
- Check embedding cache warnings (should use /tmp)

### Performance issues
- Consider upgrading to Standard Plus plan (more RAM/CPU)
- Monitor embedding cache hit rate
- Consider enabling persistent disk for embedding cache
