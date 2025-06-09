import os

import pytz

tz = pytz.timezone(os.getenv("TIMEZONE", "UTC"))
utc = pytz.timezone("UTC")
