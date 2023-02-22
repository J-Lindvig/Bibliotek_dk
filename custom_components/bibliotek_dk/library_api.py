from __future__ import annotations

from bs4 import BeautifulSoup as BS
from datetime import datetime
import json
import logging
import random
import requests


from .const import HEADERS, URL_LOGIN_PAGE, USER_AGENTS

DEBUG = True

"""
# Constants used in multiple functions, primarily as string keys in dict.
"""
# CHECKLIST = "CHECKLIST"	# JS
DEBTS = "DEBTS"
LOANS = "LOANS"
LOANS_OVERDUE = "LOANS_OVERDUE"
LOGGED_IN = "logget ind"
LOGGED_IN_ELIB = "Logged-in"
LOGOUT = "LOGOUT"
MY_PAGES = "MY_PAGES"
RESERVATIONS = "RESERVATIONS"
RESERVATIONS_READY = "RESERVATIONS_READY"
# SEARCHES = "SEARCHES"		# JS
USER_PROFILE = "USER_PROFILE"

"""
Dict of URLs from the user profile page.
Key is taken from the constants. Default value is the string to look for in the HTML
"""
URLS = {
    # 	CHECKLIST: "/user/me/checklist", # JS
    DEBTS: "/user/me/status-debts",
    LOANS: "/user/me/status-loans",
    LOANS_OVERDUE: "/user/me/status-loans-overdue",
    LOGOUT: "/user/logout",
    MY_PAGES: "/user/me/view",
    RESERVATIONS: "/user/me/status-reservations",
    RESERVATIONS_READY: "/user/me/status-reservations-ready",
    # 	SEARCHES: "/user/me/followed-searches", # JS
    USER_PROFILE: "/user/me/edit",
}

_LOGGER: logging.Logger = logging.getLogger(__package__)
_LOGGER = logging.getLogger(__name__)

"""
Library holds the engine of the scraping.
"""


class Library:
    host, libraryName, user = None, None, None
    loggedIn, running = False, False

    """
    Initialize of Library takes these arguments:

    userId: (CPR-number) or Loaner-ID
    pincode: Pincode
    host, URL to your local library

    A libraryUser object is created from the credentials.
    """

    def __init__(self, userId: str, pincode: str, host=str) -> None:
        self.host = host
        self.user = libraryUser(userId=userId, pincode=pincode)

        if DEBUG:
            _LOGGER.debug("*" * 40)
            _LOGGER.debug(
                f"__init__ called with the arguments: userId = '{userId}', pincode = '{pincode}', host = '{host}'"
            )

    # The update function is called from the coordinator from Home Assistant
    def update(self):
        _LOGGER.debug(f"Updating ({self.user.userId[:-4]})...")

        # Only one user can login at the time.
        self.running = True

        if self.login():
            self.fetchUserLinks()  # Soon obsolete....

            # Only fetch user info once
            if not self.user.name:
                self.fetchUserInfo()

            # Fetch the states of the user
            self.user.loans = self.fetchLoans()
            self.user.reservations = self.fetchReservations()
            self.user.reservationsReady = self.fetchReservationsReady()

            # If any loans, set the nextExpireDate to the first loan in the list
            if self.user.loans:
                self.user.nextExpireDate = self.user.loans[0].expireDate

            self.logout()

        self.running = False

        return True

    #### PRIVATE BEGIN ####

    # Retrieve a webpage with either GET/POST
    def _fetchPage(self, url=str, payload=None) -> BS:
        # If payload, use POST
        if payload:
            r = self.session.post(url, data=payload)

        # else use GET
        else:
            r = self.session.get(url)

        # Return HTML soup
        return BS(r.text, "html.parser")

    # Search for given string in the HTML soup
    def _titleInSoup(self, soup, string) -> bool:
        return string.lower() in soup.title.string.lower()

    # Convert ex. "22. maj 2023" to a datetime object
    def _getDatetime(self, date, format="%d. %b %Y") -> datetime:
        # Split the string by " ", store in separate elements
        d, m, y = date.split(" ")
        # Cut the name of the month to the first 3 chars
        m = m[:3]
        # Change the few danish month to english
        key = m.lower()
        if key == "maj":
            m = "may"
        elif key == "okt":
            m = "oct"

        # Return the datetime
        return datetime.strptime(f"{d} {m} {y}", format).date()

    def sortLists(self):
        # Sort the loans by expireDate and the Title
        self.user.loans.sort(key=lambda obj: (obj.expireDate, obj.title))
        # Sort the reservations
        self.user.reservations.sort(
            key=lambda obj: (
                obj.queueNumber,
                obj.createdDate,
                obj.title,
            )
        )
        # Sort the reservations
        self.user.reservationsReady.sort(key=lambda obj: (obj.pickupDate, obj.title))

    def _getMaterials(self, soup, noodle="div[class*='material-item']") -> BS:
        return soup.select(noodle)

    def _getIdInfo(self, material) -> tuple:
        return material.input["value"], not "disabled" in material.input.attrs

    def _getMaterialUrls(self, material) -> tuple:
        return (
            self.host + material.a["href"] if material.a else "",
            material.img["src"] if material.img else "",
        )

    def _getMaterialInfo(self, material) -> tuple:
        # Some title have the type in "()", remove it
        # by splitting the string by the first "(" and use
        # only the first element, stripping whitespaces
        materialTitle = material.h3.string.split("(")[0].strip()

        materialType = material.select_one("div[class=item-material-type]")
        materialType = materialType.string if materialType else ""

        materialCreators = material.select_one("div[class=item-creators]")
        materialCreators = materialCreators.string if materialCreators else ""

        return materialTitle, materialCreators, materialType

    # Loop <li>
    # (re)Join the class(es) with a " ", use as key
    def _getDetails(self, material):
        details = {}
        for li in material.find_all("li"):
            details[" ".join(li["class"])] = li.select_one(
                "div[class=item-information-data]"
            ).string

        return details.items()

    ####  PRIVATE END  ####
    def login(self):

        # Prepare a new session with a random user-agent
        self.session = requests.Session()
        HEADERS["User-Agent"] = random.choice(USER_AGENTS)
        self.session.headers = HEADERS

        # Test if we are logged in by fetching the main page
        # This is done manually, since we are using the response later
        r = self.session.get(self.host)
        if r.status_code == 200:
            # Page OK, prepare HTML soup
            soup = BS(r.text, "html.parser")

            self.loggedIn = self._titleInSoup(soup, LOGGED_IN)
            # Retrieve the name of the Library from the title tag
            # <title>Faaborg-Midtfyn Bibliotekerne | | Logget ind</title>
            self.libraryName = soup.title.string.split("|")[0].strip()

        if not self.loggedIn:
            # Fetch the loginpage and prepare a soup
            # Must make a manual GET, since we are the response later
            r = self.session.get(self.host + URL_LOGIN_PAGE)
            soup = BS(r.text, "html.parser")

            # Prepare the payload
            payload = {}
            # Find the <form>
            form = soup.find("form")
            if form:
                for input in form.find_all("input"):
                    if input:
                        # Fill the form with the userInfo
                        if input["name"] in self.user.userInfo:
                            payload[input["name"]] = self.user.userInfo[input["name"]]
                        # or pass default values to payload
                        else:
                            payload[input["name"]] = input["value"]

                # Send the payload as POST and prepare a new soup
                # Use the URL from the response since we have been directed
                soup = self._fetchPage(form["action"].replace("/login", r.url), payload)

            # Set loggedIn
            self.loggedIn = self._titleInSoup(soup, LOGGED_IN)
            self.libraryName = soup.title.string.split("|")[0].strip()  # REDUNDANT

        if DEBUG:
            _LOGGER.debug("*" * 40)
            _LOGGER.debug(f"Logged in ({self.loggedIn}) at {self.libraryName}")

        return self.loggedIn

    def logout(self):
        if self.loggedIn:
            # Fetch the logout page, if given a 200 (true) reverse it to false
            self.loggedIn = (
                not self.session.get(self.host + URLS[LOGOUT]).status_code == 200
            )
            if not self.loggedIn:
                self.session.close()

    # Fetch the links to the different pages from the "My Pages page
    def fetchUserLinks(self):
        # # Fetch "My view"
        soup = self._fetchPage(self.host + URLS[MY_PAGES])

        if DEBUG:
            urlList = {}
            _LOGGER.debug("*" * 40)
            for key, url in URLS.items():
                urlList[key] = self.host + url
            _LOGGER.debug("URLS:\n" + json.dumps(urlList, indent=4))

        # Fetch usefull user states - OBSOLETE WHEN FETCHING DETAILS
        for a_status in soup.select_one("ul[class='list-links specials']").find_all(
            "a"
        ):
            if URLS[DEBTS] in a_status["href"]:
                self.user.debts = a_status.parent.find_all("span")[-1].string

    # Get information on the user
    def fetchUserInfo(self):
        # Fetch the user profile page
        soup = self._fetchPage(self.host + URLS[USER_PROFILE])

        # From the <div> with a specific class, loop all the <div>
        # containging a part of the class
        for fields in soup.select_one("div[class=content]").select(
            "div[class*=field-name]"
        ):
            fieldName = fields.select_one("div[class=field-label]")
            # NASTY HTML PAGE....
            # From the tag of the fieldName, go to the parent
            # Find the first <div> with given class
            fieldValue = fieldName.parent.select_one("div[class=field-items]").div
            # Remove <br>, again NASTY HTML
            for e in fieldValue.findAll("br"):
                e.extract()

            # Find the correct place for the field
            key = fieldName.string.lower()
            if key == "navn":
                self.user.name = fieldValue.string
            elif key == "adresse":
                self.user.address = fieldValue.contents

        # Find the correct <form>, extract info
        form = soup.select_one(f"form[action='{URLS[USER_PROFILE]}']")
        self.user.phone = form.select_one("input[name*='phone]']")["value"]
        self.user.phoneNotify = (
            int(form.select_one("input[name*='phone_notification']")["value"]) == 1
        )
        self.user.mail = form.select_one("input[name*='mail]']")["value"]
        self.user.mailNotify = (
            int(form.select_one("input[name*='mail_notification']")["value"]) == 1
        )

        # Find our preferred library, when found break the loop
        for library in form.select_one("select[name*='preferred_branch']").find_all(
            "option"
        ):
            if "selected" in library.attrs:
                self.user.pickupLibrary = library.string
                break

    # Get the loans with all possible details
    def fetchLoans(self, soup=None):
        # Fetch the loans page
        if not soup:
            soup = self._fetchPage(self.host + URLS[LOANS])

        # From the <div> containing part of the class
        # for material in soup.select("div[class*='material-item']"):
        tempList = []
        for material in self._getMaterials(soup):
            # Create an instance of libraryLoan
            obj = libraryLoan()

            # Renewable
            obj.renewId, obj.renewAble = self._getIdInfo(material)

            # URL and image
            obj.url, obj.coverUrl = self._getMaterialUrls(material)

            # Type, title and creator
            obj.title, obj.creators, obj.type = self._getMaterialInfo(material)

            # Details
            for keys, value in self._getDetails(material):
                if "loan-date" in keys:
                    obj.loanDate = self._getDatetime(value)
                elif "expire-date" in keys:
                    obj.expireDate = self._getDatetime(value)
                elif "material-number" in keys:
                    obj.id = value

            # Add the loan to the stack
            tempList.append(obj)
        #            self.user.loans.append(obj)

        return tempList

    # Get the current reservations
    def fetchReservations(self):
        # Fecth the reservations page
        soup = self._fetchPage(self.host + URLS[RESERVATIONS])

        tempList = []
        # From the <div> with containg the class of the materials
        for material in self._getMaterials(soup):
            # Create a instance of libraryReservation
            obj = libraryReservation()

            # Get the first element (id)
            obj.id = self._getIdInfo(material)[0]

            # URL and image
            obj.url, obj.coverUrl = self._getMaterialUrls(material)

            # Type, title and creator
            obj.title, obj.creators, obj.type = self._getMaterialInfo(material)

            # Details
            for keys, value in self._getDetails(material):
                if "expire-date" in keys:
                    obj.expireDate = self._getDatetime(value)
                elif "created-date" in keys:
                    obj.createdDate = self._getDatetime(value)
                elif "queue-number" in keys:
                    obj.queueNumber = value
                elif "pickup-branch" in keys:
                    obj.pickupLibrary = value

            # Add the reservation to the stack
            tempList.append(obj)

        return tempList

    # Get the reservations which are ready
    def fetchReservationsReady(self):
        # Fecth the ready reservationsReady page
        soup = self._fetchPage(self.host + URLS[RESERVATIONS_READY])

        tempList = []
        # From the <div> with the materials
        for material in self._getMaterials(soup):
            # Create a instance of libraryReservationReady
            obj = libraryReservationReady()

            # Get the first element (id)
            obj.id = self._getIdInfo(material)[0]

            # URL and image
            obj.url, obj.coverUrl = self._getMaterialUrls(material)

            # Type, title and creator
            obj.title, obj.creators, obj.type = self._getMaterialInfo(material)

            # Details
            for keys, value in self._getDetails(material):
                if "pickup-id" in keys:
                    obj.reservationNumber = value
                elif "pickup-date" in keys:
                    obj.pickupDate = self._getDatetime(value)
                elif "created-date" in keys:
                    obj.createdDate = self._getDatetime(value)
                elif "pickup-branch" in keys:
                    obj.pickupLibrary = value

            # Add the reservation to the stack
            tempList.append(obj)

        return tempList


class libraryUser:
    userInfo = None
    name, address = None, None
    phone, phoneNotify, mail, mailNotify = None, None, None, None
    reservations, reservationsReady, loans, debts = [], [], [], None
    nextExpireDate = None
    pickupLibrary = None

    def __init__(self, userId: str, pincode: str):
        self.userInfo = {"userId": userId, "pincode": pincode}
        self.userId = userId


class libraryMaterial:
    id = None
    type, title, creators = None, None, None
    url, coverUrl = None, None


class libraryLoan(libraryMaterial):
    loanDate, expireDate = None, None
    renewId, renewAble = None, None


class libraryReservation(libraryMaterial):
    createdDate, expireDate, queueNumber = None, None, None
    pickupLibrary = None


class libraryReservationReady(libraryMaterial):
    createdDate, pickupDate, reservationNumber = None, None, None
    pickupLibrary = None


class libraryEbook(libraryMaterial):
    loanDate, expireDate = None, None
