# Bibliotek
![image](https://user-images.githubusercontent.com/54498188/220741705-0e2aec42-e582-4161-ad13-d66e537c5272.png)
## Home Assistant custom integration for all public libraries in Denmark
With this custom integration for [Home Assistant](https://www.home-assistant.io/) you will probably never be late again on your returns.
The integrations creates 4 sensors:

[Custom foo description](### General Library Sensor)

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
