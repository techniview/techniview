FROM python:3.14-slim

# git is needed: compose command sets core.hooksPath in /workspace
RUN apt-get update -qq && apt-get install -y -qq git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# --reload is dev only, drop it for a prod image
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
