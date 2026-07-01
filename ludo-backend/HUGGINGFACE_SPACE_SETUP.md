# Hugging Face Space Setup for `chess_backend`

यो backend Flask हो, FastAPI होइन. HF prompt ले दिएको FastAPI sample ignore गर्नु.

## Deploy गर्नुपर्ने files

Space root मा कम्तीमा यी files/folders हुनुपर्छ:

- `run.py`
- `Dockerfile`
- `requirements.txt`
- `app/`
- `uploads/` (empty भए पनि हुन्छ)

## Important

`ModuleNotFoundError: No module named 'app'` आयो भने 99% case मा `app/` folder Space मा upload भएको छैन वा root मा छैन।

## Correct steps in Hugging Face UI

1. Open your Space: `Anil1515/chess_backend`.
2. Go to `Files` tab.
3. Make sure `app/` folder is present at the Space root.
4. Upload the missing files inside `app/` one by one if needed.
5. Upload or verify `run.py`, `Dockerfile`, and `requirements.txt`.
6. Click `Commit changes`.
7. Wait for rebuild.

## Fix for the current runtime error

Current error:

```text
ModuleNotFoundError: No module named 'app'
```

This means the Space does not currently contain the Flask package folder. Add the whole `app/` directory from this repo.

## What the `app/` folder must contain

- `__init__.py`
- `cleanup.py`
- `security.py`
- `utils.py`
- `websocket.py`
- `models/`
- `routes/`
- `token_store.py`

## Good final check

After commit, the log should show:

- `Starting Chess Authentication API on port 7860...`
- no `ModuleNotFoundError`

## Flutter app URL

After Space is live, use:

```bash
--dart-define=API_BASE_URL=https://<your-space>.hf.space/api
```
