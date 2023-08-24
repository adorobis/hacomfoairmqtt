#!/bin/bash

# build config file
sed \
    -e "s|SerialPort=.*|SerialPort=${SERIAL_PORT}|"  \
    -e "s|RS485_protocol=.*|RS485_protocol=${RS485_PROTOCOL}|"  \
    -e "s|refresh_interval=.*|refresh_interval=${REFRESH_INTERVAL}|"  \
    -e "s|enablePcMode=.*|enablePcMode=${ENABLE_PC_MODE}|"  \
    -e "s|debug=.*|debug=${DEBUG}|"  \
    -e "s|MQTTServer=.*|MQTTServer=${MQTT_SERVER}|"  \
    -e "s|MQTTPort=.*|MQTTPort=${MQTT_PORT}|"  \
    -e "s|MQTTKeepalive=.*|MQTTKeepalive=${MQTT_KEEPALIVE}|"  \
    -e "s|MQTTUser=.*|MQTTUser=${MQTT_USER}|"  \
    -e "s|MQTTPassword=.*|MQTTPassword=${MQTT_PASSWORD}|"  \
    -e "s|HAEnableAutoDiscoverySensors=.*|HAEnableAutoDiscoverySensors=${HA_ENABLE_AUTO_DISCOVERY_SENSORS}|"  \
    -e "s|HAEnableAutoDiscoveryClimate=.*|HAEnableAutoDiscoveryClimate=${HA_ENABLE_AUTO_DISCOVERY_CLIMATE}|"  \
    -e "s|HAAutoDiscoveryDeviceId=.*|HAAutoDiscoveryDeviceId=${HA_AUTO_DISCOVERY_DEVICE_ID}|"  \
    -e "s|HAAutoDiscoveryDeviceName=.*|HAAutoDiscoveryDeviceName=${HA_AUTO_DISCOVERY_DEVICE_NAME}|"  \
    -e "s|HAAutoDiscoveryDeviceManufacturer=.*|HAAutoDiscoveryDeviceManufacturer=${HA_AUTO_DISCOVERY_DEVICE_MANUFACTURER}|"  \
    -e "s|HAAutoDiscoveryDeviceModel=.*|HAAutoDiscoveryDeviceModel=${HA_AUTO_DISCOVERY_DEVICE_MODEL}|"  \
    /opt/hacomfoairmqtt/config.ini.docker >  /opt/hacomfoairmqtt/config.ini

# Start the first process
if [ "$SOCAT" == "True" ]; then
    echo "create serial device over ethernet with socat for ip $COMFOAIR_IP:$COMFOAIR_PORT"
    /usr/bin/socat -d -d pty,link="$SERIAL_PORT",raw,group-late=dialout,mode=660 tcp:"$COMFOAIR_IP":"$COMFOAIR_PORT" &
    export SERIAL_DEVICE=/dev/comfoair
else
    echo "don't create serial device over ehternet. enable it with SOCAT=True"
fi

# Start the second process
/usr/bin/python3 /opt/hacomfoairmqtt/ca350.py &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?