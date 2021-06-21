ARG PYTHON_VERSION=3.9-slim

FROM python:$PYTHON_VERSION as builder
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y gcc git
RUN pip install -U pip setuptools wheel

WORKDIR /wheels
COPY requirements.txt /
RUN pip wheel -r /requirements.txt

FROM python:${PYTHON_VERSION} as api
ENV PYTHONUNBUFFERED=1

COPY --from=builder /wheels /wheels
RUN pip install -U pip \
        && pip install /wheels/* \
        && rm -rf /wheels \
        && rm -rf /root/.cache/pip/*

WORKDIR /code
COPY src .
CMD ["python", "selectel.py"]
