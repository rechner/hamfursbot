FROM python:3.7-buster

WORKDIR /code

COPY requirements.txt .
COPY *.py /code/
COPY res /code/res/
COPY cron /code/cron/

ADD cron/crontab /etc/cron.d/hamfurs
RUN chmod 0644 /etc/cron.d/hamfurs

RUN touch /var/log/cron.log

#Install Cron
RUN apt-get update
RUN apt-get -y install cron

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD cron && python3 ./main.py

