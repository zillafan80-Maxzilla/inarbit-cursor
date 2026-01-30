import traceback, sys
try:
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=8000, log_level="debug")
except Exception as e:
    traceback.print_exc()
    sys.exit(1)
