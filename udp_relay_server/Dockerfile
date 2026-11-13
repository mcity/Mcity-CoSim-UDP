# Build from the repository root (one level up from this file) so the
# shared wire protocol module can be included, e.g.:
#   docker build -f udp_relay_server/Dockerfile -t terasim-udp-relay .
FROM python:3.11-slim

WORKDIR /app

# Only the dependency-free protocol module is needed, not the full
# terasim_cosim_udp package (which pulls in redis/loguru for the client side).
COPY terasim_cosim_udp/__init__.py ./terasim_cosim_udp/__init__.py
COPY terasim_cosim_udp/udp_protocol.py ./terasim_cosim_udp/udp_protocol.py
COPY udp_relay_server/server.py ./udp_relay_server/server.py

ENV PYTHONPATH=/app
ENV TERASIM_UDP_SERVER_HOST=0.0.0.0
ENV TERASIM_UDP_SERVER_PORT=8443
# TERASIM_UDP_PASSWORD has no default and must be supplied at runtime
# (docker run -e TERASIM_UDP_PASSWORD=... or an --env-file).

EXPOSE 8443/udp

CMD ["python", "udp_relay_server/server.py"]
