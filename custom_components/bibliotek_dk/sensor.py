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
    CONF_SHOW_DEBTS,
    CONF_SHOW_RESERVATIONS,
)
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_UNIT_OF_MEASUREMENT,
    ATTR_ENTITY_PICTURE,
)

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
    sensors.append(LibrarySensor(myLibrary, coordinator))

    # Loans
    if entry.data[CONF_SHOW_LOANS]:
        sensors.append(LoanSensor(myLibrary.user, coordinator))
        sensors.append(LoanOverdueSensor(myLibrary.user, coordinator))

    # Debts
    if entry.data[CONF_SHOW_DEBTS]:
        sensors.append(DebtSensor(myLibrary.user, coordinator))

    # Reservations
    if entry.data[CONF_SHOW_RESERVATIONS]:
        sensors.append(ReservationSensor(myLibrary.user, coordinator))
        sensors.append(ReservationReadySensor(myLibrary.user, coordinator))

    async_add_entities(sensors)


def md5_unique_id(string):
    return hashlib.md5(string.encode("utf-8")).hexdigest()


class LibrarySensor(SensorEntity):
    def __init__(
        self,
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
            return (
                self.myLibrary.user.loans[0].expireDate.date() - datetime.now().date()
            ).days
        return ""

    @property
    def extra_state_attributes(self):
        attr = {
            "loans": len(self.myLibrary.user.loans),
            "loans_overdue": len(self.myLibrary.user.loansOverdue),
            "reservations": len(self.myLibrary.user.reservations),
            "reservations_ready": len(self.myLibrary.user.reservationsReady),
            "debts": len(self.myLibrary.user.debts),
            "user": self.myLibrary.user.name,
            "address": self.myLibrary.user.address,
            "phone": self.myLibrary.user.phone,
            "phone_notifications": self.myLibrary.user.phoneNotify,
            "mail": self.myLibrary.user.mail,
            "mail_notifications": self.myLibrary.user.mailNotify,
            "pickup_library": self.myLibrary.user.pickupLibrary,
            "sensor_type": "main",
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

        # PNG as icon/entity-picture
        if self.myLibrary.icon:
            attr.update({ATTR_ENTITY_PICTURE: self.myLibrary.icon})

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
        amount = len(self.libraryUser.loans)
        if amount == 0:
            return "mdi:book-cancel"
        elif amount == 1:
            return "mdi:book"
        else:
            return "mdi:book-multiple"

    @property
    def state(self):
        return len(self.libraryUser.loans)

    @property
    def extra_state_attributes(self):
        attr = {"user": self.libraryUser.name}
        loans = []
        for loan in self.libraryUser.loans:
            loans.append(
                {
                    "title": loan.title,
                    "creators": loan.creators,
                    "type": loan.type,
                    "loan_date": loan.loanDate,
                    "expire_date": loan.expireDate,
                    "renewable": loan.renewAble,
                    "url": loan.url,
                    "cover": loan.coverUrl,
                }
            )
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


class LoanOverdueSensor(SensorEntity):
    def __init__(
        self,
        libraryUser: libraryUser,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        self.libraryUser = libraryUser
        self.coordinator = coordinator
        self._name = f"Bibliotekslån overskredet ({self.libraryUser.name})"
        self._unique_id = md5_unique_id("LoansOverdue_" + self.libraryUser.userId)

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        amount = len(self.libraryUser.loansOverdue)
        if amount == 0:
            return "mdi:alarm-off"
        elif amount == 1:
            return "mdi:alarm"
        else:
            return "mdi:alarm-multiple"

    @property
    def state(self):
        return len(self.libraryUser.loansOverdue)

    @property
    def extra_state_attributes(self):
        attr = {"user": self.libraryUser.name}
        loans_overdue = []
        for loan_overdue in self.libraryUser.loansOverdue:
            loans_overdue.append(
                {
                    "title": loan_overdue.title,
                    "creators": loan_overdue.creators,
                    "type": loan_overdue.type,
                    "loan_date": loan_overdue.loanDate,
                    "expire_date": loan_overdue.expireDate,
                    "url": loan_overdue.url,
                    "cover": loan_overdue.coverUrl,
                }
            )
        attr["loans_overdue"] = loans_overdue
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
        amount = len(self.libraryUser.reservations)
        if amount == 0:
            return "mdi:book-cancel"
        elif amount == 1:
            return "mdi:book-plus"
        else:
            return "mdi:book-plus-multiple"

    @property
    def state(self):
        return len(self.libraryUser.reservations)

    @property
    def extra_state_attributes(self):
        attr = {"user": self.libraryUser.name}
        reservations = []
        for reservation in self.libraryUser.reservations:
            reservations.append(
                {
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
            )
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
        amount = len(self.libraryUser.reservationsReady)
        if amount == 0:
            return "mdi:book-cancel"
        elif amount == 1:
            return "mdi:book-plus"
        else:
            return "mdi:book-plus-multiple"

    @property
    def state(self):
        return len(self.libraryUser.reservationsReady)

    @property
    def extra_state_attributes(self):
        attr = {"user": self.libraryUser.name}
        reservationsReady = []
        for reservationReady in self.libraryUser.reservationsReady:
            reservationsReady.append(
                {
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
            )
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


class DebtSensor(SensorEntity):
    def __init__(
        self,
        libraryUser: libraryUser,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        self.libraryUser = libraryUser
        self.coordinator = coordinator
        self._name = f"Gebyrer ({self.libraryUser.name})"
        self._unique_id = md5_unique_id("Debts_" + self.libraryUser.userId)

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        amount = len(self.libraryUser.debts)
        if amount == 0:
            return "mdi:numeric-0"
        elif amount == 1:
            return "mdi:cash"
        else:
            return "mdi:cash-multiple"

    @property
    def state(self):
        return self.libraryUser.debtsAmount

    @property
    def extra_state_attributes(self):
        attr = {"user": self.libraryUser.name}
        debts = []
        for debt in self.libraryUser.debts:
            debts.append(
                {
                    "title": debt.title,
                    "type": debt.type,
                    "fee_date": debt.feeDate,
                    "fee_type": debt.feeType,
                    "fee_amount": debt.feeAmount,
                    "url": debt.url,
                    "cover": debt.coverUrl,
                }
            )
        attr["debts"] = debts
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
