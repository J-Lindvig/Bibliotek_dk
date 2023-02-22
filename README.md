

# Bibliotek (library)
![image](https://user-images.githubusercontent.com/54498188/220741705-0e2aec42-e582-4161-ad13-d66e537c5272.png)
## Home Assistant custom integration for all public libraries in Denmark
## Installation
1. Add this repository to your HACS as a manual integration. when the integration is finished and stable, I will add it to HACS' default.
2. Download it in HACS
3. Restart your Home Assistant
## Configuration
All the configuration is done in GUI.

![image](https://user-images.githubusercontent.com/54498188/220758300-7c87b080-938d-467b-b19a-11c6e6d66f99.png)

1. Just add the integration on your integrationspage.
2. Fill the form with the needed and optional information (**required is bold**, optional is not):
- Name, added to the name of the integration, fx. "Faaborg-Midtfyn Bibliotekerne (Jacob Lindvig Henriksen)"
- **Municipality**, Home Assistant will try to determine this from the coordinates of your home zone
- **CPR - number / loannumber**
- **Pincode**
- Show loans, boolean (default true)
- Show reservations, boolean (default true)
- Show reservations ready, boolean (default true)
- Update interval, minutes (default 60)

## Usage
With this custom integration for [Home Assistant](https://www.home-assistant.io/) you will probably never be late again on your returns.
The integrations creates 4 sensors:

- [General Library Sensor](#general-library-sensor)
- [Loans sensor](#loans-sensor)
- [Reservations sensor](#reservations-sensor)
- [Reservations Ready sensor](#reservations-ready-sensor)

### General Library Sensor
In its current state (yes it is still in development), you will get 4 diffent sensors:
- A general sensor with "days to return" in state and states on :
  - Loans
  - Reservations
  - Reservations ready for pickup
  - Debts
  - Your profile information and settings from the library
### Loans sensor
- A "Loans" sensor with number of loans as state and all available details on the materials (if supplied by the library):
  - Title
  - Creators
  - Type
  - Date of loan
  - Date of return
  - Whether the material is renewable
  - Link to the info on the website
  - URL to the bookcover
### Reservations sensor
Almost identical to the [Loans sensor](#loans-sensor) with these differences:
- Queue number
- Date of reservation
- Date of expiration
- Pick-up location
- ~~Date of loan~~
- ~~Date of return~~
- ~~Whether the material is renewable~~
### Reservations Ready sensor
Again almost identical to the prior [Reservations sensor](#reservations-sensor), but with these differences:
- Reservation number
- Date of available for pickup
- Date of last chance for pickup
- Pick-up location
- ~~Queue number~~
