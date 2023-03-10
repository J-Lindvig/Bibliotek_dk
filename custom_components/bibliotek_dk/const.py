CONF_AGENCY = "agency"
CONF_BRANCH_ID = "branchId"
CONF_HOST = "host"
CONF_MUNICIPALITY = "municipality"
CONF_NAME = "name"
CONF_PINCODE = "pincode"
CONF_SHOW_DEBTS = "show_debts"
CONF_SHOW_E_LIBRARY = "show_e_library"
CONF_SHOW_LOANS = "show_loans"
CONF_SHOW_RESERVATIONS = "show_reservations"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_USER_ID = "user_id"
CREDITS = "J-Lindvig (https://github.com/J-Lindvig)"

DOMAIN = "bibliotek_dk"

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "da,en-US;q=0.9,en;q=0.8",
    "Dnt": "1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.dk/",
}

MUNICIPALITY_LOOKUP_URL = "https://api.dataforsyningen.dk/kommuner/reverse?x=LON&y=LAT"

UPDATE_INTERVAL = 60
URL_FALLBACK = "https://fmbib.dk"
URL_LOGIN = "/adgangsplatformen/login"
URL_LOGIN_PAGE = URL_LOGIN + "?destination=ding_frontpage"
URL_LOGIN_PAGE_ELIB = URL_LOGIN + "?destination=/user"
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:77.0) Gecko/20100101 Firefox/77.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
]
