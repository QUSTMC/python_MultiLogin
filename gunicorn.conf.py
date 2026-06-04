import multiprocessing
import os

bind = os.environ.get("MULTILOGIN_BIND", "0.0.0.0:8080")
workers = 1
worker_class = "gthread"
threads = 4
timeout = 120
keepalive = 5
errorlog = "-"
accesslog = "-"
loglevel = "info"
