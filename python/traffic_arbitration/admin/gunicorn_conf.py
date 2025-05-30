import multiprocessing

bind = "0.0.0.0:8088"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 30
loglevel = "info"
accesslog = "-"
errorlog = "-"
