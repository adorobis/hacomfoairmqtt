FROM ubuntu:22.04
LABEL maintainer="jens@schanz.cloud"
LABEL version="0.1"
LABEL description="Docker image for hacomfoairmqtt and serial over IP"

ENV SOCAT="True"
ENV COMFOAIR_IP="192.168.1.50"
ENV COMFOAIR_PORT="502"
ENV SERIAL_PORT="/dev/comfoair"
ENV RS485_PROTOCOL="False"
ENV REFRESH_INTERVAL="10"
ENV ENABLE_PC_MODE="False"
ENV DEBUG="False"
ENV MQTT_SERVER="mosquitto.domain.tld"
ENV MQTT_PORT="1883"
ENV MQTT_KEEPALIVE="45"
ENV MQTT_USER="username"
ENV MQTT_PASSWORD="password"
ENV HA_ENABLE_AUTO_DISCOVERY_SENSORS="True"
ENV HA_ENABLE_AUTO_DISCOVERY_CLIMATE="True"
ENV HA_AUTO_DISCOVERY_DEVICE_ID="ca350"
ENV HA_AUTO_DISCOVERY_DEVICE_NAME="CA350"
ENV HA_AUTO_DISCOVERY_DEVICE_MANUFACTURER="Zehnder"
ENV HA_AUTO_DISCOVERY_DEVICE_MODEL="ComfoAir 350"

RUN apt update
RUN apt upgrade -y
RUN apt install -y socat python3-paho-mqtt python3-serial python3-yaml

RUN mkdir -p /opt/hacomfoairmqtt
COPY src/ca350.py /opt/hacomfoairmqtt/ca350.py
COPY src/config.ini.docker /opt/hacomfoairmqtt/config.ini.docker

RUN sed \
    -e "s|{{SERIAL_PORT}}|${SERIAL_PORT}|"  \
    -e "s|{{RS485_PROTOCOL}}|${RS485_PROTOCOL}|"  \
    -e "s|{{REFRESH_INTERVAL}}|${REFRESH_INTERVAL}|"  \
    -e "s|{{ENABLE_PC_MODE}}|${ENABLE_PC_MODE}|"  \
    -e "s|{{DEBUG}}|${DEBUG}|"  \
    -e "s|{{MQTT_SERVER}}|${MQTT_SERVER}|"  \
    -e "s|{{MQTT_PORT}}|${MQTT_PORT}|"  \
    -e "s|{{MQTT_KEEPALIVE}}|${MQTT_KEEPALIVE}|"  \
    -e "s|{{MQTT_USER}}|${MQTT_USER}|"  \
    -e "s|{{MQTT_PASSWORD}}|${MQTT_PASSWORD}|"  \
    -e "s|{{HA_ENABLE_AUTO_DISCOVERY_SENSORS}}|${HA_ENABLE_AUTO_DISCOVERY_SENSORS}|"  \
    -e "s|{{HA_ENABLE_AUTO_DISCOVERY_CLIMATE}}|${HA_ENABLE_AUTO_DISCOVERY_CLIMATE}|"  \
    -e "s|{{HA_AUTO_DISCOVERY_DEVICE_ID}}|${HA_AUTO_DISCOVERY_DEVICE_ID}|"  \
    -e "s|{{HA_AUTO_DISCOVERY_DEVICE_NAME}}|${HA_AUTO_DISCOVERY_DEVICE_NAME}|"  \
    -e "s|{{HA_AUTO_DISCOVERY_DEVICE_MANUFACTURER}}|${HA_AUTO_DISCOVERY_DEVICE_MANUFACTURER}|"  \
    -e "s|{{HA_AUTO_DISCOVERY_DEVICE_MODEL}}|${HA_AUTO_DISCOVERY_DEVICE_MODEL}|"  \   
    /opt/hacomfoairmqtt/config.ini.docker >  /opt/hacomfoairmqtt/config.ini

COPY src/start.sh /usr/local/bin/start.sh
RUN chmod 744 /usr/local/bin/start.sh
CMD /usr/local/bin/start.sh
