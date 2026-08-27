from redis import Redis
from rq import Worker

from app.core.config import get_settings
from app.core.logging import configure_logging

if __name__ == "__main__":
    configure_logging()
    Worker(["flyers"], connection=Redis.from_url(get_settings().redis_url)).work()
