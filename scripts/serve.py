#!/usr/bin/env python3
"""Start a local HTTP server for a directory and open it in the browser."""

import argparse
import os
import socket
import subprocess
import time


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a directory and open it in the browser.")
    parser.add_argument("directory", help="Directory to serve")
    args = parser.parse_args()

    port = free_port()
    subprocess.Popen(["python3", "-m", "http.server", str(port), "--directory", args.directory])
    time.sleep(0.5)
    os.system(f"open http://localhost:{port}")


if __name__ == "__main__":
    main()
