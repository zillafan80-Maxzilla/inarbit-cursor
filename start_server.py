import logging, traceback, sys, os, json, time, socket

logging.basicConfig(level=logging.DEBUG)

try:
    try:
        os.makedirs("c:\\Users\\周浩\\.cursor\\cursor-workspace\\inarbit\\.cursor", exist_ok=True)
    except Exception:
        pass
    import uvicorn
    host = os.getenv("API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        requested_port = int(os.getenv("API_PORT", "").strip() or os.getenv("INARBIT_API_PORT", "").strip() or "8000")
    except Exception:
        requested_port = 8000

    def _port_in_use(bind_host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((bind_host, port)) == 0

    port = requested_port
    if _port_in_use(host, port):
        try:
            scan = int(os.getenv("API_PORT_SCAN_RANGE", "10").strip() or "10")
        except Exception:
            scan = 10
        for offset in range(1, max(1, scan) + 1):
            candidate = requested_port + offset
            if not _port_in_use(host, candidate):
                port = candidate
                print(f"Port {requested_port} in use, fallback to {port}")
                break
        if port == requested_port:
            raise RuntimeError(f"Port {requested_port} already in use")
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cursor_dir = os.path.join(base_dir, ".cursor")
        os.makedirs(cursor_dir, exist_ok=True)
        port_path = os.path.join(cursor_dir, "api_port.json")
        with open(port_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "host": host,
                    "port": port,
                    "base": f"http://{host}:{port}",
                    "timestamp": int(time.time() * 1000),
                },
                f,
                ensure_ascii=False,
            )
    except Exception:
        pass
    print("Starting uvicorn...")
    uvicorn.run("server.app:app", host=host, port=port, log_level="debug")
except Exception as e:
    print("Exception during uvicorn.run:")
    traceback.print_exc()
    sys.exit(1)
