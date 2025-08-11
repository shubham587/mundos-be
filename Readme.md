Use a production ASGI command without reload:
uvicorn: uvicorn main:app --host 0.0.0.0 --port $PORT --workers $(python -c "import os;print(max(1,os.cpu_count() or 1))")
Ensure Python 3.12 is available (repo’s local venv shows 3.12).
Health check: GET / returns {"status":"ok"}; point your LB/monitor here.
Logging: JSON logs at INFO go to stdout; ensure your platform captures stdout.


Enforce HTTPS at the edge; block direct HTTP if possible.

Create a Pub/Sub topic and push subscription to:
POST https://<your-domain>/pubsub/push?token=$PUBSUB_VERIFICATION_TOKEN
Ensure public ingress to POST /pubsub/push from Google.

Deployment risks to address before push:
Sensitive files (confidential.json, token.json, venv) in repo
Inconsistent DB env var names (MONGO_* vs MONGODB_*)
Default Mongo URI embedded in code
Multiple instances creating Gmail watches

 ENVIRONMENT=development PYTHONUNBUFFERED=1 uvicorn main:create_app --factory --host 0.0.0.0 --port 8000 --reload --access-log