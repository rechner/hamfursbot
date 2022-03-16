FROM python:3.10-buster

WORKDIR /code

COPY requirements.txt .
COPY *.py /code/
COPY res /code/res/

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD python3 ./main.py

