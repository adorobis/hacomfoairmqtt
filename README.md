# hacomfoairmqtt
Home Assistant integration for ComfoAir 350 device via serial communication and MQTT
This work is based on scripts created for Domoticz integration https://github.com/AlbertHakvoort/StorkAir-Zehnder-WHR-930-Domoticz-MQTT

`configuration.yaml` - sample entries for MQTT Fan integration device and service status binary_sensor

`src/ca350` - python script to communicate with the CA350 unit via serial port, publish data on MQTT broker and react to control messages

`rc.d/ca350` - rc.d script to set up the service in FreeNAS jail virtual python environment

`servicetest.sh` - simple script to test ca350 service status

File locations when installed on FreeNAS jail:
Python script: 
`/usr/local/share/ca350/bin`
Daemon config file: 
`/usr/local/etc/rc.d/ca350`


Installation instructions:
1. The following packages are needed:
`sudo pkg install python3-pip python3-yaml`
2. Create directory for the application `/usr/local/share/ca350/bin/` and copy `src/ca350` script to it
3. Update the script as required (serial port and MQTT server mainly)
4. Create virtual environment: 
`python3 -m venv /usr/local/share/ca350/bin/`
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

TODO:
Create installation script for automatic installation of the script, venv, dependencies and the service. Any help welcome!
