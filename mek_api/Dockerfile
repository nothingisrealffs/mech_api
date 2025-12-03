FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.api.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY battletech_api.py mtf_ingest.py blk_ingest.py mech_bv.py /app/
COPY api_frontend.html /app/api_frontend.html

EXPOSE 8000

CMD ["uvicorn", "battletech_api:app", "--host", "0.0.0.0", "--port", "8000"]
