from URDF_Exporter.standalone.server import run


if __name__ == "__main__":
    if run() is False:
        raise SystemExit(3)
