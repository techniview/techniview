FROM python:3.14-slim
ARG SOURCE_COMMIT=unrecorded
LABEL org.opencontainers.image.revision=${SOURCE_COMMIT}
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir pytest==9.1.1
COPY . .
