import logging, traceback, sys

logging.basicConfig(level=logging.DEBUG)

try:
    import uvicorn
    print("Starting uvicorn...")
    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, log_level="debug")
except Exception as e:
    print("Exception during uvicorn.run:")
    traceback.print_exc()
    sys.exit(1)
