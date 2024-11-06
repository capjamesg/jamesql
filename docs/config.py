import os

BASE_URLS = {
    "local": os.getcwd(),
    "production": "https://jamesg.blog/jamesql/",
}

SITE_ENV = os.environ.get("SITE_ENV", "local")
BASE_URL = BASE_URLS[SITE_ENV]
ROOT_DIR = "pages"
LAYOUTS_BASE_DIR = "_layouts"
SITE_DIR = "_site"
HOOKS = {
    "post_template_generation": {"hooks": ["highlight_code"]},
    "pre_template_generation": {"hooks": ["generate_table_of_contents"]}
}
SITE_STATE = {}

BASE_URL = BASE_URLS[SITE_ENV]