# RecoverAI frontend update

## Files

This archive contains the complete `frontend/src` directory.

## Install

1. Stop the Vite development server.
2. Extract this archive.
3. Copy all extracted files and folders into `frontend/src`, replacing files with the same names.
4. No new frontend dependency is required; this update continues to use React, TypeScript and `lucide-react`.
5. From `frontend`, run:

```powershell
npm run build
npm run dev
```

## Backend URL

The default API URL is `http://127.0.0.1:8000/api/v1`.

To override it, create `frontend/.env.local`:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

## Payment Events page

The Payment Events page reads `GET /api/v1/payment-events`. Use the separate backend support archive if this endpoint is not already present.
