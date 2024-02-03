from __future__ import annotations

from bs4 import BeautifulSoup as BS
from datetime import datetime
import logging
import random
import re
import requests

from .const import (
    CONF_AGENCY,
    HEADERS,
    URL_LOGIN_PAGE,
    URL_LOGIN_PAGE_ELIB,
    USER_AGENTS,
)

DEBUG = True

#### KEYS
DEBTS = "DEBTS"
LOANS = "LOANS"
LOANS_OVERDUE = "LOANS_OVERDUE"
LOGOUT = "LOGOUT"
LOGOUT_ELIB = "LOGOUT_ELIB"
MY_PAGES = "MY_PAGES"
RESERVATIONS = "RESERVATIONS"
RESERVATIONS_READY = "RESERVATIONS_READY"
USER_PROFILE = "USER_PROFILE"

#### LINKS TO USER PAGES
URLS = {
    DEBTS: "/user/me/status-debts",
    LOANS: "/user/me/status-loans",
    LOANS_OVERDUE: "/user/me/status-loans-overdue",
    LOGOUT: "/user/logout",
    LOGOUT_ELIB: "/user/me/logout",
    MY_PAGES: "/user/me/view",
    RESERVATIONS: "/user/me/status-reservations",
    RESERVATIONS_READY: "/user/me/status-reservations-ready",
    USER_PROFILE: "/user/me/edit",
}

### IDENTIFIERS FOR CONTENT DIVS
DIVS = {
    DEBTS: "pane-debts",
    LOANS: "pane-loans",
    LOANS_OVERDUE: "pane-loans",
    RESERVATIONS: "pane-reservations",
    RESERVATIONS_READY: "pane-reservations",
}

#### SEARCH STRINGS
LOGGED_IN = "logget ind"
LOGGED_IN_ELIB = "Logged-in"
EBOOKS = "ebøger"
AUDIO_BOOKS = "lydbøger"

_LOGGER: logging.Logger = logging.getLogger(__package__)
_LOGGER = logging.getLogger(__name__)


class Library:
    host, libraryName, icon, user = None, None, None, None
    loggedIn, eLoggedIn, running = False, False, False

    def __init__(
        self, userId: str, pincode: str, host=str, libraryName=None, agency=None
    ) -> None:

        # Prepare a new session with a random user-agent
        HEADERS["User-Agent"] = random.choice(USER_AGENTS)
        self.session = requests.Session()
        self.session.headers = HEADERS

        self.host = host
        self.host_elib = "https://ereolen.dk"
        self.user = libraryUser(userId=userId, pincode=pincode)
        self.municipality = libraryName
        self.agency = agency

    # The update function is called from the coordinator from Home Assistant
    def update(self):
        _LOGGER.debug("Updating (%s)", self.user.userId[:-4])

        # Only one user can login at the time.
        self.running = True

        if self.login():
            # Only fetch user info once
            if not self.user.name:
                self.fetchUserInfo()

            # Fetch the states of the user
            self.user.loans = self.fetchLoans()
            self.user.loansOverdue = self.fetchLoansOverdue()
            self.user.reservations = self.fetchReservations()
            self.user.reservationsReady = self.fetchReservationsReady()
            self.user.debts, self.user.debtsAmount = self.fetchDebts()

            # Logout
            self.logout()

            # eReolen
            if self.municipality and self.agency:
                loginResult, soup = self.login_eLib()
                if loginResult:
                    if soup:
                        self.fecthELibUsedQuota(soup)
                        self.user.loans.extend(self.fetchLoans(soup))
                        self.user.reservations.extend(self.fetchReservations(soup))
                        self.user.reservationsready.extend(self.fetchReservationsReady(soup))

                    # Logout of eReolen
                    self.logout(self.host_elib + URLS[LOGOUT_ELIB])

            # Sort the lists
            self.sortLists()

        self.running = False

        return True

    #### PRIVATE BEGIN ####
    # Retrieve a webpage with either GET/POST
    def _fetchPage(self, url=str, payload=None, return_r=False) -> BS | tuple:
        try:
            # If payload, use POST
            if payload:
                r = self.session.post(url, data=payload)

            # else use GET
            else:
                r = self.session.get(url)

            r.raise_for_status()

        except requests.exceptions.HTTPError as err:
            _LOGGER.error(f"HTTP Error while fetching {url}: {err}")
            # Handle the error as needed, e.g., raise it, log it, or notify the user.
            return None if return_r else None, None 
        except requests.exceptions.Timeout:
            _LOGGER.error("Timeout fecthing (%s)", url)
            return None if return_r else None, None
        except requests.exceptions.TooManyRedirects:
            _LOGGER.error("Too many redirects fecthing (%s)", url)
            return None if return_r else None, None
        except requests.exceptions.RequestException as err:
            _LOGGER.error(f"Request Exception while fetching {url}: {err}")
            return None if return_r else None, None

        if return_r:
            return BS(r.text, "html.parser"), r

        # Return HTML soup
        return BS(r.text, "html.parser")

    # Search for given string in the HTML soup
    def _titleInSoup(self, soup, string) -> bool:
        try:
            result = string.lower() in soup.title.string.lower()
        except (AttributeError, KeyError) as err:
            _LOGGER.error(
                "Error in finding (%s) in the title of the page. Error: (%s)",
                string.lower(),
                err,
            )
        return result

    # Convert ex. "22. maj 2023 [23:12:45]" to a datetime object
    def _getDatetime(self, date, a_format="%d. %b %Y") -> datetime:
        # Split the string by the " "
        date = date.split(" ")

        # Extract time if present (ebooks etc.)
        t = date.pop() if len(date) == 4 else None

        # Unpack into separate elements
        d, m, y = date

        # Check that there actually is a date
        _LOGGER.debug("Day (%s) is numeric: (%s)",d,d.split(".")[0].isnumeric())
        if not d.split(".")[0].isnumeric(): return None
        
        # Cut the name of the month to the first 3 chars
        m = m[:3]
        # Change the few danish month to english
        key = m.lower()
        if key == "maj":
            m = "may"
        elif key == "okt":
            m = "oct"

        # Create a datetime with the date
        date = datetime.strptime(f"{d} {m} {y}", a_format)
        # If Time is present, add it to the date
        if t:
            h, m, s = t.split(":")
            return date.replace(hour=int(h), minute=int(m), second=int(s))
        # Return the date
        return date

    def sortLists(self):
        # Sort the loans by expireDate and the Title
        self.user.loans.sort(key=lambda obj: (obj.expireDate is None, obj.expireDate, obj.title))
        # Sort the reservations
        self.user.reservations.sort(
            key=lambda obj: (
                obj.createdDate is None, 
                obj.queueNumber,
                obj.createdDate,
                obj.title,
            )
        )
        # Sort the reservations
        self.user.reservationsReady.sort(key=lambda obj: (obj.pickupDate is None, obj.pickupDate, obj.title))

    def _getMaterials(self, soup, noodle="div[class*='material-item']") -> BS:
        try:
            result = soup.select(noodle)
        except (AttributeError, KeyError) as err:
            _LOGGER.error(
                "Error in getting the <div> with this noodle (%s). Error: (%s)",
                noodle,
                err,
            )
        return result

    def _getIdInfo(self, material) -> tuple:
        try:
            value = material.input["value"]
            renewAble = not "disabled" in material.input.attrs
        except (AttributeError, KeyError) as err:
            _LOGGER.error(
                "Error in getting the Id and renewable on the material. Error: (%s)",
                err,
            )
        return value, renewAble

    def _getMaterialUrls(self, material) -> tuple:
        return (
            self.host + material.a["href"] if material.a else "",
            material.img["src"] if material.img else "",
        )

    def _getMaterialInfo(self, material) -> tuple:
        materialTitle, materialCreators, materialType = "", "", ""
        # Some title have the type in "()", remove it
        # by splitting the string by the first "(" and use
        # only the first element, stripping whitespaces
        materialTitle = material.select_one("[class*='item-title']")
        try:
            if materialTitle:
                materialTitle = materialTitle.string
            if materialTitle and "(" in materialTitle:
                materialTitle = materialTitle.split("(")[0].strip()
        except (AttributeError, KeyError) as err:
            _LOGGER.error("Error searching for the title. Error: %s", err)

        # Assume it is a physical loan
        materialType = material.select_one("div[class=item-material-type]")
        try:
            if materialType:
                materialType = materialType.string
            # Ok, maybe it is a digital
            else:
                materialType = material.select_one("span[class*='icon']")
                if materialType:
                    result = re.search(
                        "This material is a (.+?) and", materialType["aria-label"]
                    )
                    # Yes, it is a digital
                    if result:
                        materialType = result.group(1)
                # I have no idea...
                else:
                    materialType = ""
        except (AttributeError, KeyError) as err:
            _LOGGER.error("Error in getting the materialType. Error: (%s)", err)

        materialCreators = material.select_one("div[class=item-creators]")
        try:
            materialCreators = materialCreators.string if materialCreators else ""
        except (AttributeError, KeyError) as err:
            _LOGGER.error("Error in getting the materialCreators. Error: (%s)", err)

        return materialTitle, materialCreators, materialType

    # Loop <li>
    # (re)Join the class(es) with a " ", use as key
    def _getDetails(self, material):
        details = {}
        try:
            for li in material.find_all("li"):
                details[" ".join(li["class"])] = li.select_one(
                    "div[class=item-information-data]"
                ).string
        except (AttributeError, KeyError) as err:
            _LOGGER.error(
                "Error in getting the Details of af material. Error: (%s)", err
            )

        return details.items()

    def _removeCurrency(self, amount) -> float:
        result = re.search(r"(\d*\,\d*)", amount)
        if result:
            amount = float(result.group(1).replace(",", "."))
        return amount

    ####  PRIVATE END  ####
    def login(self):

        # Test if we are logged in by fetching the main page
        soup, r = self._fetchPage(url=self.host, return_r=True)
        if r.status_code == 200:

            self.loggedIn = self._titleInSoup(soup, LOGGED_IN)
            # Retrieve the name of the Library from the title tag
            # <title>Faaborg-Midtfyn Bibliotekerne | | Logget ind</title>
            try:
                self.libraryName = soup.title.string.split("|")[0].strip()
            except (AttributeError, KeyError) as err:
                _LOGGER.error(
                    "Error in getting the title of the page (%s). Error: (%s)",
                    self.host,
                    err,
                )

            # Fetch the icon of the library
            self.icon = soup.select_one("link[rel*='icon']")
            self.icon = self.icon["href"] if self.icon else None

        if not self.loggedIn:
            # Fetch the loginpage and prepare a soup
            soup, r = self._fetchPage(url=self.host + URL_LOGIN_PAGE, return_r=True)

            # Prepare the payload
            payload = {}
            # Find the <form>
            try:
                form = soup.find("form")
                for inputTag in form.find_all("input"):
                    # Fill the form with the userInfo
                    if inputTag["name"] in self.user.userInfo:
                        payload[inputTag["name"]] = self.user.userInfo[inputTag["name"]]
                    # or pass default values to payload
                    else:
                        payload[inputTag["name"]] = inputTag["value"]

                # Send the payload as POST and prepare a new soup
                # Use the URL from the response since we have been directed
                soup = self._fetchPage(form["action"].replace("/login", r.url), payload)
            except (AttributeError, KeyError) as err:
                _LOGGER.error(
                    "Error processing the <form> tag and subtags (%s). Error: (%s)",
                    self.host + URL_LOGIN_PAGE,
                    err,
                )

            # Set loggedIn
            self.loggedIn = self._titleInSoup(soup, LOGGED_IN)

        if DEBUG:
            _LOGGER.debug("(%s) is logged in: %s", self.user.userId[:-4], self.loggedIn)

        return self.loggedIn

    def login_eLib(self) -> tuple:
        # Make sure we are logged OUT
        if self.loggedIn:
            self.logout()
            return self.login_eLib()

        # Test if we are logged in at eReolen.dk
        soup, r = self._fetchPage(url=self.host_elib, return_r=True)
        if r.status_code == 200:
            self.eLoggedIn = self._titleInSoup(soup, LOGGED_IN_ELIB)

        if not self.loggedIn:
            soup, r = self._fetchPage(
                url=self.host_elib + URL_LOGIN_PAGE_ELIB, return_r=True
            )

            payload = self.user.userInfo
            payload[CONF_AGENCY] = self.agency

            try:
                libraryFormToken = soup.select_one("input[name*=libraryName-]")
                if libraryFormToken:
                    payload[libraryFormToken["name"]] = self.municipality

                # Send the payload aka LOGIN
                soup = self._fetchPage(
                    soup.form["action"].replace("/login", r.url), payload
                )
                self.loggedIn = (
                    soup if self._titleInSoup(soup, LOGGED_IN_ELIB) else False
                )
            except (AttributeError, KeyError) as err:
                _LOGGER.error(
                    "Error processing the <form> tag and subtags (%s). Error: (%s)",
                    self.host_elib + URL_LOGIN_PAGE_ELIB,
                    err,
                )

        if DEBUG:
            _LOGGER.debug(
                "(%s) is logged in @%s: {bool(self.loggedIn)}",
                self.user.userId[:-4],
                self.host_elib,
            )

        return self.loggedIn, soup

    def logout(self, url=None):
        url = self.host + URLS[LOGOUT] if not url else url
        if self.loggedIn:
            # Fetch the logout page, if given a 200 (true) reverse it to false
            self.loggedIn = not self.session.get(url).status_code == 200
            if not self.loggedIn:
                self.session.close()
        if DEBUG:
            _LOGGER.debug(
                "(%s) is logged OUT @%s: %s",
                self.user.userId[:-4],
                url,
                not bool(self.loggedIn),
            )

    def fecthELibUsedQuota(self, soup):
        try:
            for li in soup.h1.parent.div.ul.find_all("li"):
                result = re.search(r"(\d+) ud af (\d+) (ebøger|lydbøger)", li.string)
                if result:
                    if result.group(3) == EBOOKS:
                        self.user.eBooks = result.group(1)
                        self.user.eBooksQuota = result.group(2)
                    elif result.group(3) == AUDIO_BOOKS:
                        self.user.audioBooks = result.group(1)
                        self.user.audioBooksQuota = result.group(2)
        except (AttributeError, KeyError) as err:
            _LOGGER.error("Error getting the quotas of eReolen. Error: (%s)", err)

        if DEBUG:
            _LOGGER.debug(
                "(%s), done fetching eLibQuotas: (%s/%s) (%s/%s)",
                self.user.userId[:-4],
                self.user.eBooks,
                self.user.eBooksQuota,
                self.user.audioBooks,
                self.user.audioBooksQuota,
            )

    # Get information on the user
    def fetchUserInfo(self):
        # Fetch the user profile page
        soup = self._fetchPage(self.host + URLS[USER_PROFILE])

        try:
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
        except (AttributeError, KeyError) as err:
            _LOGGER.error(
                "Error getting user info (%s). Error: (%s)",
                self.host + URLS[USER_PROFILE],
                err,
            )

        if DEBUG:
            _LOGGER.debug(
                "(%s) is actually '%s'. Pickup library is %s",
                self.user.userId[:-4],
                self.user.name,
                self.user.pickupLibrary,
            )

    # Get the loans with all possible details
    def fetchLoans(self, soup=None) -> list:
        # Fetch the loans page
        if not soup:
            soup = self._fetchPage(self.host + URLS[LOANS])

        # From the <div> containing part of the class
        # for material in soup.select("div[class*='material-item']"):
        tempList = []
        for material in self._getMaterials(soup.find("div", class_=DIVS[LOANS])):
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

        if DEBUG:
            _LOGGER.debug("%s has %s loans", self.user.name, len(tempList))

        return tempList

    def fetchLoansOverdue(self) -> list:
        if DEBUG:
            _LOGGER.debug("%s, Reusing the fetchLoans function", self.user.name)
        # Fetch the loans overdue page
        return self.fetchLoans(self._fetchPage(self.host + URLS[LOANS_OVERDUE]))

    # Get the current reservations
    def fetchReservations(self, soup=None) -> list:
        # Fecth the reservations page
        if not soup:
            soup = self._fetchPage(self.host + URLS[RESERVATIONS])

        tempList = []
        # From the <div> with containg the class of the materials
        _LOGGER.debug("Number of divs (%s): (%d)",DIVS[RESERVATIONS],len(soup.select("."+DIVS[RESERVATIONS])))
        for material in self._getMaterials(soup.find_all("div", class_=DIVS[RESERVATIONS])[len(soup.select("."+DIVS[RESERVATIONS]))-1]):
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

        if DEBUG:
            _LOGGER.debug("%s has %s reservations", self.user.name, len(tempList))

        return tempList

    # Get the reservations which are ready
    def fetchReservationsReady(self, soup=None) -> list:
        # Fecth the ready reservationsReady page
        if not soup:
            soup = self._fetchPage(self.host + URLS[RESERVATIONS_READY])

        tempList = []
        # From the <div> with the materials
        for material in self._getMaterials(soup.find("div", class_=DIVS[RESERVATIONS_READY])):
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

        if DEBUG:
            _LOGGER.debug(
                "%s has %s reservations ready for pickup", self.user.name, len(tempList)
            )

        return tempList

    # Get debts, if any, from the Library
    def fetchDebts(self) -> tuple:
        # Fetch the debts page
        soup = self._fetchPage(self.host + URLS[DEBTS])

        tempList = []
        # From the <div> with containg the class of the materials
        for material in self._getMaterials(soup):
            obj = libraryDebt()

            # Get the first element (id)
            obj.id = self._getIdInfo(material)[0]

            # URL and image
            obj.url, obj.coverUrl = self._getMaterialUrls(material)

            # Type, title and creator
            obj.title, obj.creators, obj.type = self._getMaterialInfo(material)

            # Details
            for keys, value in self._getDetails(material):
                if "fee-date" in keys:
                    obj.feeDate = self._getDatetime(value)
                elif "fee-type" in keys:
                    obj.feeType = value
                elif "fee_amount" in keys:
                    obj.feeAmount = self._removeCurrency(value)

            tempList.append(obj)

        try:
            amount = soup.select_one("span[class='amount']")
            amount = self._removeCurrency(amount.string) if amount else 0.0
        except (AttributeError, KeyError) as err:
            _LOGGER.error("Error processing the debt amount. Error: (%s)", err)

        if DEBUG:
            _LOGGER.debug(
                "%s has %s debts with a total of {amount}",
                self.user.name,
                len(tempList),
            )

        return tempList, amount


class libraryUser:
    userInfo = None
    name, address = None, None
    phone, phoneNotify, mail, mailNotify = None, None, None, None
    loans, loansOverdue, reservations, reservationsReady, debts = [], [], [], [], []
    debtsAmount = 0.0
    eBooks, eBooksQuota, audioBooks, audioBooksQuota = 0, 0, 0, 0
    pickupLibrary = None

    def __init__(self, userId: str, pincode: str) -> None:
        self.userInfo = {"loginBibDkUserId": userId, "pincode": pincode}
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


class libraryDebt(libraryMaterial):
    feeDate, feeType, feeAmount = None, None, None
