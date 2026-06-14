FROM tillsteinbach/carconnectivity-mqtt:latest
COPY carconnectivity.json /carconnectivity.json.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
