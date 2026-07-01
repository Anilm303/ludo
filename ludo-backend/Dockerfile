FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=7860
ENV FLASK_PORT=7860
ENV FLASK_HOST=0.0.0.0
ENV FLASK_DEBUG=false

EXPOSE 7860

ENTRYPOINT ["python", "run.py"]