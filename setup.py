from pathlib import Path

from setuptools import setup, find_packages

# The TeraSim wheels ship in dist/ rather than on PyPI. install_requires only
# accepts absolute URLs for direct references, so build them from this file's
# location.
DIST_DIR = Path(__file__).resolve().parent / "dist"


def local_wheel(name, filename):
    return f"{name} @ {(DIST_DIR / filename).as_uri()}"


setup(
    name="terasim_cosim_udp",
    version="0.1.0",
    description="UDP bridge (client + relay server) for mirroring TeraSim-Cosim Redis pub/sub channels between remote sites over the internet",
    license="MIT",
    packages=find_packages(
        where=".",
        include=[
            "terasim_cosim_udp",
            "terasim_cosim_udp.*",
        ],
    ),
    install_requires=[
        "redis==5.0.2",
        "loguru==0.7.2",
        "carla==0.9.16",
        "pygame",
        local_wheel("terasim", "terasim-2024.9.25.1332-py3-none-any.whl"),
        local_wheel("terasim_cosim", "terasim_cosim-2025.6.11-py3-none-any.whl"),
        local_wheel("terasim_nde_nade", "terasim_nde_nade-2025.4.27.1659-py3-none-any.whl"),
    ],
)
