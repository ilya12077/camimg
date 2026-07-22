FROM python:3.11-slim

RUN apt-get update && apt-get upgrade -y && apt-get install -y emacs &&\
    apt-get autoremove -y
	
# Install software 
RUN apt-get install -y git


# Clone the conf files into the docker container
RUN git clone https://github.com/ilya12077/camimg.git
	
	
RUN cp -a ./camimg/. /etc/camimg/
RUN rm -r -f ./camimg/

RUN pip install -r /etc/camimg/requirements.txt

ENV AM_I_IN_A_DOCKER_CONTAINER Yes
EXPOSE 8867/tcp
CMD ["python", "/etc/camimg/main.py"]
