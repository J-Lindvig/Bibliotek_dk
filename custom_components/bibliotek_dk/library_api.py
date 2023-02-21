from __future__ import annotations

from bs4 import BeautifulSoup as BS
from datetime import datetime
import json
import logging
import requests


from .const import (
    HEADERS,
    URL_LOGIN_PAGE,
)

DEBUG = True

"""
# Constants used in multiple functions, primarily as string keys in dict.
"""
# CHECKLIST = "CHECKLIST"	# JS
DEBTS = "DEBTS"
LOANS = "LOANS"
LOANS_OVERDUE = "LOANS_OVERDUE"
LOGGED_IN = "logget ind"
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
    # 	CHECKLIST: "min liste", # JS
    DEBTS: "betal",
    LOANS: "lån",
    LOANS_OVERDUE: "over",
    LOGOUT: "log",
    MY_PAGES: "/user/me/view",
    RESERVATIONS: "reserveringer i",
    RESERVATIONS_READY: "reserveringer klar",
    # 	SEARCHES: "mine gemte", # JS
    USER_PROFILE: "bruger",
}

_LOGGER: logging.Logger = logging.getLogger(__package__)
_LOGGER = logging.getLogger(__name__)

"""
Library holds the engine of the scraping.
"""


class Library:
    session = requests.Session()
    session.headers = HEADERS

    host, libraryName, user = None, None, None
    loggedIn, updatedUrls, running = False, False, False

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
            # Only fetch the URLs once
            if not self.updatedUrls:
                self.fetchUserLinks()

            # Only fetch user info once
            if not self.user.name:
                self.fetchUserInfo()

            # Fetch the states of the user
            self.fetchLoans()
            self.fetchReservations()
            self.fetchReservationsReady()

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

    def _getMaterials(self, soup, noodle="div[class*='material-item']"):
        return soup.select(noodle)

    def _getIdInfo(self, material):
        return material.input["value"], not "disabled" in material.input.attrs

    def _getMaterialUrls(self, material):
        return (
            self.host + material.a["href"] if material.a else "",
            material.img["src"] if material.img else "",
        )

    def _getMaterialInfo(self, material):
        # Some title have the type in "()", remove it
        # by splitting the string by the first "(" and use
        # only the first element, stripping whitespaces
        materialTitle = material.h3.string.split("(")[0].strip()

        materialType = material.select_one("div[class=item-material-type]")
        materialType = materialType.string if materialType else ""

        materialCreators = material.select_one("div[class=item-creators]")
        materialCreators = materialCreators.string if materialCreators else ""

        return materialTitle, materialCreators, materialType

    def _getDetails(self, material):
        details = {}
        for li in material.find_all("li"):
            # Use last element in class ad key
            details[li["class"][-1]] = li.select_one(
                "div[class=item-information-data]"
            ).string
        return details

    ####  PRIVATE END  ####

    def login(self):
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

    # Fetch the links to the different pages from the "My Pages page
    def fetchUserLinks(self):
        # Fetch "My view"
        soup = self._fetchPage(self.host + URLS[MY_PAGES])

        # Find all <a> within a <ul> with a specific class
        urls = soup.select_one("ul[class=main-menu-third-level]").find_all("a")
        _LOGGER.debug(f"HTML:\n{urls}")
        for url in urls:
            # Only work on URLs not allready in our dict
            if not url["href"] in URLS.values():
                # Search for key and value
                # if the text of the URL starts with our value
                # update the list at the key
                for key, value in URLS.items():
                    if not self.updatedUrls:
                        self.updatedUrls = True
                    if url.text.lower().startswith(value):
                        URLS[key] = (
                            url["href"]
                            if url["href"].startswith("/")
                            else url["href"] + "/"
                        )

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
    def fetchLoans(self):
        # Reset the loans
        self.user.loans = []

        # Fetch the loans page
        soup = self._fetchPage(self.host + URLS[LOANS])

        # From the <div> containing part of the class
        # for material in soup.select("div[class*='material-item']"):
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
            for key, value in self._getDetails(material).items():
                if key == "loan-date":
                    obj.loanDate = self._getDatetime(value)
                elif key == "expire-date":
                    obj.expireDate = self._getDatetime(value)
                elif key == "material-number":
                    obj.id = value

            # Add the loan to the stack
            self.user.loans.append(obj)

        # Sort the loans by expireDate and the Title
        self.user.loans.sort(key=lambda obj: (obj.expireDate, obj.title))

        # If any loans, set the nextExpireDate to the first loan in the list
        if self.user.loans:
            self.user.nextExpireDate = self.user.loans[0].expireDate

    # Get the current reservations
    def fetchReservations(self):
        # Reset the reservations
        self.user.reservations = []

        # Fecth the reservations page
        soup = self._fetchPage(self.host + URLS[RESERVATIONS])

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
            for key, value in self._getDetails(material).items():
                if key == "expire-date":
                    obj.expireDate = self._getDatetime(value)
                elif key == "created-date":
                    obj.createdDate = self._getDatetime(value)
                elif key == "queue-number":
                    obj.queueNumber = value
                elif key == "pickup-branch":
                    obj.pickupLibrary = value

            # Add the reservation to the stack
            self.user.reservations.append(obj)

            # Sort the reservations
            self.user.reservations.sort(
                key=lambda obj: (
                    obj.queueNumber,
                    obj.createdDate,
                    obj.title,
                )
            )

    # Get the reservations which are ready
    def fetchReservationsReady(self):
        # Reset the reservationsReady
        self.user.reservationsReady = []

        # Fecth the ready reservationsReady page
        soup = self._fetchPage(self.host + URLS[RESERVATIONS_READY])

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
            for key, value in self._getDetails(material).items():
                if key == "pickup-id":
                    obj.reservationNumber = value
                elif key == "pickup-date":
                    obj.pickupDate = self._getDatetime(value)
                elif key == "created-date":
                    obj.createdDate = self._getDatetime(value)
                elif key == "pickup-branch":
                    obj.pickupLibrary = value

            # Add the reservation to the stack
            self.user.reservationsReady.append(obj)

            # Sort the reservations
            self.user.reservationsReady.sort(
                key=lambda obj: (obj.pickupDate, obj.title)
            )


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
