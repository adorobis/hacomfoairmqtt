#!/bin/sh
#Simple file to check status of the ca350 service for reporting in Home Assistant

if service ca350 status>nul; then
        echo running
else
        echo stopped
fi
