# Scope

Given the time constraints, focus will be placed on the data relationships. The approach could easily be scaled to bigger regions with automated data ingestion, additional API calls, etc. The dashboard will remain simple, with flight trajectories being described rather than mapped.

For this exercise, we’ll assume the flight will take place in the “gros de Vaud” region, which we’ll assume is a flat plain of altitude ~600m AMSL. Altitudes can be expressed in AMSL, AGL, and STD. For this exercise, we approximately convert all altitudes to AMSL. For AGL we add the 600m approx. altitude of the take-off site. We assume that STD is roughly equivalent to AMSL.

## Airspace Maps

https://airspace.shv-fsvl.ch/doc/v2/geojson  
geojson to match swisstopo  
Some airspaces are activated/modified by NOTAMs, see below.  
Wildlife zones are fetched by a separate endpoint and are ignored in this exercise.

## Airspace Descriptions

A number of official files in French were converted into more concise summaries of airspace classes and types. These .md files were parsed to create entries for each airspace class/kind.

## Terrain

data regarding building density/water/altitude/steepness of terrain https://docs.geo.admin.ch/  
In this initial demo, this data will not be integrated fully, although it is clearly an integral part of flight planning. In a full application, it would impact the flight trajectory (min. 300m above surface, except in landing phase, i.e. last 10 mins of flight, higher above agglomerations, etc.), avoidance of obstacles (in this demo, we will assume that the flight region is a plain at altitude approx. 600m ASL),  choice of appropriate landing zones (need open, flat spaces, ie. low building density, no lakes, relatively flat area)

## Wind

https://open-meteo.com/en/docs  
In the interest of this demonstration, we’ll assume that a flight is one hour long and that the forecast for the takeoff time/location applies throughout the flight. In a future version, it would be important to fetch additional wind forecasts at points along the potential trajectories.

## NOTAMs

NOtices To AirMen (NOTAMs) can be fetched via APIs, but there is no official open API in Switzerland. Also, these APIs often require an ICAO airport code, whereas balloon flights rarely take off from aerodromes. Skyguide publish a Daily Airspace Bulletin Switzerland (DABS) which is available from the skybriefing website https://www.skybriefing.com/o/dabs?today  
The DABS for the following day is published at 16:00 local time, https://www.skybriefing.com/o/dabs?tomorrow  
Given Switzerland’s limited size, parsing these official DABS is an appropriate way to obtain the relevant NOTAMs for the flight. Each NOTAM can be limited in time (Validity UTC), and geographically (Lower Limit & Upper Limit (m/ft AMSL or FL), Center Point, Covering Radius).

## Data

In the interest of time, NetworkX will be used to represent the data source relationships. To make the graph relationships most relevant for the RAG, it is best to process the DABS into individual notams, each with their area of validity. We also need to break down pdfs about airspaces classes and types into one entry for each airspace parameter. And we should parse all the different airspaces in Switzerland, and include them in the database. This information changes rarely, and does not need to be reindexed regularly. The dynamic parts are usually DABs dependent, and therefore updated daily.

Fetched documents are ranked according to their distance from the take-off point, whether they’re always applicable, whether they’re active, and their relevance to balloon flights.

## Dashboard

When we click on the map, relevant Airspace and NOTAM regions appear, this point is also recorded as the take-off point. Details regarding the airspaces and NOTAMs will appear in the graph context box (a max trajectory length is calculated based on the forecast wind speeds at different altitudes and all airspaces/NOTAMS within this radius are fetched/displayed). Response will describe potential flight paths, and things to take into consideration. Future implementation would also highlight potential flight paths on the map, and take into consideration factors such as desired flight time, etc.
