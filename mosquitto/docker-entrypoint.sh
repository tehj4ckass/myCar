#!/bin/sh
mosquitto_passwd -c -b /tmp/passwd "$MQTT_USER" "$MQTT_PASSWORD"
chmod 644 /tmp/passwd
exec mosquitto -c /mosquitto/config/mosquitto.conf
