# The staff API with its data baked in. Build it on the machine that holds data/ (the export is
# gitignored and must stay out of the public repository), push to a PRIVATE registry, deploy there.
# deploy_api.py does all of it, with checks (docs/HOSTING.md, "The staff API on Render"). By hand:
#   python export_site.py && python export_worklist.py
#   docker build --platform linux/amd64 -f api/Dockerfile -t sdfood-api .
#   docker run -p 8000:8000 -e SDFOOD_API_KEYS=... sdfood-api
FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt && useradd --no-create-home --uid 10001 api
COPY api/ api/
COPY data/site/ data/site/
COPY data/worklists/ data/worklists/
COPY data/research_results.json data/research_results.json
ARG SDFOOD_BUILD=""
ENV SDFOOD_DATA_DIR=/app/data/site SDFOOD_WORKLISTS_DIR=/app/data/worklists SDFOOD_RESEARCH_FILE=/app/data/research_results.json \
    SDFOOD_BUILD=${SDFOOD_BUILD} PYTHONUNBUFFERED=1
USER api
EXPOSE 8000
# Render (and most hosts) say which port to listen on in PORT; 8000 when it is unset. Behind the
# host's proxy, --proxy-headers keeps the client's address and https scheme in the logs.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --forwarded-allow-ips='*'"]
