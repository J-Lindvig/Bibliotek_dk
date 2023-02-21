from __future__ import annotations

from bs4 import BeautifulSoup as BS
from datetime import datetime
import json
import logging
import re
import requests


from .const import (
    HEADERS,
    URL_LOGIN_PAGE,
)

DEBUG = True

LOGGED_IN = "logget ind"
MY_PAGES = "MY_PAGES"
LOANS_OVERDUE = "LOANS_OVERDUE"
LOANS = "LOANS"
RESERVATIONS_READY = "RESERVATIONS_READY"
RESERVATIONS = "RESERVATIONS"
# CHECKLIST = "CHECKLIST"	# JS
# SEARCHES = "SEARCHES"		# JS
USER_PROFILE = "USER_PROFILE"
DEBTS = "DEBTS"
LOGOUT = "LOGOUT"
URLS = {
    MY_PAGES: "/user/me/view",
    LOANS_OVERDUE: "over",
    LOANS: "lån",
    RESERVATIONS_READY: "reserveringer klar",
    RESERVATIONS: "reserveringer i",
    # 	CHECKLIST: "min liste",				# JS
    # 	SEARCHES: "mine gemte",				# JS
    USER_PROFILE: "bruger",
    DEBTS: "betal",
    LOGOUT: "log",
}

_LOGGER: logging.Logger = logging.getLogger(__package__)
_LOGGER = logging.getLogger(__name__)


class Library:
    session = requests.Session()
    session.headers = HEADERS

    host = None  # The URL to the library
    loggedIn = False  # Boolean
    libraryName = None  # Name of the Library/Municipality
    user = None  # Object of libraryUser
    updatedUrls = False
    running = False

    # Required:
    # userId: (CPR-number) or Loaner-ID
    # pincode: Pincode
    # host, URL to your local library
    def __init__(self, userId: str, pincode: str, host=str) -> None:
        self.host = host
        self.user = libraryUser(userId=userId, pincode=pincode)

    def update(self):
        _LOGGER.debug(f"Updating ({self.user.userId[:-4]})...")
        self.running = True

        if self.login():
            if not self.updatedUrls:
                self.fetchUserLinks()

            if not self.user.name:
                self.fetchUserInfo()

            self.fetchLoans()
            self.fetchReservations()
            self.fetchReservationsReady()

            self.logout()

        self.running = False

        return True

    # Private
    # GET / POST a webpage, returned as soup
    def _fetchPage(self, url=str, payload=None):
        # If payload, use POST
        if payload:
            r = self.session.post(url, data=payload)

        # else use GET
        else:
            r = self.session.get(url)

        # Return HTML soup
        return BS(r.text, "html.parser")

    # Private
    # Search the title for a string
    def _titleInSoup(self, soup, string):
        return string.lower() in soup.title.string.lower()

    # Private
    # Convert ex. "22. maj 2023" to a datetime object
    def _getDatetime(self, date, format="%d. %b %Y"):
        # Split the string by " "
        d, m, y = date.split(" ")
        # Cut the name of the month to the first 3 chars
        m = m[:3]
        # Change the few danish month to english
        key = m.lower()
        if key == "maj":
            m = "may"
        elif key == "okt":
            m = "oct"
        # match m.lower():
        # 	case "maj":
        # 		m = "may"
        # 	case "okt":
        # 		m = "oct"

        # Return the datetime
        return datetime.strptime(f"{d} {m} {y}", format).date()

    def login(self):
        # Test if we are logged in
        r = self.session.get(self.host)
        if r.status_code == 200:
            soup = BS(r.text, "html.parser")
            self.loggedIn = self._titleInSoup(soup, LOGGED_IN)
            self.libraryName = soup.title.string.split("|")[0].strip()

        if not self.loggedIn:
            _LOGGER.debug(f"Logging in ({self.user.userId[:-4]})...")
            # Fetch the loginpage and prepare a soup
            # Must make a manual GET, since we are using "r" later
            r = self.session.get(self.host + URL_LOGIN_PAGE)
            soup = BS(r.text, "html.parser")

            # Prepare the payload
            payload = {}
            # Find the <form>
            form = soup.find("form")
            for input in form.find_all("input"):
                # Fill the form with the userInfo
                if input["name"] in self.user.userInfo:
                    payload[input["name"]] = self.user.userInfo[input["name"]]
                # or pass default values to payload
                else:
                    payload[input["name"]] = input["value"]

            # Send the payload as POST and prepare a new soup
            # Use the URL from "r" since we have been directed
            soup = self._fetchPage(form["action"].replace("/login", r.url), payload)

            # Set loggedIn
            self.loggedIn = self._titleInSoup(soup, LOGGED_IN)
            self.libraryName = soup.title.string.split("|")[0].strip()

        _LOGGER.debug(f"Logged in ({self.user.userId[:-4]}): {self.loggedIn}")
        return self.loggedIn

    def logout(self):
        _LOGGER.debug(f"Logging ({self.user.userId[:-4]}) out...")
        if self.loggedIn:
            self.loggedIn = (
                not self.session.get(self.host + URLS[LOGOUT]).status_code == 200
            )

    # From the users mainpage, we are able to load the URLs for the subpages
    def fetchUserLinks(self):
        _LOGGER.debug(f"Getting links for: {self.user.userId[:-4]}...")
        # Fetch "My view"
        soup = self._fetchPage(self.host + URLS[MY_PAGES])

        # Find all <a> within a specific <ul>
        for url in soup.select_one("ul[class=main-menu-third-level]").find_all("a"):
            # Only work on URLs not allready in our dict
            if not url["href"] in URLS.values():
                # Search for key and value
                # if the text of the URL starts with our value
                # update the list at the key
                for key, value in URLS.items():
                    if not self.updatedUrls:
                        self.updatedUrls = True
                    if url.text.lower().startswith(value):
                        URLS[key] = url["href"]

        # Fetch usefull user states - OBSOLETE WHEN FETCHING DETAILS
        for a_status in soup.select_one("ul[class='list-links specials']").find_all(
            "a"
        ):
            if URLS[DEBTS] in a_status["href"]:
                self.user.debts = a_status.parent.find_all("span")[-1].string

    # Get information on the user
    def fetchUserInfo(self):
        _LOGGER.debug(f"Getting info on: {self.user.userId[:-4]}...")
        # Fetch the user profile page
        soup = self._fetchPage(self.host + URLS[USER_PROFILE])

        # From the <div> with a class containing the given name
        for fields in soup.select_one("div[class=content]").select(
            "div[class*=field-name]"
        ):
            # Crappy HTML page....
            # Find the fieldName tag
            fieldName = fields.select_one("div[class=field-label]")
            # Get the parent of the fieldName tag and extract the value from the sub div
            fieldValue = fieldName.parent.select_one("div[class=field-items]").div
            # Remove <br>
            for e in fieldValue.findAll("br"):
                e.extract()

            # Find the correct place for the field
            key = fieldName.string.lower()
            if key == "navn":
                self.user.name = fieldValue.string
            elif key == "adresse":
                self.user.address = fieldValue.contents
            # match fieldName.string.lower():
            # 	case "navn":
            # 		self.user.name = fieldValue.string
            # 	case "adresse":
            # 		self.user.address = fieldValue.contents

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
        for library in form.select_one("select[name*='preferred_branch']").find_all(
            "option"
        ):
            if "selected" in library.attrs:
                self.user.pickupLibrary = library.string
                break

    # Get the loans with all possible details
    def fetchLoans(self):
        _LOGGER.debug(f"Getting loans on: {self.user.userId[:-4]}...")
        self.user.loans = []
        # Fecth the loans page
        soup = self._fetchPage(self.host + URLS[LOANS])

        # From the <div> with the materials
        for material in soup.select("div[class*='material-item']"):
            # Create an instance of libraryLoan
            loan = libraryLoan()

            # Renewable
            loan.renewAble = not "disabled" in material.input.attrs
            loan.renewid = material.input["value"]

            # URL and image
            loan.url = self.host + material.a["href"] if material.a else ""
            loan.coverUrl = material.img["src"] if material.img else ""

            # Type, title and creator
            loanType = material.select_one("div[class=item-material-type]")
            loan.type = (
                material.select_one("div[class=item-material-type]").string
                if loanType
                else ""
            )
            # Some title have the type in "()", remove it
            loan.title = material.h3.string.split("(")[0].strip()
            loan.creators = (
                material.select_one("div[class=item-creators]").string
                if material.select_one("div[class=item-creators]")
                else ""
            )

            # Dates and ID
            for li in material.find_all("li"):
                value = li.select_one("div[class=item-information-data]").string
                key = li["class"][-1]
                if key == "loan-date":
                    loan.loanDate = self._getDatetime(value)
                elif key == "expire-date":
                    loan.expireDate = self._getDatetime(value)
                elif key == "material-number":
                    loan.id = value
                # Uncomment when using python >= 3.10
                # match li["class"][-1]:
                # 	case "loan-date":
                # 		loan.loanDate = self._getDatetime(value)
                # 	case "expire-date":
                # 		loan.expireDate = self._getDatetime(value)
                # 	case "material-number":
                # 		loan.id = value

            # Add the loan to the stack
            self.user.loans.append(loan)

        # Sort the loans by expireDate and the Title
        self.user.loans.sort(key=lambda x: (x.expireDate, x.title))
        # If any loans, set the nextExpireDate to the first loan in the list
        if self.user.loans:
            self.user.nextExpireDate = self.user.loans[0].expireDate

    # Get the current reservations
    def fetchReservations(self):
        _LOGGER.debug(f"Getting reservations on: {self.user.userId[:-4]}...")
        self.user.reservations = []
        # Fecth the reservations page
        soup = self._fetchPage(self.host + URLS[RESERVATIONS])

        # From the <div> with the materials
        for material in soup.select("div[class*='material-item']"):
            # Create a instance of libraryReservation
            reservation = libraryReservation()

            # Fill the reservation with info
            reservation.id = material.input["value"]
            reservation.url = self.host + material.a["href"] if material.a else ""
            reservation.coverUrl = material.img["src"] if material.img else ""
            reservation.type = (
                material.select_one("div[class=item-material-type]").string
                if material.select_one("div[class=item-material-type]")
                else ""
            )
            reservation.title = material.h3.string
            reservation.creators = (
                material.select_one("div[class=item-creators]").string
                if material.select_one("div[class=item-creators]")
                else ""
            )

            # Loop the <li> of the reservation
            for li in material.find_all("li"):
                # Extract the value
                value = li.select_one("div[class=item-information-data]").string
                # Match on the last element of the Class in <li>
                key = li["class"][-1]
                if key == "expire-date":
                    reservation.expireDate = self._getDatetime(value)
                elif key == "created-date":
                    reservation.createdDate = self._getDatetime(value)
                elif key == "queue-number":
                    reservation.queueNumber = value
                elif key == "pickup-branch":
                    reservation.pickupLibrary = value
                # match li["class"][-1]:
                # 	case "expire-date":
                # 		reservation.expireDate = self._getDatetime(value)
                # 	case "created-date":
                # 		reservation.createdDate = self._getDatetime(value)
                # 	case "queue-number":
                # 		reservation.queueNumber = value
                # 	case "pickup-branch":
                # 		reservation.pickupLibrary = value

            # Add the reservation to the stack
            self.user.reservations.append(reservation)

            # Sort the reservations
            self.user.reservations.sort(
                key=lambda x: (x.queueNumber, x.createdDate, x.title)
            )

    # Get the reservations which are ready
    def fetchReservationsReady(self):
        _LOGGER.debug(
            f"Getting reservations ready for pickup on: {self.user.userId[:-4]}..."
        )
        self.user.reservationsReady = []
        # Fecth the ready reservations page
        soup = self._fetchPage(self.host + URLS[RESERVATIONS_READY])

        # From the <div> with the materials
        for material in soup.select("div[class*='material-item']"):
            # Create a instance of libraryReservation
            reservationReady = libraryReservationReady()

            # Fill the reservation with info
            reservationReady.id = material.input["value"]
            reservationReady.url = self.host + material.a["href"] if material.a else ""
            reservationReady.coverUrl = material.img["src"] if material.img else ""
            reservationReady.type = (
                material.select_one("div[class=item-material-type]").string
                if material.select_one("div[class=item-material-type]")
                else ""
            )
            reservationReady.title = material.h3.string
            reservationReady.creators = (
                material.select_one("div[class=item-creators]").string
                if material.select_one("div[class=item-creators]")
                else ""
            )

            # Loop the <li> of the reservation
            for li in material.find_all("li"):
                # Extract the value
                value = li.select_one("div[class=item-information-data]").string
                # Match on the last element of the Class in <li>
                key = li["class"][-1]
                if key == "pickup-id":
                    reservationReady.reservationNumber = value
                elif key == "pickup-date":
                    reservationReady.pickupDate = self._getDatetime(value)
                elif key == "created-date":
                    reservationReady.createdDate = self._getDatetime(value)
                elif key == "pickup-branch":
                    reservationReady.pickupLibrary = value

            # Add the reservation to the stack
            self.user.reservationsReady.append(reservationReady)

            # Sort the reservations
            self.user.reservationsReady.sort(key=lambda x: (x.pickupDate, x.title))


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
    renewid, renewAble = None, None


class libraryReservation(libraryMaterial):
    createdDate, expireDate, queueNumber = None, None, None
    pickupLibrary = None


class libraryReservationReady(libraryMaterial):
    createdDate, pickupDate, reservationNumber = None, None, None
    pickupLibrary = None
