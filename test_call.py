import requests

# Define the login URL and the data endpoint URL
login_url = "http://156.17.181.172:8000/token"
data_url = "http://156.17.181.172:8000/read-data"

# User credentials
username = "johndoe"
password = "password"

# Define the request payload
data = {
    "bounding_box": [59.0, 49.0, 22.2, 15.2],
    "level": 18,
    "time_from": '2018-01-01',
    "time_to": '2020-02-01',
    "factors": ["precipitation", "temperature"]
}


def login(username, password):
    # Prepare the payload for the login request
    payload = {
        "username": username,
        "password": password
    }

    # Send a POST request to the login endpoint
    response = requests.post(login_url, data=payload)

    if response.status_code == 200:
        # Extract the access token from the response
        token = response.json().get("access_token")
        return token
    else:
        print(f"Failed to login: {response.status_code}")
        print(response.json())
        return None


def fetch_data(token):
    # Define the headers with the JWT token
    headers = {
        "Authorization": f"Bearer {token}"
    }
    # Send a POST request to the data endpoint
    response = requests.post(data_url, json=data, headers=headers)

    if response.status_code == 200:
        print("Data fetched successfully!")
        download_link = response.json().get("download_link")
        return download_link
    else:
        print(f"Failed to fetch data: {response.status_code}")
        print(response.json())


def download_file(download_link, token):
    # Define the headers with the JWT token
    headers = {
        "Authorization": f"Bearer {token}"
    }

    # Send a GET request to download the file
    response = requests.get(download_link, headers=headers)

    if response.status_code == 200:
        file_name = download_link.split("/")[-1]
        with open(file_name, "wb") as f:
            f.write(response.content)
        print(f"File downloaded successfully as {file_name}")
    else:
        print(f"Failed to download file: {response.status_code}")
        print(response.json())


def main():
    # Log in and get the access token
    token = login(username, password)

    if token:
        # Fetch data to get the download link
        download_link = fetch_data(token)

        if download_link:
            # Use the token to download the file
            download_file(download_link, token)


if __name__ == "__main__":
    main()
