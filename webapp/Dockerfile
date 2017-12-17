FROM ubuntu:14.04
RUN apt-get update \
    && apt-get install -y python-pip
WORKDIR /myapp
ADD . /myapp
RUN pip install -r requirements.txt
CMD python app.py
EXPOSE 5000

