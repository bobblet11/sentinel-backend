import datetime
import json
import os
from microservices.ingestor.rss_ingestor import RssIngestor
from common.process.monitor import format_sys_stats, get_sys_stats
from common.io.redirect_and_modify import redirect_and_modify
from common.io.utils import indent_with_tab


# @redirect_and_modify(string_modification_function=indent_with_tab)
def exec():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_file_path = os.path.join(script_dir, "rss_feeds.json")

    with open(json_file_path, "r") as file:
        structured_rss_feeds = json.load(file)

    available_structured_rss_feeds = [outlet for outlet in structured_rss_feeds if len(outlet["feeds"]) > 0]
    free_outlets = [outlet for outlet in available_structured_rss_feeds if outlet["paywall"] == "None"]
    num_free_feeds = sum(len(outlet['feeds']) for outlet in free_outlets)
    metered_outlets = [outlet for outlet in available_structured_rss_feeds if outlet["paywall"] == "Metered"]
    num_metered_feeds = sum(len(outlet['feeds']) for outlet in metered_outlets)
    
    rss_feeds = sum([x["feeds"] for x in available_structured_rss_feeds], [])
    num_feeds = len(rss_feeds)
    
    print(f"Feeds")
    print("-" * 20)
    print(f"Number of Free Outlets: {len(free_outlets)} ({num_free_feeds} feeds) [{100 * (num_free_feeds / num_feeds)}]")
    print(f"Number of Metered Outlets: {len(metered_outlets)} ({num_metered_feeds} feeds) [{100 * (num_metered_feeds / num_feeds)}]")
    print(f"Total number of feeds: {num_feeds}")
    print("-" * 20)
    
    rss_ingestor = RssIngestor(rss_feeds)
    rss_ingestor.run()


if __name__ == "__main__":
        print(f"\n\nmain.py is being run. It is currently {datetime.datetime.now()}")
        # print(format_sys_stats(get_sys_stats()))
        exec()
        print(f"\n\nmain.py is finished. It is currently {datetime.datetime.now()}")
