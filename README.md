# ct_ss_delineate
Script to use stream stat web services to delineate drainage basins and calc stream flow stats for CT

## Documentation of StreamStatsFlowStatisticsWorkflow_CSVDirect.py

This script is designed to take an input csv with the columns ylat, xlong, and staSeq.
The csv file can be placed in the ct_ss_delineate folder.

The script contains a function called snap_to_stream which takes latitude, longitude, and a geojson file as arguments.
The function iterates through every feature in the geojson file and determines the distance between the nearest point to the point of the given lat/long.
The smallest distance is saved and the lat/long of the closest point on the stream feature is returned as the snapped point.

The csv is first read in and the file name is extracted for use in naming the output.
StreamStats Service URLs are also initialized.

Dictionaries are initialized to store basin geometries, basin characteristics, and flow statistics.

A request is made to get the statistic groups that are available for the region and regression region.

The csv data is looped through and the ylat, xlong, and staSeq are extracted.
ylat and xlong are used alongside the Final_Streamflow_Classifications_1981697674842956603.geojson file to call the snap_to_stream function.
snapped_lat and snapped_lon are returned and used in the calculations.

A delineation request is made, and the returned geometry is added as a value to the dictionary all_geometries using staSeq as the key.

For each available statistic group, a request is made for the scenarios for the specified regression region.
The parameterCodes from the scenarioResponse are joined to the delineationResponse and a request is made for the basin characteristics.
The basin characteristics are stored in the all_basin_characteristics organized by staSeq and statistic group id.

For the specific scenario, a flowStatsPOSTBody is built.
A POST request is made and once the response is received the flow statistics are stored in the all_flow_stats dictionary by staSeq and statGroupID.

The content of all_geometries are converted to geojson format.
An all_geometries geojson, basin_characteristics json, and flowStats json are all written out to the results folder.

## Documentation of StreamStatsFlowStatisticsWorkflowQueryDatabase.py

This script is designed to take an input csv with the columns staSeq and summer_category.
The csv file can be placed in the ct_ss_delineate folder.

A .env file is required for this script.
A .env.example file has been provided.
The script begins by loading the .env file.

The script contains a function called snap_to_stream which takes latitude, longitude, and a geojson file as arguments.
The function iterates through every feature in the geojson file and determines the distance between the nearest point to the point of the given lat/long.
The smallest distance is saved and the lat/long of the closest point on the stream feature is returned as the snapped point.

The database is connected to via the credentials in the .env file.

The data is read from the csv and a subset is taken as sites that are Cold in the summer_category.
This data is used for the rest of the calculations.

All of the staSeqs are extracted, and a query is sent to the database to select the xlong, ylat, and the staSeq from the stations table where the staSeq matches a staSeq in the dataframe.

StreamStats service URLs are initialized along with empty dictionaries for storing basin geometries, basin characteristics, and flow statistics.

A request is made to get the statistic groups that are available for the region and regression region.

The ylat, xlong, and staSeq from the query are looped through.
ylat and xlong are used alongside the Final_Streamflow_Classifications_1981697674842956603.geojson file to call the snap_to_stream function.
snapped_lat and snapped_lon are returned and used in the calculations.

A delineation request is made, and the returned geometry is added as a value to the dictionary all_geometries using staSeq as the key.

For each available statistic group, a request is made for the scenarios for the specified regression region.
The parameterCodes from the scenarioResponse are joined to the delineationResponse and a request is made for the basin characteristics.
The basin characteristics are stored in the all_basin_characteristics organized by staSeq and statistic group id.

For the specific scenario, a flowStatsPOSTBody is built.
A POST request is made and once the response is received the flow statistics are stored in the all_flow_stats dictionary by staSeq and statGroupID.

The content of all_geometries are converted to geojson format.
An all_geometries geojson, basin_characteristics json, and flowStats json are all written out to the results folder.