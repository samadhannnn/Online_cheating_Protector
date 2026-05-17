import multiprocessing

bind = "0.0.0.0:5000"
workers = 1 # Eventlet with SocketIO should typically use 1 worker for broadcasting correctly without Redis
worker_class = "eventlet"
timeout = 120
keepalive = 5
