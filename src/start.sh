#!/bin/bash

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