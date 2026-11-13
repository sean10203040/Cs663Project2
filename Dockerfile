FROM python:3.12-slim
WORKDIR /service
COPY backend/requirements.txt /service/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend /service/backend
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
