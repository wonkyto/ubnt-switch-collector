FROM python:3

WORKDIR /app

# Change the timezone (required for localtime when logging)
RUN cp /usr/share/zoneinfo/Australia/NSW /etc/localtime
RUN echo "Australia/NSW" > /etc/timezone

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app

CMD [ "python", "./ubnt-switch-collector.py" ]
