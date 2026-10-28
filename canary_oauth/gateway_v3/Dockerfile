FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 10001 appuser
COPY gateway /srv/gateway
USER appuser
EXPOSE 8080
CMD ["uvicorn","gateway.app:app","--host","0.0.0.0","--port","8080","--no-access-log","--workers","1"]
