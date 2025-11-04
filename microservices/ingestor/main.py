import datetime
import json
import os
import datetime
from microservices.ingestor.rss_ingestor import RssIngestor
from common.process.monitor import format_sys_stats, get_sys_stats
from common.io.redirect_and_modify import redirect_and_modify
from common.io.utils import indent_with_tab


@redirect_and_modify(string_modification_function=indent_with_tab)
def exec():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_file_path = os.path.join(script_dir, "rss_feeds.json")

    with open(json_file_path, "r") as file:
        rss_feeds = json.load(file)

    rss_ingestor = RssIngestor(rss_feeds)
    rss_ingestor.run()


if __name__ == "__main__":
        print(f"\n\nmain.py is being run. It is currently {datetime.datetime.now()}")
        print(format_sys_stats(get_sys_stats()))
        exec()
        print(f"\n\nmain.py is finished. It is currently {datetime.datetime.now()}")
