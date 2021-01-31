# hacomfoairmqtt
Home Assistant integration for ComfoAir 350 device via serial communication and MQTT
This work is based on scripts created for Domoticz integration https://github.com/AlbertHakvoort/StorkAir-Zehnder-WHR-930-Domoticz-MQTT

`configuration.yaml` - sample entries for MQTT Fan integration device and service status binary_sensor

`src/ca350` - python script to communicate with the CA350 unit via serial port, publish data on MQTT broker and react to control messages

`src/config.ini.dist` - sample configuration file. Needs to be renamed to config.ini and customized

`rc.d/ca350` - rc.d script to set up the service in FreeNAS jail virtual python environment

`servicetest.sh` - simple script to test ca350 service status

File locations when installed on FreeNAS jail:
Python script: 
`/usr/local/share/ca350/bin`
Daemon config file: 
`/usr/local/etc/rc.d/ca350`


## Installation instructions:
1. The following packages are needed:
`sudo pkg install python3-pip python3-yaml`
2. Create directory for the application `/usr/local/share/ca350/bin/` and copy `src/ca350` script to it
3. Copy the src/config.ini.dist to /usr/local/share/ca350/bin/config.ini and update as required (serial port and MQTT server mainly)
4. Create virtual environment: 
`python3 -m venv /usr/local/share/ca350/`
5. install packages in the venv:
```
source /usr/local/share/ca350/bin/activate.csh
sudo pip3 install paho-mqtt pyserial
deactivate
```
6. Copy rc.d/ca350 script to the directory:
`/usr/local/etc/rc.d/`
7. Enable the service:
`service ca350 enable`
8. Start the service
`service ca350 start`

## Home Assistant Comfoair MQTT Configuration
Configuration Name | Description
------------ | -------------
SerialPort       | The Serialport to the Comfoair on the Host Linux Machine. Examples: /dev/ttyUSB0 or /dev/cuau3
MQTTServer       | IP Adress to your MQTT Server, may be different to the HA Server
MQTTPort         | Port of your MQTT Server. Default: 1833
MQTTKeepalive    | MQTT Keepalive Settings. Default: 45
MQTTUser         | MQTT User, if you enabled authorization on your MQTT Server. Default: False (no authentication)
MQTTPassword     | MQTT User Password, if you enabled authorization on your MQTT Server. Default: False (no authentication)
refresh_interval | Refresh Interval in Seconds. Default: 10
enablePcMode     | Automaticly enable PC Mode (disable comfosense). Default: False (disabled)
debug            | Enable Debug Output. Default: False (disabled)


## MQTT Auto Discovery Configutation:
If you are using MQTT in Home Assistant, you will probably have the Auto Discovery enabled by default. The MQTT AD implementation is expected to run with the prefix "homeassistant/". 

If you enable Autodiscovery in this Service, you will get following entities:

### Configuration: HAEnableAutoDiscoveryFan = True

Entity Name | Description
------------ | -------------
fan.ca350_fan | This will enable the fan described in the configuration.yaml example

### Configuration: HAEnableAutoDiscoverySensors = True 

Entity Name | Sensor/Binary Sensor
------------ | -------------
sensor.ca350_outsidetemp | Sensor: Outside Temperature 
sensor.ca350_supplytemp | Sensor: Supply Temperature
sensor.ca350_exhausttemp | Sensor: Exhaust Temperature
sensor.ca350_returntemp | Sensor: Return Temperatur
sensor.ca350_fan_speed_supply | Sensor: Supply Fan Speed
sensor.ca350_fan_speed_exhaust | Sensor: Exhaust Fan Speed
sendor.ca350_return_air_level | *ToDo: Currently exposing Fan Speed - as i am missing this data*
sensor.ca350_supply_air_level | *ToDo: Currently exposing Fan Speed - as i am missing this data*
sensor.ca350_supply_fan | Sensor: supply fan
binary_sensor.ca350_filterstatus | Binary Sensor: Filterstatus
binary_sensor.ca350_bypass_valve | Binary Sensor: Bypass valve
binary_sensor.ca350_summer_mode | Binary Seonsor: Summer Mode

### Configuration: HAEnableAutoDiscoveryClimate = False 
Adding the Comfoair as an HAVC makes sense, since it has a temperature control and a fan.

*This is still a work in progress*

Entity Name | Description
------------ | -------------
climate.ca350_fan | Expose Temperature Control & Fan Control

## HA Lovelace Widget:
The following Lovelace widgets depend on the MQTT AD enities and can be used with this service:

* https://github.com/TimWeyand/lovelace-comfoair
* https://github.com/mweimerskirch/lovelace-hacomfoairmqtt

## TODO:
- [ ] Create installation script for automatic installation of the script
- [ ] venv
- [ ] dependencies and the service. 
- [ ] Installation description for Debian based Linux Systems
- [ ] Correct implementation of climate
- [ ] Full Control in Home Assistant with a single Widget (Fan Speed, Temperature)
- [ ] React on input immediatly - Still Read on Interval Status
- [ ] Implement set_fan_levels() based on values from MQTT (e.g. input_numbers in HA) to set the fan levels for all modes. Also enables setting intake or exhaust fans only as in original controller.

Any help welcome!
