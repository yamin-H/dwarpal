FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway/ ./gateway/
RUN useradd --create-home app && chown -R app /srv
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--app-dir", "gateway", \
     "--host", "0.0.0.0", "--port", "8000"]