# SaplingTrack

Tracks saplings after community plantation drives so organisers see the real survival rate.

Built with Python (Flask), Supabase and Leaflet. Hosted on Render.

## Run locally

    pip install -r requirements.txt
    set SUPABASE_URL and SUPABASE_KEY as environment variables
    python app.py

## Deploy on Render

Build command: `pip install -r requirements.txt`
Start command: `gunicorn app:app`
Environment variables: `SUPABASE_URL`, `SUPABASE_KEY`
