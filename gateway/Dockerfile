FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/opt/hf
ARG INSTALL_ML=false
ARG EMBEDDING_MODEL=intfloat/multilingual-e5-small
WORKDIR /srv
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Optional: CPU-only torch + the embedding model baked into the image (no runtime download).
RUN if [ "$INSTALL_ML" = "true" ]; then \
      pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
      pip install --no-cache-dir -r requirements-ml.txt && \
      python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"; \
    fi
COPY gateway/ ./gateway/
COPY ui/ ./ui/
RUN useradd --create-home app && mkdir -p /opt/hf && chown -R app /srv /opt/hf
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--app-dir", "gateway", \
     "--host", "0.0.0.0", "--port", "8000"]