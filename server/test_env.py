import sys
print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")

try:
    import networkx
    print(f"NetworkX Version: {networkx.__version__}")
except ImportError:
    print("NetworkX not installed")

try:
    import ccxt
    print(f"CCXT Version: {ccxt.__version__}")
except ImportError:
    print("CCXT not installed")
