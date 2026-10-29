FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PYTHONUTF8=1 PYTHONUNBUFFERED=1 AEGIS_PUBLIC=1
EXPOSE 8000
# Platforms like Render / Hugging Face Spaces provide $PORT. Keys come from the platform's environment variables, never from the image.
CMD ["sh", "-c", "python -m aegismesh.server --host 0.0.0.0 --port ${PORT:-8000}"]
