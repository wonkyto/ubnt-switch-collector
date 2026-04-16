FROM python:3.13-slim-bookworm AS base

ARG TZ=Australia/NSW
ENV TZ=${TZ}

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app


FROM base AS production

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app

CMD ["python", "./ubnt_switch_collector.py"]


FROM base AS dev

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app /app
COPY tests /tests
