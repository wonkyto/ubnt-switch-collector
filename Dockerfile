FROM python:3

ARG TZ=Australia/NSW
ENV TZ=${TZ}

WORKDIR /app

# Change the timezone (required for localtime when logging)
RUN ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo "${TZ}" > /etc/timezone

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app

CMD [ "python", "./ubnt-switch-collector.py" ]
