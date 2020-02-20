# hacomfoairmqtt
Home Assistant integration for ComfoAir 350 device via serial communication and MQTT

configuration.yaml - sample entries for MQTT Fan integration device

src/ca350 - python script to communicate with the CA350 unit via serial port, publish data on MQTT broker and react to control messages

rc.d/ca350 - rc.d script to set up the service in FreeNAS jail virtual python environment
