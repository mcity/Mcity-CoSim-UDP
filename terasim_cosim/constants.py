# UDP relay related constants
ENVIRONMENT_VARIABLE_UDP_HOST = "TERASIM_UDP_HOST"
ENVIRONMENT_VARIABLE_UDP_PORT = "TERASIM_UDP_PORT"
ENVIRONMENT_VARIABLE_UDP_PASSWORD = "TERASIM_UDP_PASSWORD"
ENVIRONMENT_VARIABLE_UDP_SERVER_HOST = "TERASIM_UDP_SERVER_HOST"
ENVIRONMENT_VARIABLE_UDP_SERVER_PORT = "TERASIM_UDP_SERVER_PORT"

# Redis channels or keys (must match the keys used by the main TeraSim-Cosim
# Redis client so this bridge reads/writes the same data the simulator uses)
CAV_INFO = "cav_info"
TLS_INFO = "tls_info"

TERASIM_ACTOR_INFO = "terasim_actor_info"
CONSTRUCTION_ZONE_INFO = "construction_zone_info"

LATENCY = "terasim/latency"
FLAG = "terasim/flag"

VEHICLE_CONTROL = "terasim/vehicle_control"
VEHICLE_STATE = "terasim/vehicle_state"
VEHICLE_PLANNING = "terasim/vehicle_planning"
