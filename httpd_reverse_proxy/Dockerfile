FROM httpd:2.4
RUN apt-get update \
    && apt-get install -y python-pip
WORKDIR /httpd-manager
ADD . /httpd-manager
RUN pip install -r requirements.txt
CMD python httpd.py
EXPOSE 8080
