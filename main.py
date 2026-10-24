import os
import socket
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(128)

    config = uvicorn.Config("app.main:app", host=None, port=None, log_level="info")
    server = uvicorn.Server(config)
    server.run(sockets=[sock])