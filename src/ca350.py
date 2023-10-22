#!/usr/local/share/ca350/bin/python3.9
# -*- coding: utf-8 -*-

"""
Interface with a StorkAir CA350 on Home Assistant
Version 0.1 by adorobis[@]gmail[.]com
based on code from https://github.com/AlbertHakvoort/StorkAir-Zehnder-WHR-930-Domoticz-MQTT
Publish every 15 seconds the status on a MQTT comfoair/speed and comfoair/on topics
This is to integrate with FAN device type in Home Assistant deployed on FreeNAS jail
Listen on MQTT topic for commands to set the ventilation level
todo :
- set bypass temperature
- turn on/off intake and exhaust ventilators
- check on faulty messages
- serial check
The following packages are needed:
sudo pkg install py37-serial python3-pip python3-yaml
sudo pip3 install paho-mqtt
start script with python3.7 ca350
"""

import paho.mqtt.client as mqtt
import time
import serial
import sys
import configparser
import os
import json

# Read configuration from ini file
config = configparser.ConfigParser()
config.read(os.path.dirname(os.path.abspath(__file__)) + '/config.ini')

# Service Configuration
SerialPort = config['DEFAULT']['SerialPort']                   # Serial port CA350 RS232 direct or via USB TTL adapter
RS485_protocol = config['DEFAULT']['RS485_protocol'] == 'True' # Protocol type
refresh_interval = int(config['DEFAULT']['refresh_interval'])  # Interval in seconds at which data from RS232 will be polled
enablePcMode = config['DEFAULT']['enablePcMode'] == 'True'     # automatically enable PC Mode (disable comfosense)
debug = config['DEFAULT']['debug'] == 'True'

#Fan % configuration for each ventilation level
FanOutAbsent = int(config['DEVICE']['FanOutAbsent'])
FanOutLow = int(config['DEVICE']['FanOutLow'])
FanOutMid = int(config['DEVICE']['FanOutMid'])
FanOutHigh = int(config['DEVICE']['FanOutHigh'])
FanInAbsent = int(config['DEVICE']['FanInAbsent'])
FanInLow = int(config['DEVICE']['FanInLow'])
FanInMid = int(config['DEVICE']['FanInMid'])
FanInHigh = int(config['DEVICE']['FanInHigh'])

#Set fan levels at the start of the program. If false will be only controlled when fans are enabled or disabled.
SetUpFanLevelsAtStart = config['DEVICE']['SetUpFanLevelsAtStart'] == 'True'

MQTTServer = config['MQTT']['MQTTServer']            # MQTT broker - IP
MQTTPort = int(config['MQTT']['MQTTPort'])           # MQTT broker - Port
MQTTKeepalive = int(config['MQTT']['MQTTKeepalive']) # MQTT broker - keepalive
MQTTUser = config['MQTT']['MQTTUser']                # MQTT broker - user - default: 0 (disabled/no authentication)
MQTTPassword = config['MQTT']['MQTTPassword']        # MQTT broker - password - default: 0 (disabled/no authentication)

HAEnableAutoDiscoverySensors = config['HA']['HAEnableAutoDiscoverySensors'] == 'True' # Home Assistant send auto discovery for temperatures
HAEnableAutoDiscoveryClimate = config['HA']['HAEnableAutoDiscoveryClimate'] == 'True' # Home Assistant send auto discovery for climate

HAAutoDiscoveryDeviceName = config['HA']['HAAutoDiscoveryDeviceName']            # Home Assistant Device Name

# Used for Home Assistant device discovery
HAAutoDiscoveryDeviceId = config['HA']['HAAutoDiscoveryDeviceId']     # Home Assistant Unique Id
HAAutoDiscoveryDeviceManufacturer = config['HA']['HAAutoDiscoveryDeviceManufacturer']
HAAutoDiscoveryDeviceModel = config['HA']['HAAutoDiscoveryDeviceModel']


print("*****************************")
print("* CA350 MQTT Home Assistant *")
print("*****************************")
print("")

def debug_msg(message):
    if debug is True:
        print('{0} DEBUG: {1}'.format(time.strftime("%d-%m-%Y %H:%M:%S", time.gmtime()), message))

def warning_msg(message):
    print('{0} WARNING: {1}'.format(time.strftime("%d-%m-%Y %H:%M:%S", time.gmtime()), message))

def info_msg(message):
    print('{0} INFO: {1}'.format(time.strftime("%d-%m-%Y %H:%M:%S", time.gmtime()), message))

# Get the checksum from the serial data (third to last byte)
def get_returned_checksum(serial_data):
    return serial_data[-3:-2]

# Calculate the checksum for a given byte string received from the serial connection.
# The checksum is calculated by adding all bytes (excluding start and end) plus 173.
# If the value 0x07 appears twice in the data area, only one 0x07 is used for the checksum calculation.
# If the checksum is greater than one byte, the least significant byte is used.
def calculate_checksum(serial_data_slice):
    checksum = 173
    seven_encountered = False

    for byte in serial_data_slice:
        if byte == 0x07:
            if not seven_encountered:
                seven_encountered = True  # Mark that we have encountered the first 0x07
            else:
                seven_encountered = False # Next one will be counted again
                continue  # Skip the seconds 0x07

        checksum += int(byte)

    return checksum.to_bytes(((checksum.bit_length() + 8) // 8), byteorder='big')[-1:]

# Calculate the length for a given byte string received from the serial connection.
# If the value 0x07 appears twice in the data area, only one 0x07 is used for the checksum calculation.
def calculate_length(serial_data_slice):
    length = 0
    seven_encountered = False

    for byte in serial_data_slice:
        if byte == 0x07:
            if not seven_encountered:
                seven_encountered = True  # Mark that we have encountered the first 0x07
            else:
                seven_encountered = False # Next one will be counted again
                continue  # Skip the seconds 0x07

        length += 1

    return length.to_bytes(1, byteorder='big')

# Filter the data from the serial connection to find the output we're looking for.
# The serial connection is sometimes busy with input/output from other devices (e. g. ComfoSense).
# Then, validate the checksum for the output we're looking for.
# Currently, the data returned is passed as a string, so we'll need to convert it back to bytes for easier handling.
def filter_and_validate(data, result_command):
    split_data = split_result(data)

    for line in split_data:
        if not (len(line) == 2 and line[0] == b'\x07' and line[1] == b'\xf3'):  # Check if it's not an ACK
            if (
                    len(line) >= 7 and
                    line[0:2] == b'\x07\xf0' and  # correct start
                    line[-2:] == b'\x07\x0f' and  # correct end
                    line[2:4] == result_command[0:2] # is it the return we're looking for
            ):
                # Validate length of data
                line_length = calculate_length(line[5:-3])  # Strip start, command, length, checksum and end
                if line[4:5] != line_length:
                    warning_msg('Incorrect length')
                    return None

                # Validate checksum
                returned_checksum = get_returned_checksum(line)
                calculated_checksum = calculate_checksum(line[2:-3])  # Strip start, checksum and end
                if returned_checksum != calculated_checksum:
                    warning_msg('Incorrect checksum')
                    return None

                return line[5:-3]  # Only return data, no start, end, length and checksum

    warning_msg('Expected return not found')
    return None

def on_message(client, userdata, message):
    #print("message check")
    msg_data = str(message.payload.decode("utf-8"))
    fan_level = -1
    if message.topic == "comfoair/ha_climate_mode/fan/set":
        selector = msg_data
        if selector == "off":
            print("comfoair/ha_climate_mode/fan/set is off (speed 10)")
            fan_level = 1
        elif selector == "low":
            print("comfoair/ha_climate_mode/fan/set is low (speed 20)")
            fan_level = 2
        elif selector == "medium":
            print("comfoair/ha_climate_mode/fan/set is medium (speed 30)")
            fan_level = 3
        elif selector == "high":
            print("comfoair/ha_climate_mode/fan/set is high (speed 40)")
            fan_level = 4
        else:
            print("comfoair/ha_climate_mode/fan/set got unkown value "+msg_data)
    elif message.topic == "comfoair/ha_climate_mode/set":
        selector = msg_data
        if selector == "off":
            print("comfoair/on/set is 10")
            fan_level = 1
        elif selector == "fan_only":
            print("comfoair/on/set is 20")
            fan_level = 2
    elif message.topic == "comfoair/comforttemp/set":
        comforttemp = int(float(msg_data))
        if RS485_protocol == False:
            set_comfort_temperature(comforttemp)
            get_temp()
    elif message.topic == "comfoair/reset_filter":
        selector = msg_data
        if selector == "PRESS":
            reset_filter_timer()
    elif message.topic == "comfoair/filterweeks":
        filter_weeks = int(msg_data)    
        set_filter_weeks(filter_weeks)
    elif message.topic == "comfoair/fancontrol/set":
        if msg_data == "Both":
            set_fan_levels(Intake=True, Exhaust=True)
        elif msg_data == "In":
            set_fan_levels(Intake=True, Exhaust=False)
        elif msg_data == "Out":
            set_fan_levels(Intake=False, Exhaust=True)
        elif msg_data == "off":
            set_fan_levels(Intake=False, Exhaust=False)
    elif message.topic == "comfoair/ewtlowtemp":
        ewtlowtemp = int(msg_data)
        set_ewt(ewtlowtemp=ewtlowtemp)
    elif message.topic == "comfoair/ewthightemp":
        ewthightemp = int(msg_data)
        set_ewt(ewthightemp=ewthightemp)
    elif message.topic == "comfoair/ewtspeedup":
        print("Message "+message.topic+" with message: "+msg_data)
        ewtspeedup = int(msg_data)
        set_ewt(ewtspeedup=ewtspeedup)
    else:
        print("Message "+message.topic+" with message: "+msg_data+" ignored")
    print('FanLevel ' + str(fan_level))
    if 0 <= fan_level <= 4:
        if RS485_protocol == False:
            set_ventilation_level(fan_level)

def publish_message(msg, mqtt_path):
    try:
        mqttc.publish(mqtt_path, payload=msg, qos=0, retain=True)
    except:
        warning_msg('Publishing message '+msg+' to topic '+mqtt_path+' failed.')
        warning_msg('Exception information:')
        warning_msg(sys.exc_info())
    else:
        time.sleep(0.1)
        debug_msg('published message {0} on topic {1} at {2}'.format(msg, mqtt_path, time.asctime(time.localtime(time.time()))))

def delete_message(mqtt_path):
    try:
        mqttc.publish(mqtt_path, payload="", qos=0, retain=False)
    except:
        warning_msg('Deleting topic ' + mqtt_path + ' failed.')
        warning_msg('Exception information:')
        warning_msg(sys.exc_info())
    else:
        time.sleep(0.1)
        debug_msg('delete topic {0} at {1}'.format(mqtt_path, time.asctime(time.localtime(time.time()))))

def serial_command(cmd):
    try:
        data = b''
        ser.write(cmd)
        time.sleep(2)

        while ser.inWaiting() > 0:
            data += ser.read(1)
        if len(data) > 0:
            return data
        else:
            return None
    except:
        warning_msg('Serial command write and read exception:')
        warning_msg(sys.exc_info())
        return None

# Write serial data for the given command and data.
# Start, end as well as the length and checksum are added automatically.
def send_command(command, data, expect_reply=True):
    start = b'\x07\xF0'
    end = b'\x07\x0F'
    if data is None:
        length = b'\x00'
        command_plus_data = command + length
    else:
        length_int = len(data)
        length = length_int.to_bytes(((length_int.bit_length() + 8) // 8), byteorder='big')[-1:]
        command_plus_data = command + length + data

    checksum = calculate_checksum(command_plus_data)

    cmd = start + command_plus_data + checksum + end

    result = serial_command(cmd)

    if expect_reply:
        if result:
            if RS485_protocol == False:
                # Increment the command by 1 to get the expected result command for RS232
                result_command_int = int.from_bytes(command, byteorder='big') + 1
            else:
                # Decrement the command by 1 to get the expected result command for RS485
                result_command_int = int.from_bytes(command, byteorder='big') - 1
            result_command = result_command_int.to_bytes(2, byteorder='big')
            filtered_result = filter_and_validate(result, result_command)
            if filtered_result:
                ser.write(b'\x07\xF3')  # Send an ACK after receiving the correct result
                return filtered_result
    else:
        # TODO: Maybe check if there was an "ACK", but given the noise on the serial bus, not sure if that makes sense.
        return True

    return None

# Split the data at \x07\f0 (start) or \x07\xf3 (ACK)
def split_result(data):
    split_data = []
    line = b''

    for index in range(len(data)):
        byte = data[index:index+1]
        nextbyte = data[index+1:index+2]
        if index > 0 and len(data) > index+2 and (byte == b'\x07' and nextbyte == b'\xf0' or byte == b'\x07' and nextbyte == b'\xf3'):
            split_data.append(line)
            line = b''
        line += byte

    split_data.append(line)
    return split_data

#RS232 commands

def set_ventilation_level(nr):
    if 0 <= nr <= 4:
        data = send_command(b'\x00\x99', bytes([nr]), expect_reply=False)
    else:
        data = False
        warning_msg('Wrong parameter: {0}'.format(nr))

    if data:
        info_msg('Changed the ventilation to {0}'.format(nr))
        get_ventilation_status()
        get_fan_status()
    else:
        warning_msg('Changing the ventilation to {0} went wrong, received invalid data after the set command'.format(nr))
        time.sleep(2)
        set_ventilation_level(nr)

def set_pc_mode(nr):
    if 0 <= nr <= 4 and nr != 2:
        data = send_command(b'\x00\x9B', bytes([nr]))
    else:
        data = None
        warning_msg('Wrong parameter: {0}'.format(nr))

    if data:
        info_msg('Changed RS232 mode to {0}'.format(nr))
    else:
        warning_msg('Changing the RS232 mode went wrong')

def set_comfort_temperature(nr):
    if 15 <= nr <= 27:
        data = send_command(b'\x00\xD3', bytes([nr * 2 + 40]), expect_reply=False)
    else:
        data = None
        warning_msg('Wrong temperature provided: {0}. No changes made.'.format(nr))

    if data:
        info_msg('Changed comfort temperature to {0}'.format(nr))
        get_temp()
        get_bypass_status()
    else:
        warning_msg('Changing comfort temperature to {0} went wrong, did not receive an ACK after the set command'.format(nr))
        time.sleep(2)
        set_comfort_temperature(nr)

def get_temp():
    data = send_command(b'\x00\xD1', None)
    EWTTemp = None
    if data is None:
        warning_msg('get_temp function could not get serial data')
    else:
        if len(data) > 4:
            ComfortTemp = data[0] / 2.0 - 20
            OutsideAirTemp = data[1] / 2.0 - 20
            SupplyAirTemp = data[2] / 2.0 - 20
            ReturnAirTemp = data[3] / 2.0 - 20
            ExhaustAirTemp = data[4] / 2.0 - 20
#            SensorsInstalled = data[5]
#            info_msg('Sensors installed {0} :'.SensorsInstalled)
            if len(data) > 6:
                EWTTemp = data[6] / 2.0 - 20
				
            if 10 < ComfortTemp < 30:
                publish_message(msg=str(ComfortTemp), mqtt_path='comfoair/comforttemp')
                publish_message(msg=str(OutsideAirTemp), mqtt_path='comfoair/outsidetemp')
                publish_message(msg=str(SupplyAirTemp), mqtt_path='comfoair/supplytemp')
                publish_message(msg=str(ExhaustAirTemp), mqtt_path='comfoair/exhausttemp')
                publish_message(msg=str(ReturnAirTemp), mqtt_path='comfoair/returntemp')
                if EWTTemp is not None:
                    publish_message(msg=str(EWTTemp), mqtt_path='comfoair/ewttemp')
                debug_msg('OutsideAirTemp: {0}, SupplyAirTemp: {1}, ReturnAirTemp: {2}, ExhaustAirTemp: {3}, ComfortTemp: {4}, EWTTemp: {5}'.format(OutsideAirTemp, SupplyAirTemp, ReturnAirTemp, ExhaustAirTemp, ComfortTemp, EWTTemp))
            else:
                warning_msg('get_temp returned bad temp data. Retrying in 2 sec')
                warning_msg('OutsideAirTemp: {0}, SupplyAirTemp: {1}, ReturnAirTemp: {2}, ExhaustAirTemp: {3}, ComfortTemp: {4}, EWTTemp: {5}'.format(OutsideAirTemp, SupplyAirTemp, ReturnAirTemp, ExhaustAirTemp, ComfortTemp, EWTTemp))
                get_temp()
        else:
            warning_msg('get_temp function: incorrect data received')
def get_ewt():

    data = send_command(b'\x00\xEB', None)
    ewtdata = []
    if data is None:
        warning_msg('get_ewt function could not get serial data')
    else:
        if len(data) > 4:
            EWTLowTemp = data[0] / 2.0 - 20
            EWTHighTemp = data[1] / 2.0 - 20
            EWTSpeedUp = data[2]
				
            if -1 < EWTSpeedUp < 100:
                publish_message(msg=str(EWTLowTemp), mqtt_path='comfoair/ewtlowtemp_state')
                publish_message(msg=str(EWTHighTemp), mqtt_path='comfoair/ewthightemp_state')
                publish_message(msg=str(EWTSpeedUp), mqtt_path='comfoair/ewtspeedup_state')
                
                ewtdata.append(EWTLowTemp)
                ewtdata.append(EWTHighTemp)
                ewtdata.append(EWTSpeedUp)
                
                if EWTLowTemp < 0 or EWTHighTemp < 10:
                    if EWTLowTemp < 0:
                        EWTLowTemp = 0
                    if EWTHighTemp < 10:
                        EWTHighTemp = 10
                    debug_msg('EWTLowTemp: {0}, EWTHighTemp: {1}, EWTSpeedUp: {2}'.format(EWTLowTemp, EWTHighTemp, EWTSpeedUp))
                    set_ewt(EWTLowTemp, EWTHighTemp, EWTSpeedUp, True)
                    warning_msg('EWT Settings out of range, correcting to minimal temperature values')
                    time.sleep(10)
                    get_ewt()
                
            else:
                warning_msg('get_ewt returned bad data. Retrying in 2 sec')
                warning_msg('EWTLowTemp: {0}, EWTHighTemp: {1}, EWTSpeedUp: {2}'.format(EWTLowTemp, EWTHighTemp, EWTSpeedUp))
                time.sleep(2)
                get_ewt()
        else:
            warning_msg('get_ewt function: incorrect data received')

    return ewtdata

def set_ewt(ewtlowtemp=None, ewthightemp=None, ewtspeedup=None, initial=False):

    ewtdata = []
    if initial == False:
        ewtdata = get_ewt()
        warning_msg('get_ewt received data {0} '.format(ewtdata))
    else:
        ewtdata.append(ewtlowtemp)
        ewtdata.append(ewthightemp)
        ewtdata.append(ewtspeedup)
        
    if len(ewtdata) == 0:
        warning_msg('set_ewt function has not received ewt serial data')
    else:
        if ewtlowtemp is None:
            data1 = bytes([int(ewtdata[0] * 2 + 40)])
        else:
            data1 = bytes([ewtlowtemp * 2 + 40])

        if ewthightemp is None:
            data2 = bytes([int(ewtdata[1] * 2 + 40)])
        else:
            data2 = bytes([ewthightemp * 2 + 40])

        if ewtspeedup is None:
            data3 = bytes([ewtdata[2]])
        else:
            data3 = bytes([ewtspeedup])

        datasend = data1 + data2 + data3
        debug_msg('ewt data do be sent {0} '.format(datasend))
        data = send_command(b'\x00\xED', datasend, expect_reply=True)
        
        if data is None:
            warning_msg('function set_ewt could not get serial data, retrying in 2 seconds')
            time.sleep(2)
            data = send_command(b'\x00\xED', datasend, expect_reply=True)

            
def get_analog_sensor():
    data = send_command(b'\x00\x97', None)
    if data is None:
        warning_msg('get_analog_sensor function could not get serial data')
    else:
        if len(data) > 13:
            Analog1 = data[2]
            Analog2 = data[3]
            Analog3 = data[12]
            Analog4 = data[13]
            
            publish_message(msg=str(Analog1), mqtt_path='comfoair/analog_sensor_1')
            publish_message(msg=str(Analog2), mqtt_path='comfoair/analog_sensor_2')
            publish_message(msg=str(Analog3), mqtt_path='comfoair/analog_sensor_3')
            publish_message(msg=str(Analog4), mqtt_path='comfoair/analog_sensor_4')
		
            debug_msg('Analog sensors: 1: {0} %, 2: {1} %, 3: {2} %, 4: {3} %'.format(Analog1, Analog2, Analog3, Analog4))
        else:
            warning_msg('get_analog_sensor function: incorrect data received')

def set_fan_levels(Intake=True, Exhaust=True):

    if Intake:
        InAbsent = bytes([FanInAbsent])
        InLow = bytes([FanInLow])
        InMid = bytes([FanInMid])
        InHigh = bytes([FanInHigh])
    else:
        InAbsent = bytes([0])
        InLow = bytes([0])
        InMid = bytes([0])
        InHigh = bytes([0])
    if Exhaust:
        OutAbsent = bytes([FanOutAbsent])
        OutLow = bytes([FanOutLow])
        OutMid = bytes([FanOutMid])
        OutHigh = bytes([FanOutHigh])
    else:
        OutAbsent = bytes([0])
        OutLow = bytes([0])
        OutMid = bytes([0])
        OutHigh = bytes([0])
    
    debug_msg('Fan levels config: FanOutAbsent: {0} %, FanOutLow: {1} %, FanOutMid: {2} %, FanInAbsent: {3} %'.format(FanOutAbsent, FanOutLow, FanOutMid, FanInAbsent))
    
    datasend = OutAbsent + OutLow + OutMid + InAbsent + InLow + InMid + OutHigh + InHigh
    
    debug_msg('Fan levels data do be sent {0} '.format(datasend))
    
    data = send_command(b'\x00\xCF', datasend, expect_reply=False)

    if data:
        info_msg('Changed the fan levels')
        time.sleep(10)
        get_ventilation_status()
        get_fan_status()
    else:
        warning_msg('Changing the fan levels went wrong, received invalid data after the set command')
        time.sleep(2)
        set_fan_levels(Intake, Exhaust)
        get_ventilation_status()
        get_fan_status()

def get_ventilation_status():
    data = send_command(b'\x00\xCD', None)

    if data is None:
        warning_msg('get_ventilation_status function could not get serial data')
    else:
        if len(data) > 12:
            ReturnAirLevel = data[6]
            SupplyAirLevel = data[7]
            FanLevel = data[8]
            IntakeFanActive = data[9]
            OutAbsent = data[0]
            OutLow = data[1]
            OutMid = data[2]
            InAbsent = data[3]
            InLow = data[4]
            InMid = data[5]
            OutHigh = data[10]
            InHigh = data[11]
            
            debug_msg('OutAbsent: {}, OutLow: {}, OutMid: {}, OutHigh: {}, InAbsent: {}, InLow: {}, InMid: {}, InHigh: {}'.format(OutAbsent, OutLow, OutMid, OutHigh, InAbsent, InLow, InMid, InHigh))

            if IntakeFanActive == 1:
                StrIntakeFanActive = 'Yes'
            elif IntakeFanActive == 0:
                StrIntakeFanActive = 'No'
            else:
                StrIntakeFanActive = 'Unknown'

            debug_msg('ReturnAirLevel: {}, SupplyAirLevel: {}, FanLevel: {}, IntakeFanActive: {}'.format(ReturnAirLevel, SupplyAirLevel, FanLevel, StrIntakeFanActive))

            if OutLow == 0 and InLow == 0:
                publish_message(msg='off', mqtt_path='comfoair/fancontrol')
            elif OutLow > 0 and InLow == 0:
                publish_message(msg='Out', mqtt_path='comfoair/fancontrol')
            elif OutLow == 0 and InLow > 0:
                publish_message(msg='In', mqtt_path='comfoair/fancontrol')
            else:
                publish_message(msg='Both', mqtt_path='comfoair/fancontrol')

            if FanLevel == 1:
                publish_message(msg='off', mqtt_path='comfoair/ha_climate_mode')
                publish_message(msg='off', mqtt_path='comfoair/ha_climate_mode/fan')
            elif FanLevel == 2 or FanLevel == 3 or FanLevel == 4:
                publish_message(msg='fan_only', mqtt_path='comfoair/ha_climate_mode')
                if FanLevel == 2:
                  publish_message(msg='low', mqtt_path='comfoair/ha_climate_mode/fan')
                elif FanLevel == 3:
                  publish_message(msg='medium', mqtt_path='comfoair/ha_climate_mode/fan')
                elif FanLevel == 4:
                  publish_message(msg='high', mqtt_path='comfoair/ha_climate_mode/fan')
            else:
                warning_msg('Wrong FanLevel value: {0}'.format(FanLevel))
                time.sleep(2)
                get_ventilation_status()
        else:
            warning_msg('get_ventilation_status function: incorrect data received')

def get_fan_status():
    data = send_command(b'\x00\x0B', None)

    if data is None:
        warning_msg('function get_fan_status could not get serial data')
    else:
        if len(data) > 5:
            IntakeFanSpeed  = data[0]
            ExhaustFanSpeed = data[1]
            if IntakeFanSpeed != 0 and int.from_bytes(data[2:4], byteorder='big') != 0:
                IntakeFanRPM    = int(1875000 / int.from_bytes(data[2:4], byteorder='big'))
            else:
                IntakeFanRPM    = 0
            if ExhaustFanSpeed != 0 and int.from_bytes(data[4:6], byteorder='big') != 0:
                ExhaustFanRPM   = int(1875000 / int.from_bytes(data[4:6], byteorder='big'))
            else:
                ExhaustFanRPM   = 0

            publish_message(msg=str(IntakeFanSpeed), mqtt_path='comfoair/intakefanspeed')
            publish_message(msg=str(ExhaustFanSpeed), mqtt_path='comfoair/exhaustfanspeed')
            publish_message(msg=str(IntakeFanRPM), mqtt_path='comfoair/intakefanrpm')
            publish_message(msg=str(ExhaustFanRPM), mqtt_path='comfoair/exhaustfanrpm')
            debug_msg('IntakeFanSpeed {0}%, ExhaustFanSpeed {1}%, IntakeAirRPM {2}, ExhaustAirRPM {3}'.format(IntakeFanSpeed, ExhaustFanSpeed, IntakeFanRPM, ExhaustFanRPM))
        else:
            warning_msg('function get_fan_status data array too short')

def get_bypass_status():
    data = send_command(b'\x00\xDF', None)

    if data is None:
        warning_msg('function get_bypass_status could not get serial data')
    else:
        if len(data) > 6:
            BypassStatus = data[3]
            SummerMode = data[6]
            publish_message(msg=str(BypassStatus), mqtt_path='comfoair/bypassstatus')
            if BypassStatus == 0:
                publish_message(msg='OFF', mqtt_path='comfoair/ca350_bypass_valve')
            else:
                publish_message(msg='ON', mqtt_path='comfoair/ca350_bypass_valve')
            if SummerMode == 1:
                publish_message(msg='Summer', mqtt_path='comfoair/bypassmode')
                publish_message(msg='ON', mqtt_path='comfoair/ca350_summer_mode')
            else:
                publish_message(msg='Winter', mqtt_path='comfoair/bypassmode')
                publish_message(msg='OFF', mqtt_path='comfoair/ca350_summer_mode')
        else:
            warning_msg('function get_bypass_status data array too short')

def get_preheating_status():
    data = send_command(b'\x00\xE1', None)

    if data is None:
        warning_msg('function get_preheating_status could not get serial data')
    else:
        if len(data) > 5:
            PreheatingStatus = data[2]
            if PreheatingStatus == 0:
                publish_message(msg='OFF', mqtt_path='comfoair/preheatingstatus')
            else:
                publish_message(msg='ON', mqtt_path='comfoair/preheatingstatus')
        else:
            warning_msg('function get_preheating_status data array too short')

def get_filter_status():
    data = send_command(b'\x00\xD9', None)

    if data is None:
        warning_msg('get_filter_status function could not get serial data')
    else:
        if len(data) > 16:
            
            if data[8] == 0:
                FilterStatus = 'Ok'
                FilterStatusBinary = 'OFF'
            elif data[8] == 1:
                FilterStatus = 'Full'
                FilterStatusBinary = 'ON'
            else:
                FilterStatus = 'Unknown'
                FilterStatusBinary = 'OFF'
            publish_message(msg=str(FilterStatus), mqtt_path='comfoair/filterstatus')
            publish_message(msg=str(FilterStatusBinary), mqtt_path='comfoair/filterstatus_binary')
            debug_msg('FilterStatus: {0}'.format(FilterStatus))
        else:
            warning_msg('get_filter_status data array too short')

def get_filter_weeks():
    data = send_command(b'\x00\xC9', None)
    if data is None:
        warning_msg('function get_filter_weeks could not get serial data')
    else:
        if len(data) > 4:
            FilterWeeks = data[4]
            publish_message(msg=str(FilterWeeks), mqtt_path='comfoair/filterweeks_state')
        else:
            warning_msg('function get_filter_weeks data array too short')

def set_filter_weeks(nr):

    if 0 <= nr < 256:
        start = b'\x00\x00\x00\x00'
        weeks = bytes([nr])
        end = b'\x00\x00\x00'
        datasend = start + weeks + end
        data = send_command(b'\x00\xCB', datasend, expect_reply=False)
        if data is None:
            warning_msg('function set_filter_weeks could not get serial data')
    
    else:
        warning_msg('function set_filter_weeks wrong number')
            
def get_filter_hours():
    data = send_command(b'\x00\xDD', None)

    if data is None:
        warning_msg('function get_filter_hours could not get serial data')
    else:
        if len(data) > 16:
            FilterHours = int.from_bytes(data[15:17], byteorder='big')
            publish_message(msg=str(FilterHours), mqtt_path='comfoair/filterhours')
        else:
            warning_msg('function get_filter_hours data array too short')
            
def reset_filter_timer():
    data = send_command(b'\x00\x37', b'\x00\x82\x00\x00\x00\x00\x00', expect_reply=False)

    if data is None:
        warning_msg('reset_filter_timer function could not get serial data')
    else:
        get_filter_weeks()
        get_filter_hours()
        get_filter_status()


# RS485 commands

def get_temp_rs485():
    data = send_command(b'\x00\x85', None)		

    if data is None:
        warning_msg('get_temp function could not get serial data')
    else:
        if len(data) > 5:
            SupplyAirTemp = 0 #dummy value because it is not available
            BypassStatus = data[0]
            #data[1:2] unknown, seems like status info
            ExhaustAirTemp = data[3] / 2.0 - 20
            ReturnAirTemp = data[4] / 2.0 - 20
            OutsideAirTemp = data[5] / 2.0 - 20
            #data[6:7] optional temperature sensors?
            #data[8:9] unknown, seems like status info
				
            publish_message(msg=str(BypassStatus), mqtt_path='comfoair/bypassstatus')
            publish_message(msg=str(OutsideAirTemp), mqtt_path='comfoair/outsidetemp')
            publish_message(msg=str(SupplyAirTemp), mqtt_path='comfoair/supplytemp')
            publish_message(msg=str(ExhaustAirTemp), mqtt_path='comfoair/exhausttemp')
            publish_message(msg=str(ReturnAirTemp), mqtt_path='comfoair/returntemp')
            debug_msg('BypassStatus: {}, ExhaustAirTemp: {}, ReturnAirTemp: {}, OutsideAirTemp: {}'.format(BypassStatus, ExhaustAirTemp, ReturnAirTemp, OutsideAirTemp))
        else:
            warning_msg('get_temp function: incorrect data received')

def get_fan_status_rs485():
    data = send_command(b'\x00\x87', None)
    if data is None:
        warning_msg('function get_fan_status could not get serial data')
    else:
        if len(data) > 9:
            IntakeFanSpeed  = data[0]
            ExhaustFanSpeed = data[1]  
            IntakeFanRPM    = data[2] * 20
            ExhaustFanRPM   = data[3] * 20
            #data[4:7] unknown, (input) states?
            FanLevel        = data[8] + 1
            #data[9:10] unknown, (input) states?

            publish_message(msg=str(IntakeFanSpeed), mqtt_path='comfoair/intakefanspeed')
            publish_message(msg=str(ExhaustFanSpeed), mqtt_path='comfoair/exhaustfanspeed')
            publish_message(msg=str(IntakeFanRPM), mqtt_path='comfoair/intakefanrpm')
            publish_message(msg=str(ExhaustFanRPM), mqtt_path='comfoair/exhaustfanrpm')

            publish_message(msg='fan_only', mqtt_path='comfoair/ha_climate_mode')
            if FanLevel == 1:
              publish_message(msg='low', mqtt_path='comfoair/ha_climate_mode/fan')
            elif FanLevel == 2:
                publish_message(msg='medium', mqtt_path='comfoair/ha_climate_mode/fan')
            elif FanLevel == 3:
                publish_message(msg='high', mqtt_path='comfoair/ha_climate_mode/fan')
            else:
                warning_msg('Wrong FanLevel value: {0}'.format(FanLevel))

            debug_msg('IntakeFanSpeed {0}%, ExhaustFanSpeed {1}%, IntakeAirRPM {2}, ExhaustAirRPM {3}, FanLevel: {4}'.format(IntakeFanSpeed, ExhaustFanSpeed, IntakeFanRPM, ExhaustFanRPM, FanLevel))
        else:
            warning_msg('function get_fan_status data array too short')

def get_parameters1_rs485():
    data = send_command(b'\x00\x89', None)

    if data is None:
        warning_msg('get_parameters1 function could not get serial data')
    else:
        if len(data) > 8:
            #data[0] is most likely absence / presence of EWT, Heater, Bypass & Filterguard. 8 seems to be bypass present, rest absent.
            SwitchOnDelay = data[1]
            SwitchOffDelay = data[2]
            #data[3] is zero, no clue what it is
            #data[4] is zero, no clue what it is
            OutLow = data[5]
            OutMid = data[6]
            OutHigh = data[7]
            InLow = data[8]
            InMid = data[9]
            debug_msg('SwitchOnDelay: {}, SwitchOffDelay: {}, OutLow: {}%, OutMid: {}%, OutHigh: {}%, InLow: {}%, InMid: {}%'.format(SwitchOnDelay, SwitchOffDelay, OutLow, OutMid, OutHigh, InLow, InMid))
        else:
            warning_msg('get_parameters1 function data array too short')

def get_parameters2_rs485():
    data = send_command(b'\x00\x8B', None)

    if data is None:
        warning_msg('get_parameters2 function could not get serial data')
    else:
        if len(data) > 8:
            InHigh = data[0]
            ComfortTemp = data[1] / 2.0 - 20
            HeaterTemp = data[2] / 2.0 - 20
            EWTTempLow = data[3] / 2.0 - 20
            EWTTempHigh = data[4] / 2.0 - 20
            BypassHysteresisTemp = data[5] / 2.0 - 20
            BypassOutCorr = data[6]
            AntiFrostTemp = data[7] / 2.0 - 20
            EWTInCorr = data[8]
            FilterTimer = data[9]
            debug_msg('InHigh: {}%, ComfortTemp: {}, HeaterTemp: {}, EWTTempLow: {}, EWTTempHigh: {}, BypassHysteresisTemp: {}, BypassOutCorr: {}%, AntiFrostTemp: {}, EWTInCorr {}%, FilterTimer {}wks'.format(InHigh, ComfortTemp, HeaterTemp, EWTTempLow, EWTTempHigh, BypassHysteresisTemp, BypassOutCorr, AntiFrostTemp, EWTInCorr, FilterTimer))
            if 10 < ComfortTemp < 30:
                publish_message(msg=str(ComfortTemp), mqtt_path='comfoair/comforttemp')
        else:
            warning_msg('get_parameters2 function data array too short')

def recon():
    try:
        mqttc.reconnect()
        info_msg('Successfull reconnected to the MQTT server')
        topic_subscribe()
    except:
        warning_msg('Could not reconnect to the MQTT server. Trying again in 10 seconds')
        time.sleep(10)
        recon()

def topic_subscribe():
    try:
        mqttc.subscribe("comfoair/comforttemp/set", 0)
        info_msg('Successfull subscribed to the comfoair/comforttemp/set topic')
        mqttc.subscribe("comfoair/ha_climate_mode/set", 0)
        info_msg('Successfull subscribed to the comfoair/ha_climate_mode/set topic')
        mqttc.subscribe("comfoair/ha_climate_mode/fan/set", 0)
        info_msg('Successfull subscribed to the comfoair/ha_climate_mode/fan/set topic')
        mqttc.subscribe("comfoair/reset_filter", 0)
        info_msg('Successfull subscribed to the comfoair/reset_filter topic')
        mqttc.subscribe("comfoair/filterweeks", 0)
        info_msg('Successfull subscribed to the comfoair/filterweeks topic')

        mqttc.subscribe("comfoair/ewtlowtemp", 0)
        info_msg('Successfull subscribed to the comfoair/ewtlowtemp topic')
        mqttc.subscribe("comfoair/ewthightemp", 0)
        info_msg('Successfull subscribed to the comfoair/ewthightemp topic')
        mqttc.subscribe("comfoair/ewtspeedup", 0)
        info_msg('Successfull subscribed to the comfoair/ewtspeedup topic')
        mqttc.subscribe("comfoair/fancontrol/set", 0)
        info_msg('Successfull subscribed to the comfoair/fancontrol/set topic')
        
    except:
        warning_msg('There was an error while subscribing to the MQTT topic(s), trying again in 10 seconds')
        time.sleep(10)
        topic_subscribe()

def send_autodiscover(name, entity_id, entity_type, state_topic = None, device_class = None, unit_of_measurement = None, state_class = None, icon = None, attributes = {}, command_topic = None, min_value = None, max_value = None):
    mqtt_config_topic = "homeassistant/" + entity_type + "/" + entity_id + "/config"
    sensor_unique_id = HAAutoDiscoveryDeviceId + "-" + entity_id

    discovery_message = {
        "name": name,
        "has_entity_name": True,
        "availability_topic":"comfoair/status",
        "payload_available":"online",
        "payload_not_available":"offline",
        "unique_id": sensor_unique_id,
        "device": {
            "identifiers":[
                HAAutoDiscoveryDeviceId
            ],
            "name": HAAutoDiscoveryDeviceName,
            "manufacturer": HAAutoDiscoveryDeviceManufacturer,
            "model": HAAutoDiscoveryDeviceModel
        }
    }
    if state_topic:
        discovery_message["state_topic"] = state_topic
        
    if command_topic:
        discovery_message["command_topic"] = command_topic
        
    if unit_of_measurement:
        discovery_message["unit_of_measurement"] = unit_of_measurement

    if state_class:
        discovery_message["state_class"] = state_class

    if device_class:
        discovery_message["device_class"] = device_class

    if icon:
        discovery_message["icon"] = icon
    if min_value:
        discovery_message["min"] = min_value
    if max_value:
        discovery_message["max"] = max_value
        
    if len(attributes) > 0:
        for attribute_key, attribute_value in attributes.items():
            discovery_message[attribute_key] = attribute_value

    mqtt_message = json.dumps(discovery_message)
    
    debug_msg('Sending autodiscover for ' + mqtt_config_topic)
    publish_message(mqtt_message, mqtt_config_topic)

def on_connect(client, userdata, flags, rc):
    publish_message("online","comfoair/status")
	# Temporary: deletion of old topic for Fan entity auto discovery
    delete_message("homeassistant/fan/ca350_fan/config")
	
    if HAEnableAutoDiscoverySensors is True:
        info_msg('Home Assistant MQTT Autodiscovery Topic Set: homeassistant/sensor/ca350_[nametemp]/config')

        # Temperature readings
        send_autodiscover(
            name="Outside temperature", entity_id="ca350_outsidetemp", entity_type="sensor",
            state_topic="comfoair/outsidetemp", device_class="temperature", unit_of_measurement="°C",
            state_class="measurement"
        )
        send_autodiscover(
            name="Supply temperature", entity_id="ca350_supplytemp", entity_type="sensor",
            state_topic="comfoair/supplytemp", device_class="temperature", unit_of_measurement="°C",
            state_class="measurement"
        )
        send_autodiscover(
            name="Exhaust temperature", entity_id="ca350_exhausttemp", entity_type="sensor",
            state_topic="comfoair/exhausttemp", device_class="temperature", unit_of_measurement="°C",
            state_class="measurement"
        )
        send_autodiscover(
            name="Return temperature", entity_id="ca350_returntemp", entity_type="sensor",
            state_topic="comfoair/returntemp", device_class="temperature", unit_of_measurement="°C",
            state_class="measurement"
        )

        # Analog sensors
        send_autodiscover(
            name="Analog sensor 1", entity_id="ca350_analog_sensor_1", entity_type="sensor",
            state_topic="comfoair/analog_sensor_1", unit_of_measurement="%", icon="mdi:gauge",
            state_class="measurement"
        )
        send_autodiscover(
            name="Analog sensor 2", entity_id="ca350_analog_sensor_2", entity_type="sensor",
            state_topic="comfoair/analog_sensor_2", unit_of_measurement="%", icon="mdi:gauge",
            state_class="measurement"
        )
        send_autodiscover(
            name="Analog sensor 3", entity_id="ca350_analog_sensor_3", entity_type="sensor",
            state_topic="comfoair/analog_sensor_3", unit_of_measurement="%", icon="mdi:gauge",
            state_class="measurement"
        )
        send_autodiscover(
            name="Analog sensor 4", entity_id="ca350_analog_sensor_4", entity_type="sensor",
            state_topic="comfoair/analog_sensor_4", unit_of_measurement="%", icon="mdi:gauge",
            state_class="measurement"
        )

        # Fan speeds
        send_autodiscover(
            name="Supply fan speed", entity_id="ca350_fan_speed_supply", entity_type="sensor",
            state_topic="comfoair/intakefanrpm", unit_of_measurement="rpm", icon="mdi:fan",
            state_class="measurement"
        )
        send_autodiscover(
            name="Exhaust fan speed", entity_id="ca350_fan_speed_exhaust", entity_type="sensor",
            state_topic="comfoair/exhaustfanrpm", unit_of_measurement="rpm", icon="mdi:fan",
            state_class="measurement"
        )

        send_autodiscover(
            name="Supply air level", entity_id="ca350_supply_air_level", entity_type="sensor",
            state_topic="comfoair/intakefanspeed", unit_of_measurement="%", icon="mdi:fan",
            state_class="measurement"
        )
        send_autodiscover(
            name="Return air level", entity_id="ca350_return_air_level", entity_type="sensor",
            state_topic="comfoair/exhaustfanspeed", unit_of_measurement="%", icon="mdi:fan",
            state_class="measurement"
        )

        # Filter
        send_autodiscover(
            name="Filter status", entity_id="ca350_filterstatus", entity_type="binary_sensor",
            state_topic="comfoair/filterstatus_binary", device_class="problem", icon="mdi:air-filter"
        )
        send_autodiscover(
            name="Filter Weeks", entity_id="ca350_filter_weeks", entity_type="number",
            command_topic="comfoair/filterweeks", unit_of_measurement="weeks", icon="mdi:air-filter",
            min_value=1, max_value=26, state_topic="comfoair/filterweeks_state"
        )
        send_autodiscover(
            name="Filter Hours", entity_id="ca350_filter_hours", entity_type="sensor",
            state_topic="comfoair/filterhours", unit_of_measurement="h", icon="mdi:timer"
        )
        send_autodiscover(
            name="Reset Filter", entity_id="ca350_reset_filter", entity_type="button",
            command_topic="comfoair/reset_filter", icon="mdi:air-filter"
        )
       
        # Bypass valve
        send_autodiscover(
            name="Bypass valve", entity_id="ca350_bypass_valve", entity_type="binary_sensor",
            state_topic="comfoair/ca350_bypass_valve", device_class="opening"
        )
        send_autodiscover(
            name="Bypass valve", entity_id="ca350_bypass_valve", entity_type="sensor",
            state_topic="comfoair/bypassstatus", unit_of_measurement="%", icon="mdi:valve"
        )
        
        # Summer mode
        send_autodiscover(
            name="Summer mode", entity_id="ca350_summer_mode", entity_type="binary_sensor",
            state_topic="comfoair/ca350_summer_mode", icon="mdi:sun-snowflake"
        )
        send_autodiscover(
            name="Summer mode", entity_id="ca350_summer_mode", entity_type="sensor",
            state_topic="comfoair/bypassmode", icon="mdi:sun-snowflake"
        )
        
        send_autodiscover(
            name="Preheating status", entity_id="ca350_preheatingstatus", entity_type="binary_sensor",
            state_topic="comfoair/preheatingstatus", device_class="heat"
        )

        # EWT sensor and controls
        send_autodiscover(
            name="EWT temperature", entity_id="ca350_ewttemp", entity_type="sensor",
            state_topic="comfoair/ewttemp", device_class="temperature", unit_of_measurement="°C",
            state_class="measurement"
        )
        send_autodiscover(
            name="EWT Low Temperature", entity_id="ca350_ewtlowtemp", entity_type="number",
            command_topic="comfoair/ewtlowtemp", unit_of_measurement="°C", icon="mdi:thermometer-low",
            device_class="temperature", min_value=0, max_value=15, state_topic="comfoair/ewtlowtemp_state"
        )
        send_autodiscover(
            name="EWT High Temperature", entity_id="ca350_ewthighertemp", entity_type="number",
            command_topic="comfoair/ewthightemp", unit_of_measurement="°C", icon="mdi:thermometer-high",
            device_class="temperature", min_value=10, max_value=25, state_topic="comfoair/ewthightemp_state"
        )
        send_autodiscover(
            name="EWT Speed Up", entity_id="ca350_ewtspeedup", entity_type="number",
            command_topic="comfoair/ewtspeedup", unit_of_measurement="%", icon="mdi:fan",
            device_class="temperature", min_value=0, max_value=99, state_topic="comfoair/ewtspeedup_state"
        )

        # Fan Control
        send_autodiscover(
            name="Fan Control", entity_id="ca350_fancontrol", entity_type="select",
            state_topic="comfoair/fancontrol", command_topic="comfoair/fancontrol/set", icon="mdi:fan-off",
            attributes={
                "options":["off", "In", "Out", "Both"],
                "entity_category":"config"
            }
        )

    else:
        delete_message("homeassistant/sensor/ca350_outsidetemp/config")
        delete_message("homeassistant/sensor/ca350_supplytemp/config")
        delete_message("homeassistant/sensor/ca350_exhausttemp/config")
        delete_message("homeassistant/sensor/ca350_returntemp/config")
        delete_message("homeassistant/sensor/ca350_fan_speed_supply/config")
        delete_message("homeassistant/sensor/ca350_fan_speed_exhaust/config")
        delete_message("homeassistant/sensor/ca350_return_air_level/config")
        delete_message("homeassistant/sensor/ca350_supply_air_level/config")
        delete_message("homeassistant/sensor/ca350_supply_fan/config")
        delete_message("homeassistant/binary_sensor/ca350_filterstatus/config")
        delete_message("homeassistant/binary_sensor/ca350_bypass_valve/config")
        delete_message("homeassistant/binary_sensor/ca350_summer_mode/config")
        delete_message("homeassistant/sensor/ca350_bypass_valve/config")
        delete_message("homeassistant/sensor/ca350_summer_mode/config")
        delete_message("homeassistant/binary_sensor/ca350_preheatingstatus/config")
        delete_message("homeassistant/sensor/analog_sensor_1/config")
        delete_message("homeassistant/sensor/analog_sensor_2/config")
        delete_message("homeassistant/sensor/analog_sensor_3/config")
        delete_message("homeassistant/sensor/analog_sensor_4/config")
        delete_message("homeassistant/button/ca350_reset_filter/config")
        delete_message("homeassistant/sensor/ca350_filter_hours/config")
        delete_message("homeassistant/number/ca350_filter_weeks/config")
    #ToDo: Work in progress
    if HAEnableAutoDiscoveryClimate is True:
        info_msg('Home Assistant MQTT Autodiscovery Topic Set: homeassistant/climate/ca350_climate/config')
        send_autodiscover(
            name="Climate", entity_id="ca350_climate", entity_type="climate",
            attributes={
                "temperature_command_topic":"comfoair/comforttemp/set",
                "temperature_state_topic":"comfoair/comforttemp",
                "current_temperature_topic":"comfoair/supplytemp",
                "min_temp":"15",
                "max_temp":"27",
                "temp_step":"1",
                "modes":["off", "fan_only"],
                "mode_state_topic":"comfoair/ha_climate_mode",
                "mode_command_topic":"comfoair/ha_climate_mode/set",
                "fan_modes":["off", "low", "medium", "high"],
                "fan_mode_state_topic":"comfoair/ha_climate_mode/fan",
                "fan_mode_command_topic":"comfoair/ha_climate_mode/fan/set",
                "temperature_unit":"C"
            }
        )
    else:
        delete_message("homeassistant/climate/ca350_climate/config")
    topic_subscribe()

def on_disconnect(client, userdata, rc):
    if rc != 0:
        warning_msg('Unexpected disconnection from MQTT, trying to reconnect')
        recon()

###
# Main
###

# Connect to the MQTT broker
mqttc = mqtt.Client('CA350')
if  MQTTUser != False and MQTTPassword != False :
    mqttc.username_pw_set(MQTTUser,MQTTPassword)

# Define the mqtt callbacks
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.on_disconnect = on_disconnect
mqttc.will_set("comfoair/status",payload="offline", qos=0, retain=True)


# Connect to the MQTT server
while True:
    try:
        mqttc.connect(MQTTServer, MQTTPort, MQTTKeepalive)
        break
    except:
        warning_msg('Can\'t connect to MQTT broker. Retrying in 10 seconds.')
        time.sleep(10)
        pass

# Open the serial port
try:
    ser = serial.Serial(port = SerialPort, baudrate = 9600, bytesize = serial.EIGHTBITS, parity = serial.PARITY_NONE, stopbits = serial.STOPBITS_ONE)
except:
    warning_msg('Opening serial port exception:')
    warning_msg(sys.exc_info())
else:
    if RS485_protocol == False: 
        if enablePcMode:
            set_pc_mode(3)
        else:
            set_pc_mode(0)  # If PC mode is disabled, deactivate it (in case it was activated in an earlier run)
    if SetUpFanLevelsAtStart:
        set_fan_levels(Intake=True, Exhaust=True)
    mqttc.loop_start()
    while True:
        try:
            if RS485_protocol == False:
                get_temp()
                get_fan_status()
                get_ventilation_status()
                get_filter_status()
                get_filter_weeks()
                get_filter_hours()
                get_bypass_status()
                get_preheating_status()
                get_analog_sensor()
                get_ewt()
            else:
                get_temp_rs485()
                get_fan_status_rs485()
                get_parameters1_rs485()
                get_parameters2_rs485()
            time.sleep(refresh_interval)
            pass
        except KeyboardInterrupt:
            mqttc.loop_stop()
            ser.close()
            break


# End of program
