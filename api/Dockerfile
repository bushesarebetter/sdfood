# The staff API with its data baked in. Build it only with deploy_api.py, on the machine that holds data/
# (the export is gitignored and must stay out of the public repository): it checks the staff release's
# approval, the City's request and TRUST answer and the holds, writes data/site/api_release.json, builds
# this image, checks it, pushes it to a PRIVATE registry and deploys it (docs/HOSTING.md, "The staff API
# on Render"). An image without data/site/api_release.json does not build (below), and the API serves no
# data without it (api/main.py). For a run on your own machine, see docs/API.md, "Running it".
FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt && useradd --no-create-home --uid 10001 api
COPY api/ api/
COPY data/site/ data/site/
# Named on its own so that a build without the release record deploy_api.py writes stops here.
COPY data/site/api_release.json data/site/api_release.json
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
