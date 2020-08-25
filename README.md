# hacomfoairmqtt
Home Assistant integration for ComfoAir 350 device via serial communication and MQTT
This work is based on scripts created for Domoticz integration https://github.com/AlbertHakvoort/StorkAir-Zehnder-WHR-930-Domoticz-MQTT

configuration.yaml - sample entries for MQTT Fan integration device

src/ca350 - python script to communicate with the CA350 unit via serial port, publish data on MQTT broker and react to control messages

rc.d/ca350 - rc.d script to set up the service in FreeNAS jail virtual python environment

File locations when installed on FreeNAS jail:
Python script: 
/srv/ca350/bin/ca350
Daemon config file: 
/usr/local/etc/rc.d/ca350