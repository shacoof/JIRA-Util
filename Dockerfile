FROM ubuntu:16.04
FROM python:3.7.5-slim


LABEL maintainer="Sharon.CohenOfir@Trilogy.com"

RUN apt-get update -y && \
    apt-get install -y python-pip python-dev


# We copy just the requirements.txt first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt

EXPOSE 5000

WORKDIR /app

RUN pip install --upgrade pip

ADD /shacoof /shacoof
RUN pip install -r requirements.txt

COPY . /app

ENTRYPOINT [ "python" ]

CMD [ "app.py" ]