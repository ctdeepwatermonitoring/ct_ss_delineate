import requests
import json
import pandas as pd
import os
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

# Returns coordinate points snapped to the nearest stream in the provided streams geojson file
def snap_to_stream(lat, lon, streams_geojson_path):
    with open(streams_geojson_path) as f:
        streams_geojson = json.load(f)

    # Original point from the database
    point = Point(lon, lat)

    # Iterate through stream features to find the nearest point on any stream
    best_dist = float('inf')
    snapped_point = None

    for feature in streams_geojson['features']:
        geom = shape(feature['geometry'])
        nearest_pt = nearest_points(point, geom)[1]
        dist = point.distance(nearest_pt)
        if dist < best_dist:
            best_dist = dist
            snapped_point = nearest_pt
    
    # Return the snapped coordinates (latitude, longitude)
    return snapped_point.y, snapped_point.x

# Read and filter CSV data
csv_path = '/home/deepuser/watershed_project/test.csv'
data = pd.read_csv(csv_path)
print(data.head())

# Extract CSV filename without extension for output naming
csv_filename = os.path.basename(csv_path)
csv_name_without_ext = os.path.splitext(csv_filename)[0]

# StreamStats Service URLs
DelineateURL = 'https://streamstats.usgs.gov/ss-delineate/v1/delineate/sshydro/{region}'
BasinCharacteristicsURL = 'https://streamstats.usgs.gov/ss-hydro/v1/basin-characteristics/calculate'
NSSServiceURLS = {
    'regressionRegions': 'https://streamstats.usgs.gov/nssservices/regressionregions/bylocation',
    'statisticGroups': 'https://streamstats.usgs.gov/nssservices/statisticgroups',
    'scenarios': 'https://streamstats.usgs.gov/nssservices/scenarios',
    'computeFlowStats': 'https://streamstats.usgs.gov/nssservices/scenarios/estimate'
}

#Step 1 - Delineate the watershed
# Initialize dictionaries to store results organized by staSeq and statGroupID
all_geometries = {}
all_basin_characteristics = {}
all_flow_stats = {}
region = 'CT'
url = DelineateURL.format(region=region)

# Get statistic groups for the region and regression region we are working with (Duration_Flow_2010_5052, code GC1448)
statGroupParams = {
    'regions': region,
    'regressionRegions': 'GC1448'
}
statGroupResponse = requests.get(url=NSSServiceURLS['statisticGroups'], params=statGroupParams)
if statGroupResponse.status_code == 200:
    statGroupData = json.loads(statGroupResponse.content.decode('utf-8'))
    statGroupIDs = [group['id'] for group in statGroupData]
    statGroupNames = {group['id']: group['name'] for group in statGroupData}
else:
    print(f"Error fetching statistic groups: {statGroupResponse.status_code}")
    print(statGroupResponse.content.decode('utf-8'))

# Iterate through each site, snap to stream, and delineate watershed
for _, row in data.iterrows():
    ylat = row['ylat']
    xlong = row['xlong']
    staSeq = row['staSeq']

    # Snap the original coordinates to the nearest stream
    snapped_lat, snapped_lon = snap_to_stream(ylat, xlong, 'Final_Streamflow_Classifications_1981697674842956603.geojson')
    
    params = {
        "lat": snapped_lat,
        "lon": snapped_lon
    }

    # Make the Delineation request with the snapped coordinates
    response = requests.get(url, params=params)

    if response.status_code == 200:
        delineationResponse =  json.loads(response.content.decode('utf-8')) # response from Delineation service. This will be used in step 4
        collections = delineationResponse['bcrequest']['wsresp']['featurecollection'][0]
        for item in collections:
            if item['name'] == 'globalwatershed':
                for feature in item['feature']['features']:
                    props = feature.get('properties', {})
                    if props.get('GlobalWshd') == 1:
                        geometry = feature['geometry'] # geometry of entire watershed. This will be used in step 2
                        all_geometries[staSeq] = geometry
                        break      

    else:
        print('Error:' + response.content.decode('utf-8'))
    
    # Step 2 - Get the scenarios associated with the regression region Duration_Flow_2010_5052 (GC1448)
    # Iterate through statistic groups to get scenarios, then compute basin characteristics and flow stats for each scenario
    for statGroupID in statGroupIDs:
        scenarioURLParams = {
            'regions': region,
            'statisticgroups': statGroupID,
            'regressionregions': 'GC1448'
        }

        # Make the request to get scenarios for this stat group and regression region
        scenarioResponse = requests.get(url=NSSServiceURLS['scenarios'], params=scenarioURLParams)
        if scenarioResponse.status_code == 200:
            scenarios = json.loads(scenarioResponse.content.decode('utf-8'))[0] # available scenarios within the watersheds' regression regions. This will be used in step 5
            parameters = json.loads(scenarioResponse.content.decode('utf-8'))[0]["regressionRegions"][0]["parameters"]
            parameterCodes = [ sub['code'] for sub in parameters ] # basin characteristics (parameters) needed to compute the scenarios. This will be used in step 4
            
            # Step 3 - Compute basin characterics (parameters)
            delineationResponse['bcrequest']['bcLabels'] = ';'.join(parameterCodes)

            # Make the request to compute basin characteristics
            try:
                basinCharacteristicsResponse = requests.post(url = BasinCharacteristicsURL, json=delineationResponse, timeout=30)
            except requests.exceptions.ConnectionError as e:
                print(f"Connection error for staSeq {staSeq}, stat group {statGroupID}: Connection aborted")
                continue
            except requests.exceptions.Timeout:
                print(f"Timeout for staSeq {staSeq}, stat group {statGroupID}: Request timed out")
                continue

            if basinCharacteristicsResponse.status_code == 200:
                basinCharacteristics = json.loads(basinCharacteristicsResponse.content.decode('utf-8')) # calculated basin characteristics. This will be used in step 5
                
                # Store basin characteristics organized by staSeq and statGroupID
                if staSeq not in all_basin_characteristics:
                    all_basin_characteristics[staSeq] = {}
                all_basin_characteristics[staSeq][statGroupID] = {
                    'name': statGroupNames[statGroupID],
                    'characteristics': basinCharacteristics
                }

                # Step 4 - Compute Flow Statistics
                flowStatsURLParams = {
                    'regions:': region
                }

                # Build flowStatsPOST Body for this specific scenario
                flowStatsPOSTBody = []
                scenarios_copy = json.loads(json.dumps(scenarios))
                for counter, x in enumerate(scenarios_copy['regressionRegions'][0]['parameters']):
                    for p in basinCharacteristics:
                        if x['code'].lower() == p['code'].lower():
                            scenarios_copy['regressionRegions'][0]['parameters'][counter]['value'] = p['value']
                flowStatsPOSTBody.append(scenarios_copy)

                # POST request
                try:
                    flowStatsResponse = requests.post(url=NSSServiceURLS['computeFlowStats'],
                                                        params=flowStatsURLParams,
                                                        json=flowStatsPOSTBody,
                                                        timeout=30)
                    if flowStatsResponse.status_code == 200:
                        flowStats = json.loads(flowStatsResponse.content.decode('utf-8'))

                        # Store flow stats organized by staSeq and statGroupID
                        if staSeq not in all_flow_stats:
                            all_flow_stats[staSeq] = {}
                        all_flow_stats[staSeq][f'flowStats_{statGroupID}'] = flowStats[0]
                    else:
                        print(f"Error computing flow stats for staSeq {staSeq}, stat group {statGroupID}: " + flowStatsResponse.content.decode('utf-8'))

                except requests.exceptions.ConnectionError as e:
                    print(f"Connection error for staSeq {staSeq}, stat group {statGroupID}: Connection aborted")
                    continue
                except requests.exceptions.Timeout:
                    print(f"Timeout for staSeq {staSeq}, stat group {statGroupID}: Request timed out")
                    continue

            else:
                print('Error:' + response.content.decode('utf-8'))
        else:
            print('Error:' + response.content.decode('utf-8'))


# Save results to JSON files with input filename included
# Convert geometries to GeoJSON format
feature_collection = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"staSeq": staSeq},
            "geometry": geometry
        }
        for staSeq, geometry in all_geometries.items()
    ]
}
geometry_file = f"results/geometry_{csv_name_without_ext}.geojson"
basin_chars_file = f"results/basin_characteristics_{csv_name_without_ext}.json"
flow_stats_file = f"results/flowStats_{csv_name_without_ext}.json"

with open(geometry_file, "w") as file:
    json.dump(feature_collection, file, indent=4)

with open(basin_chars_file, "w") as file:
    json.dump(all_basin_characteristics, file, indent=4)

with open(flow_stats_file, "w") as file:
    json.dump(all_flow_stats, file, indent=4)

print(f"Results saved to {geometry_file}, {basin_chars_file}, and {flow_stats_file}")