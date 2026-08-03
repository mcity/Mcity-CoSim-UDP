from setuptools import setup, find_packages

setup(
    name="terasim_cosim_udp",
    version="0.1.0",
    description="UDP bridge (client + relay server) for mirroring TeraSim-Cosim Redis pub/sub channels between remote sites over the internet",
    license="MIT",
    packages=find_packages(
        where=".",
        include=[
            "terasim_cosim",
            "terasim_cosim.udp_client_wrapper",
        ],
    ),
    install_requires=[
        "redis==5.0.2",
        "loguru==0.7.2",
    ],
)
