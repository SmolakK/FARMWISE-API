import requests

# Define the URL for the FastAPI endpoint
url = "http://156.17.181.172:8000/read-data"

# Define the request payload
data = {
    "bounding_box": [59.0,49.0,22.2,15.2],
    "level": 18,
    "time_from": '2018-01-01',
    "time_to": '2020-02-01',
    "factors": ["precipitation", "temperature"]
}

# Send the POST request to the FastAPI endpoint
response = requests.post(url, json=data)

# Check if the request was successful
if response.status_code == 200:
    # Parse the JSON response
    response_json = response.json()
    print("Response JSON:", response_json)

    # Get the download links from the response
    download_links = response_json.get("download_links", [])

    # Download each file from the download links
    for link in download_links:
        file_name = link.split("/")[-1]
        download_response = requests.get(link)

        if download_response.status_code == 200:
            # Save the file to the local file system
            with open(file_name, "wb") as file:
                file.write(download_response.content)
            print(f"Downloaded {file_name}")
        else:
            print(f"Failed to download {file_name} from {link}")
else:
    print("Request failed with status code:", response.status_code)
    print("Response:", response.text)
