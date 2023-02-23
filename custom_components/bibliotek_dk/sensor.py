"""Platform for sensor integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from datetime import timedelta, datetime
import asyncio
import random
import hashlib

from .const import (
    CONF_UPDATE_INTERVAL,
    CREDITS,
    DOMAIN,
    CONF_SHOW_LOANS,
    CONF_SHOW_RESERVATIONS,
    CONF_SHOW_RESERVATIONS_READY,
)
from homeassistant.const import ATTR_ATTRIBUTION, ATTR_UNIT_OF_MEASUREMENT

from .library_api import Library, libraryUser

_LOGGER: logging.Logger = logging.getLogger(__package__)
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:

    # Define a update function
    async def async_update_data():

        # Only run one instance at a time...
        if DOMAIN in hass.data:
            while any(
                libraryObj.running == True for libraryObj in hass.data[DOMAIN].values()
            ):
                waitTime = random.randint(5, 10)
                _LOGGER.debug(
                    f"Instance of Library already running, waiting {waitTime} seconds before next probing..."
                )
                await asyncio.sleep(waitTime)

        # Retrieve the client stored in the hass data stack
        myLibrary = hass.data[DOMAIN][entry.entry_id]
        # Call, and wait for it to finish, the function with the refresh procedure
        await hass.async_add_executor_job(myLibrary.update)

    # Create a coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sensor",
        update_method=async_update_data,
        update_interval=timedelta(minutes=int(entry.data[CONF_UPDATE_INTERVAL])),
    )

    # Immediate refresh
    await coordinator.async_request_refresh()

    """Add sensor entry."""
    sensors = []

    # Library
    myLibrary = hass.data[DOMAIN][entry.entry_id]
    sensors.append(LibrarySensor(hass, myLibrary, coordinator))

    # Loans
    if entry.data[CONF_SHOW_LOANS]:
        sensors.append(LoanSensor(hass.data[DOMAIN][entry.entry_id].user, coordinator))

    # Reservations
    if entry.data[CONF_SHOW_RESERVATIONS]:
        sensors.append(
            ReservationSensor(hass.data[DOMAIN][entry.entry_id].user, coordinator)
        )

    # Reservations Ready
    if entry.data[CONF_SHOW_RESERVATIONS_READY]:
        sensors.append(
            ReservationReadySensor(hass.data[DOMAIN][entry.entry_id].user, coordinator)
        )

    async_add_entities(sensors)


def md5_unique_id(string):
    return hashlib.md5(string.encode("utf-8")).hexdigest()


class LibrarySensor(SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        myLibrary: Library,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        self.myLibrary = myLibrary
        self._name = f"{self.myLibrary.libraryName} ({self.myLibrary.user.name})"
        self._unique_id = md5_unique_id(
            self.myLibrary.libraryName + self.myLibrary.user.userId
        )
        self.coordinator = coordinator

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        return "mdi:library"

    @property
    def state(self):
        if len(self.myLibrary.user.loans) > 0:
            return (self.myLibrary.user.nextExpireDate - datetime.now()).days
        return ""

    @property
    def extra_state_attributes(self):
        attr = {
            "loans": len(self.myLibrary.user.loans),
            "reservations": len(self.myLibrary.user.reservations),
            "reservations_ready": len(self.myLibrary.user.reservationsReady),
            "debts": self.myLibrary.user.debts,
            "user": self.myLibrary.user.name,
            "address": self.myLibrary.user.address,
            "phone": self.myLibrary.user.phone,
            "phone_notifications": self.myLibrary.user.phoneNotify,
            "mail": self.myLibrary.user.mail,
            "mail_notifications": self.myLibrary.user.mailNotify,
            "pickup_library": self.myLibrary.user.pickupLibrary,
            ATTR_UNIT_OF_MEASUREMENT: "days",
            ATTR_ATTRIBUTION: CREDITS,
        }
        # If agency is set, bring eReolen
        if self.myLibrary.agency:
            attr.update(
                {
                    "ebooks": self.myLibrary.user.eBooks,
                    "ebooks_quota": self.myLibrary.user.eBooksQuota,
                    "audiobooks": self.myLibrary.user.audioBooks,
                    "audiobooks_quota": self.myLibrary.user.audioBooksQuota,
                }
            )

        return attr

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_update(self):
        """Update the entity. Only used by the generic entity update service."""
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class LoanSensor(SensorEntity):
    def __init__(
        self,
        libraryUser: libraryUser,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        self.libraryUser = libraryUser
        self.coordinator = coordinator
        self._name = f"Bibliotekslån ({self.libraryUser.name})"
        self._unique_id = md5_unique_id("Loans_" + self.libraryUser.userId)

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        loanAmount = len(self.libraryUser.loans)
        if loanAmount == 0:
            return "mdi:book-cancel"
        elif loanAmount == 1:
            return "mdi:book"
        else:
            return "mdi:book-multiple"

    @property
    def state(self):
        return len(self.libraryUser.loans)

    @property
    def extra_state_attributes(self):
        attr = {}
        loans = []
        for loan in self.libraryUser.loans:
            details = {
                "title": loan.title,
                "creators": loan.creators,
                "type": loan.type,
                "loan_date": loan.loanDate,
                "expire_date": loan.expireDate,
                "renewable": loan.renewAble,
                "url": loan.url,
                "cover": loan.coverUrl,
            }
            loans.append(details)
        attr["loans"] = loans
        attr[ATTR_ATTRIBUTION] = CREDITS
        return attr

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_update(self):
        """Update the entity. Only used by the generic entity update service."""
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class ReservationSensor(SensorEntity):
    def __init__(
        self,
        libraryUser: libraryUser,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        self.libraryUser = libraryUser
        self.coordinator = coordinator
        self._name = f"Reservationer ({self.libraryUser.name})"
        self._unique_id = md5_unique_id("Reservations_" + self.libraryUser.userId)

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        loanAmount = len(self.libraryUser.reservations)
        if loanAmount == 0:
            return "mdi:book-cancel"
        elif loanAmount == 1:
            return "mdi:book-plus"
        else:
            return "mdi:book-plus-multiple"

    @property
    def state(self):
        return len(self.libraryUser.reservations)

    @property
    def extra_state_attributes(self):
        attr = {}
        reservations = []
        for reservation in self.libraryUser.reservations:
            details = {
                "title": reservation.title,
                "creators": reservation.creators,
                "type": reservation.type,
                "queue_number": reservation.queueNumber,
                "created_date": reservation.createdDate,
                "expire_date": reservation.expireDate,
                "pickup_library": reservation.pickupLibrary,
                "url": reservation.url,
                "cover": reservation.coverUrl,
            }
            reservations.append(details)
        attr["reservations"] = reservations
        attr[ATTR_ATTRIBUTION] = CREDITS
        return attr

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_update(self):
        """Update the entity. Only used by the generic entity update service."""
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class ReservationReadySensor(SensorEntity):
    def __init__(
        self,
        libraryUser: libraryUser,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        self.libraryUser = libraryUser
        self.coordinator = coordinator
        self._name = f"Reservationer klar ({self.libraryUser.name})"
        self._unique_id = md5_unique_id("ReservationsReady_" + self.libraryUser.userId)

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        loanAmount = len(self.libraryUser.reservationsReady)
        if loanAmount == 0:
            return "mdi:book-cancel"
        elif loanAmount == 1:
            return "mdi:book-plus"
        else:
            return "mdi:book-plus-multiple"

    @property
    def state(self):
        return len(self.libraryUser.reservationsReady)

    @property
    def extra_state_attributes(self):
        attr = {}
        reservationsReady = []
        for reservationReady in self.libraryUser.reservationsReady:
            details = {
                "title": reservationReady.title,
                "creators": reservationReady.creators,
                "type": reservationReady.type,
                "reservation_number": reservationReady.reservationNumber,
                "created_date": reservationReady.createdDate,
                "pickup_date": reservationReady.pickupDate,
                "pickup_library": reservationReady.pickupLibrary,
                "url": reservationReady.url,
                "cover": reservationReady.coverUrl,
            }
            reservationsReady.append(details)
        attr["reservations_ready"] = reservationsReady
        attr[ATTR_ATTRIBUTION] = CREDITS
        return attr

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_update(self):
        """Update the entity. Only used by the generic entity update service."""
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
